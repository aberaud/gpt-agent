import asyncio
import json
import os
import pprint
import shutil
import subprocess
import datetime
import traceback
from typing import Optional
#import yaml
from chat import ChatSession, get_total_usage, get_model_list
from web_server import WebServer, Session
from search import search
from asyncio import CancelledError, Queue
from agentcmd import CommandParser, ParseError

purpose_agent = """You are an autonomous agent whose objective is to achieve a provided goal.
Analyze the goal and break it down into smaller tasks to assign to other agents, until the goal is achieved,
or acheive it yourself if you can using your own experience and the provided functions.
Take time to think and inspect your environment before acting.
Always check the result of your work and the work of other agents."""

purpose_planner = """Your objective is to acheive a long-term goal.

"""

purpose_subagent = """Your objective is to acheive a goal assigned to you, as part of a larger plan.
Complete the task yourself or break it down into smaller tasks to be solved by other agents.
Take time to think and inspect your environemnt before acting since other agents might have already done some work.
Always check the result of your work and the work of other agents.
After you complete, only your completion message and filesystem changes will be preserved.
"""

purpose_single_agent = """You are an experienced engineer whose purpose is to achieve a provided goal.
Analyze the goal and, if required, break it down into smaller tasks to be solved, and use your own experience and the provided tools to acheive the goal.
Take time to think and inspect your environment before acting.
Always check the result of your work."""

async def info_callback(agent, args):
    print(f"INFO: {args}")

async def search_callback(agent, args):
    print(f"QUERY: {args}")
    results = await search(query=args['content'], source=args['source'])
    print(f"RESULTS: {results}")
    return pprint.pformat(results)

async def write_callback(agent, args):
    file_name = args['filename']
    content = args.get('content', '')
    try:
        with open(file_name, 'w') as file:
            file.write(content)
        print(f"[SUCCESS] Successfully wrote to {file_name}")
        return f"Wrote {len(content)} bytes to {file_name}"
    except Exception as e:
        print(f"[ERROR] Failed to write: {e}")
        return f"Error: {e}"

async def request_callback(agent, args):
    to = args['supervisor']
    request = args['content']
    print(f"[REQUEST] for {to}: {request}")
    await agent.get_human_input(request)

async def assign_callback(agent, args):
    return await agent.handle_agent_assign(args['agent_id'], args['content'])

async def run_callback(agent, args):
    print(f"RUN: {args}")
    return await agent.handle_agent_process(args['content'] if type(args) is dict else args)

