import asyncio
import json
import traceback
from typing import Optional
from asyncio import CancelledError
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall

from .chat import ChatSession, get_total_usage
from .commands import AgentParseError
from .web_server import WebSession
from .prompts import getSystemPrompt, getCommands

class Agent:
    def __init__(self, args, context, name: str = "main", role : str = 'agent', prompt: str | list[str] = None, parent: Optional['Agent']=None, web_server: WebSession = None):
        self.args = args
        self.commands = {command['name']: command for command in getCommands(role)}
        self.name = name
        self.role = role
        self.web_server = web_server
        self.parent = parent
        self.context = context
        self.supervisor_path = ['human'] if parent is None else parent.supervisor_path + [parent.name]
        self.chat_session = ChatSession(args.model, functions=self.commands)
        self.stopped = False
        if prompt is None:
            prompt = getSystemPrompt(name, self.supervisor_path, role)
        self.prompt = prompt

    async def init(self):
        if isinstance(self.prompt, list):
            for p in self.prompt:
                await self.add_message(p, role="system")
        elif self.prompt:
            await self.add_message(self.prompt, role="system")
        if self.web_server:
            await self.web_server.set_agent_properties(self.name, self.role, self.chat_session.model, list(self.commands.keys()), self.parent.name if self.parent else None)

    @staticmethod
    def parse_message(message):
        function_call = message.get("function_call")
        role = message.get("role")
        if function_call:
            arguments = function_call.get("arguments")
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                print(f"[WARN] Couldn't parse arguments: {arguments}")
            return {
                'role': role,
                'content': message['content'],
                'function_call': {
                    'name': function_call["name"],
                    'arguments': arguments
                }
            }
        if role == 'function':
            content = message.get("content")
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass
            return {
                'role': role,
                'name': message.get('name'),
                'content': content
            }
        return message
    
    """     @staticmethod
    def parse_message(message: ChatCompletionMessage):
        print(message)
        function_call = message.get("function_call")#message.tool_calls# get("function_call")
        role = message.get("role")#.message.role#.get("role")
        if function_call:
            function = function_call[0].function
            arguments = function.get("arguments")#.arguments#.get("arguments")
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                print(f"[WARN] Couldn't parse arguments: {arguments}")
            return {
                'role': role,
                'content': message.content,
                'function_call': {
                    'name': function.name,
                    'arguments': arguments
                }
            }
        if role == 'function':
            content = message.content#.get("content")
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass
            return {
                'role': role,
                #'name': message.get('name'),
                'content': content
            }
        return message
    """

    async def send_new_message(self, message: ChatCompletionMessage, status='running'):
        try:
            if self.web_server:
                await self.web_server.add_message(self.name, Agent.parse_message(message), usage=get_total_usage())
        except KeyboardInterrupt:
            raise
        except CancelledError:
            raise
        except Exception as e:
            print(f"[ERROR] Couldn't send update to web server")
            traceback.print_exc()

    async def stop(self):
        print(f"Stopping agent {self.name}")
        self.stopped = True

    async def run(self):
        print(f"Agent {self.name} ({self.chat_session.model}) created. Functions: {self.commands.keys()}")
        if self.web_server:
            await self.web_server.set_state(self.name, 'running', usage=get_total_usage())
        while not self.stopped:
            try:
                print(f"Agent {self.name} running...")
                response = await self.chat_session.chat()
                await self.send_new_message(response)
                try:
                    function_call = response.get("function_call")
                    if function_call:
                        function_name = function_call["name"]
                        function_args = function_call["arguments"]
                        try:
                            function_args = json.loads(function_args)
                        except json.JSONDecodeError:
                            raise AgentParseError(f"Couldn't parse arguments: {function_args}")
                        await self.handle_agent_command(function_name, function_args)
                except AgentParseError as e:
                    print(f"[ERROR] Couldn't parse agent's message: {response}")
                    await self.add_message(f"PARSE_ERROR\n{e}\nRetry your last message using the appropriate syntax.", "system")
                except KeyboardInterrupt:
                    raise
                except CancelledError:
                    raise
                except Exception as e:
                    print(f"[ERROR] Couldn't handle agent's message: {response}")
                    traceback.print_exc()
                    await self.add_message(f"ERROR\n{type(e).__name__}: {e}", "system")
            except CancelledError:
                break
            except KeyboardInterrupt:
                print("\nExiting.")
                break
        #await self.send_update()
        if self.web_server:
            await self.web_server.set_state(self.name, 'completed', usage=get_total_usage())
        print(f"Agent {self.name} ended")

    async def add_message(self, message: str, role: str = "user", name: Optional[str] = None):
        await self.send_new_message(self.chat_session.add_message(message, role, name))

    async def get_human_input(self, message, reply_type="reply"):
        user_input = await self.web_server.get_input(self.name, message)
        print(f"{message}: {user_input}")
        await self.add_message(json.dumps({ reply_type: user_input }))

    async def handle_agent_command(self, command_name: str, args):
        command = self.commands[command_name.upper()]
        # print(f"Handling command {command} with args {args}")
        result = await command["callback"](self, args)
        print(f"Command {command['name']} returned: {result}")
        if result is not None:
            await self.add_message(result, "function", name=command_name)

    async def handle_agent_assign(self, sub_agent_id, task, messages: list[str]=[], role='worker'):
        sub_agent_id = self.context.new_agent_id(sub_agent_id)
        print(f"[ASSIGN] {sub_agent_id} {task}")
        sub_agent = Agent(self.args, self.context, name=sub_agent_id, role=role, parent=self, web_server=self.web_server)
        self.context.add_agent(sub_agent)
        await sub_agent.init()
        if task:
            await sub_agent.add_message(json.dumps({"main_goal": task}))
        for m in messages:
            await sub_agent.add_message(m)
        await sub_agent.run()
        last_msg = sub_agent.chat_session.messages[-1]
        last_msg_parsed = last_msg.get("function_call")
        print(f"[ASSIGN] {sub_agent_id} completed: {last_msg_parsed}")
        if self.web_server:
            await self.web_server.set_state(self.name, 'running')
        return last_msg_parsed and last_msg_parsed['arguments']

    async def handle_agent_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            stdout = stdout.decode()
            stderr = stderr.decode()
            return_code = process.returncode
            if return_code == 0:
                print(f"[OUTPUT] {stdout}")
                return f"stdout: {stdout}"
            else:
                print(f"[ERROR] Command returned exit code {return_code}\n{stderr}")
                return f"stderr: {stderr}"
        except Exception as e:
            print(f"[ERROR] Failed to run the command: {e}")
            return f"error: {e}"


async def main(args):
    await asyncio.gather()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Start the Argent server.")
    parser.add_argument("-m", "--model", default="gpt-4o", help="Specify the default model to use.")
    args = parser.parse_args()
    asyncio.run(main(args))