async def python_callback(agent, args):
    content = args['content']
    print(f"PYTHON:\n{content}")
    if not content:
        print("No Python code provided.")
        return

    process = await asyncio.create_subprocess_exec(
        "ipython",
        "--no-banner",
        "--no-confirm-exit",
        "--no-term-title",
        "--quiet",
        "--colors=NoColor",
        "--InteractiveShell.xmode=Plain",
        "-c",
        content,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return_code = process.returncode
    if return_code == 0:
        #print(f"Python code output:\n{stdout.decode('utf-8')}")
        return stdout.decode('utf-8')
    else:
        #print(f"Error ({return_code}): {stderr.decode('utf-8') or stdout.decode('utf-8')}")
        return stderr.decode('utf-8') or stdout.decode('utf-8')


async def complete_callback(agent, args):
    print(f"COMPLETE: {args}")
    await agent.stop()

commands = [
    {
        "name": "WRITE",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The file to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file"
                }
            },
            "required": ["filename"],
        },
        "description": "Write to a file (overrides existing content, if any)",
        "callback": write_callback
    },
    {
        "name": "REQUEST",
        "parameters": {
            "type": "object",
            "properties": {
                "supervisor": {
                    "type": "string",
                    "description": "The id of the supervisor to request information from"
                },
                "content": {
                    "type": "string",
                    "description": "The request to send to the supervisor"
                }
            },
            "required": ["supervisor", "content"],
        },
        "description": "Ask for more information to a supervisor (human or agent) - don't assign tasks or report status with this command",
        "callback": request_callback
    },
    {
        "name": "ASSIGN",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The id of the agent to assign the task to"
                },
                "content": {
                    "type": "string",
                    "description": "The task to assign to the agent"
                }
            },
            "required": ["agent_id", "content"],
        },
        "description": "Assign a task to another independent agent. Provide an id and a detailed description of the task including all required context.",
        "callback": assign_callback
    },
    {
        "name": "RUN",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The commands to run"
                }
            },
            "required": ["content"],
        },
        "description": "Run one or more shell command and get the output. Note that the shell is reset between each invocation.",
        "callback": run_callback
    },
    {
        "name": "PYTHON",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The python code to run"
                }
            },
            "required": ["content"],
        },
        "description": "Run code or commands in an IPython shell (python 3.11). Use it to perform calculations, text manipulation, or other operations. The shell is reset between each invocation.",
        "callback": python_callback
    },
    {
        "name": "QUERY",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "The source to query (knowledge-graph, wikipedia, google)",
                },
                "content": {
                    "type": "string",
                    "description": "The query to send to the source",
                }
            },
            "required": ["source", "content"],
        },
        "description": "Search for information online. Available sources: knowledge-graph, wikipedia, google",
        "example": "QUERY google\nParis",
        "callback": search_callback,
    },
    {
        "name": "COMPLETE",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "The status of the task (success or failure)",
                },
                "content": {
                    "type": "string",
                    "description": "The message to send to the supervisor",
                }
            },
            "required": ["status", "content"],
        },
        "description": "Notify task completion (either success or failure), providing your supervisor with a corresponding 'completed' message. Provide all relevent information about what you did in the message. If you are stuck in a loop, complete with failure.",
        "callback": complete_callback
    }
]

def list_files(startpath):
    result = []
    for root, dirs, files in os.walk(startpath):
        if root != startpath:
            relative_root = root[len(startpath):].lstrip(os.sep)
            level = relative_root.count(os.sep)
            indent = ' ' * 4 * level
            result.append(f"{indent}{os.path.basename(root)}/")
        else:
            level = 0
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            result.append(f"{subindent}{f}")
    return '\n'.join(result)

def getPurpose(type='agent'):
    if type == 'agent':
        return purpose_agent#purpose_agent
    elif type == 'subagent':
        return purpose_subagent

def getSystemPrompt(name, path, type='agent'):
    return [purpose_agent if type == 'agent' else purpose_subagent,
           f"""You are running in a Alpine Linux container, in your home directory.
Use functions directly with no introduction. 
Never report directly, instead use the 'COMPLETE' function to report completion of a task.
""",f"""
date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
name: {name}
supervisor_path: {path}
directory_content:\n{list_files(os.getcwd())}
"""]

class Agent:
    def __init__(self, args, web_server: Session, prompt: str | list[str] = None, name: str = "main", role : str = 'agent', parent: Optional['Agent']=None, context: dict={}):
        self.args = args
        self.commands = {command['name']: command for command in commands}
        self.name = name
        self.web_server = web_server
        self.parent = parent
        self.context = context
        self.supervisor_path = ['human'] if parent is None else parent.supervisor_path + [parent.name]
        if prompt is None:
            prompt = getSystemPrompt(name, self.supervisor_path, role)
        self.chat_session = ChatSession(args.model, prompt, commands=self.commands)
        self.stopped = False
    
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

    async def send_new_message(self, message, status='running'):
        try:
            if self.web_server:
                await self.web_server.add_message(self.name, Agent.parse_message(message), usage=get_total_usage())
        except KeyboardInterrupt:
            pass
        except CancelledError:
            pass
        except Exception as e:
            print(f"[ERROR] Couldn't send update to web server")
            traceback.print_exc()

    async def stop(self):
        print(f"Stopping agent {self.name}")
        self.stopped = True

    async def run(self):
        print(f"Agent {self.name} ({self.chat_session.model}) created")
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
                            print(f"[WARN] Couldn't parse arguments: {function_args}")
                        await self.handle_agent_command(function_name, function_args)
                #except ParseError as e:
                #    print(f"[ERROR] Couldn't parse agent's message: {response}")
                #    self.chat_session.add_message(f"PARSE_ERROR\n{e}\nHint: always use the proper syntax `COMMAND arguments` and one of the documented commands. Retry your last message using the appropriate syntax.", "system")
                except Exception as e:
                    print(f"[ERROR] Couldn't handle agent's message: {response}")
                    traceback.print_exc()
                    self.chat_session.add_message(f"ERROR\n{e}", "system")
            except CancelledError:
                break
            except KeyboardInterrupt:
                print("\nExiting.")
                break
        #await self.send_update()
        print(f"Agent {self.name} ended")

    async def add_message(self, message: str, role: str = "user", name: Optional[str] = None):
        await self.send_new_message(self.chat_session.add_message(message, role, name))

    async def get_human_input(self, message, reply_type="reply"):
        user_input = await self.web_server.get_input(self.name, message)
        print(f"{message}: {user_input}")
        await self.add_message(json.dumps({ reply_type: user_input }))

    async def handle_agent_command(self, command_name, args):
        command = self.commands[command_name]
        # print(f"Handling command {command} with args {args}")
        result = await command["callback"](self, args)
        print(f"Command {command['name']} returned: {result}")
        if result is not None:
            await self.add_message(result, "function", name=command_name)

    def convert_history_for_subagent(self):
        agent_history = self.chat_session.messages[1:-1]
        #agent_history = [self.convert_message_for_subagent(h) for h in agent_history]
        return [h for h in agent_history if h is not None]

    async def handle_agent_assign(self, sub_agent_id, task):
        print(f"[ASSIGN] {sub_agent_id} {task}")
        #await self.send_update()
        sub_agent = Agent(self.args, web_server=self.web_server, name=sub_agent_id, role='subagent', parent=self, context=self.context)
        #sub_agent.chat_session.add_message(json.dumps({"main_goal": task}), "user")
        await sub_agent.add_message(json.dumps({"main_goal": task}), "user")
        await sub_agent.run()
        last_msg = sub_agent.chat_session.messages[-1]
        last_msg_parsed = last_msg.get("function_call")
        print(f"[ASSIGN] {sub_agent_id} completed: {last_msg_parsed}")
        return last_msg_parsed and last_msg_parsed['arguments']

    async def handle_agent_process(self, command):
        #await self.send_update()
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

async def agent_worker(task_queue: Queue):
    while True:
        try :
            task = await task_queue.get()
            if task is None:
                break
            await asyncio.gather(task)
        except KeyboardInterrupt:
            break
        except CancelledError:
            break
        except Exception as e:
            print(f'Error in worker: {e}')
            traceback.print_exc()
            break


task_queue = Queue()

async def add_agent(args, session: Session):
    session.task = asyncio.create_task(execute_chat(args, session))
    await task_queue.put(session.task)

async def execute_chat(args, session: Session):
    # Delete every file and directory in the current directory
    for file_name in os.listdir():
        if os.path.isfile(file_name):
            os.remove(file_name)
        else:
            shutil.rmtree(file_name)

    context = {}
    
    agent = Agent(args, web_server=session, context=context)
    await session.set_agent(agent, messages=[Agent.parse_message(message) for message in agent.chat_session.messages])
    await session.set_property('models', await get_model_list())
    await session.set_property('usage', get_total_usage())
    await session.send_init_state()
    await agent.get_human_input("Main goal", "main_goal")
    await agent.run()
    await session.set_state(agent.name, 'completed', usage=get_total_usage())
    print("Completed")


async def main(args):
    web_server = WebServer(args, add_agent)
    await asyncio.gather(
        web_server.run(),
        asyncio.create_task(agent_worker(task_queue))
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Start the Argent server.")
    parser.add_argument("-m", "--model", default="gpt-3.5-turbo-16k-0613", help="Specify the default model to use.")
    args = parser.parse_args()
    asyncio.run(main(args))
