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
from chat import ChatSession
from web_server import WebServer, Session
from search import search
from asyncio import CancelledError, Queue
from agentcmd import CommandParser, ParseError

purpose_agent = """You are an autonomous agent whose objective is to achieve a provided goal.
Analyze the goal and break it down into smaller tasks to assign to other agents, until the goal is achieved,
or acheive it yourself if you can using your own experience and the provided commands.
Take time to think and inspect your environment before acting.
Always check the result of your work and the work of other agents."""

purpose_planner = """Your objective is to acheive a long-term goal.

"""

purpose_subagent = """Your objective is to acheive a goal assigned to you, as part of a larger plan.
Complete the task yourself or break it down into smaller tasks to be solved by other agents.
Take time to think and inspect your environemnt before acting since other agents might have already done some work.
Always check the result of your work and the work of other agents.
After you complete, only your completion message will be preserved, along with any change you made to the system.
"""

purpose_single_agent = """You are an experienced engineer whose purpose is to achieve a provided goal.
Analyze the goal and, if required, break it down into smaller tasks to be solved, and use your own experience and the provided tools to acheive the goal.
Take time to think and inspect your environment before acting.
Always check the result of your work."""

async def info_callback(agent, args, content):
    print(f"INFO: {content}")

async def search_callback(agent, args, content):
    print(f"QUERY: {content}")
    results = await search(content)
    print(f"RESULTS: {results}")
    return pprint.pformat(results)

async def write_callback(agent, args, content):
    file_name = args['filename']
    try:
        with open(file_name, 'w') as file:
            file.write(content)
        print(f"[SUCCESS] Successfully wrote to {file_name}")
        return f"Wrote {len(content)} bytes to {file_name}"
    except Exception as e:
        print(f"[ERROR] Failed to write: {e}")
        return f"Error: {e}"

async def request_callback(agent, args, content):
    print(f"REQUEST: {args} {content}")
    to = args['supervisor']
    print(f"[REQUEST] for {to}: {content}")
    await agent.get_human_input(content)

async def assign_callback(agent, args, content):
    print(f"ASSIGN: {args} {content}")
    await agent.handle_agent_assign(args['agent_id'], content)

async def run_callback(agent, args, content):
    print(f"RUN: {content}")
    return await agent.handle_agent_process(content)
    #return subprocess.check_output(content, shell=True).decode('utf-8')

async def python_callback(agent, args, content):
    print(f"PYTHON:\n{content}")
    if content is None:
        print("No Python code provided.")
        return

    process = await asyncio.create_subprocess_exec(
        "ipython",
        "-c",
        content,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return_code = process.returncode
    if return_code == 0:
        print(f"Python code output:\n{stdout.decode('utf-8')}")
        return stdout.decode('utf-8')
    else:
        print(f"Error: {stderr.decode('utf-8')}")
        return stderr.decode('utf-8')


async def complete_callback(agent, args, content):
    print(f"COMPLETE: {args} {content}")
    await agent.stop()

commands = [
    {
        "name": "WRITE",
        "args": ['filename'],
        "description": "Write to a file (overrides existing content, if any)",
        "example": "WRITE file.txt\nthis is some\nmultiline file content",
        "callback": write_callback
    },
    {
        "name": "REQUEST",
        "args": ['supervisor'],
        "description": "Ask for more information to a supervisor (human or agent) - don't assign tasks or report status with this command",
        "example": "REQUEST human\nShould we use rust or go?",
        "callback": request_callback
    },
    {
        "name": "ASSIGN",
        "args": ['agent_id'],
        "description": "Assign a task to another agent. Provide an id and a detailed description of the task including all required context.",
        "example": "ASSIGN create\nCreate a directory 'MyProject' with an empty git repo.",
        "callback": assign_callback
    },
    {
        "name": "RUN",
        "args": [],
        "description": "Run one or more shell command and get the output. Note that the shell is reset every line.",
        "example": "RUN\nmkdir project\ncd project && git init",
        "callback": run_callback
    },
    {
        "name": "PYTHON",
        "args": [],
        "description": "Run a python3 script. Use it to perform calculations, text manipulation, or other operations.",
        "example": "PYTHON\nprint(9457*2452-74)",
        "callback": python_callback
    },
    {
        "name": "QUERY",
        "args": ['source'],
        "description": "Search for information online. Available sources: knowledge-graph, wikipedia, google",
        "example": "QUERY google\nParis",
        "callback": search_callback,
    },
    {
        "name": "INFO",
        "args": [],
        "description": "Note information for future reference or planning (don't combine it with other commands - always one command per message)",
        "example": "INFO\nThis is some information to remember for later.",
        "callback": info_callback
    },
    {
        "name": "COMPLETE",
        "args": ['status'],
        "description": "Notify task completion (either success or failure), providing your supervisor with a corresponding 'completed' message. Provide all relevent information about what you did in the message. If you are stuck in a loop, complete with failure.",
        "example": "COMPLETE success\nEmpty repo created in directory 'MyProject'",
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

def getSystemPrompt(name, path, doc, type='agent'):
    return [f"""IDENTITY
{purpose_agent if type == 'agent' else purpose_subagent}""",
           f"""INSTRUCTIONS
You are running in a Alpine Linux container, in your home directory.
Always use the following syntax:
```COMMAND arguments
Optional content
that can be multiline.
```
And always only use a single command every time, directly and without any introduction, comment or text. Trying to use multiple commands at once will result in an error.
Never report directly, instead use the 'COMPLETE' command to report completion of a task.
Available commands:
{doc}
""",f"""ENVIRONMENT
date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
name: {name}
supervisor_path: {path}
directory_content:\n{list_files(os.getcwd())}
"""]

class Agent:
    def __init__(self, args, web_server: Session, prompt: str | list[str] = None, name: str = "main", role : str = 'agent', parent: Optional['Agent']=None):
        self.args = args
        self.cmd = CommandParser(commands)
        self.name = name
        self.web_server = web_server
        self.parent = parent
        self.supervisor_path = ['human'] if parent is None else parent.supervisor_path + [parent.name]
        if prompt is None:
            prompt = getSystemPrompt(name, self.supervisor_path, self.cmd.generate_documentation(), role)
        self.chat_session = ChatSession(args.model, prompt)
        self.stopped = False
    
    def parse_message(self, message):
        #print('parse_message', message)
        command = self.cmd.parse_syntax(message['content'])[0]
        return {
            'role': message['role'],
            #'message': message['content'],
            'command': command
        }

    async def send_update(self):
        try:
            if self.web_server:
                await self.web_server.send_state({
                    'state': 'running',
                    'agents': [{
                        'id': self.name,
                        'path': self.supervisor_path,
                        'messages': [self.parse_message(m) for m in self.chat_session.messages]
                    }]
                })
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
        while not self.stopped:
            try:
                await self.send_update()
                print(f"Agent {self.name} running...")
                response = await self.chat_session.chat()
                try:
                    for command in self.cmd.parse(response):
                        await self.handle_agent_command(command['command'], command['args'], command['content'])
                except ParseError as e:
                    print(f"[ERROR] Couldn't parse agent's message: {response}")
                    self.chat_session.add_message(f"PARSE_ERROR\n{e}\nHint: always use the proper syntax `COMMAND arguments` and one of the documented commands. Retry your last message using the appropriate syntax.", "system")
                except Exception as e:
                    print(f"[ERROR] Couldn't handle agent's message: {response}")
                    traceback.print_exc()
                    self.chat_session.add_message(f"ERROR\n{e}", "system")
            except CancelledError:
                break
            except KeyboardInterrupt:
                print("\nExiting.")
                break
        await self.send_update()
        print(f"Agent {self.name} ended")

    async def get_human_input(self, message, reply_type="reply"):
        user_input = await self.web_server.get_input({
            'state': 'request',
            'id': self.name,
            'message': message
        })
        print(f"{message}: {user_input}")
        self.chat_session.add_message(f"USER_INPUT {reply_type}\n{user_input}")

    async def handle_agent_command(self, command, args, content):
        #print(f"Handling command {command} with args {args} and content {content}")
        result = await command["callback"](self, args, content)
        print(f"Command {command['name']} returned: {result}")
        if result is not None:
            if result:
                self.chat_session.add_message(f"OUTPUT\n{result}", "user")
            else:
                self.chat_session.add_message(f"OUTPUT\n(empty output)", "user")
        return

    def convert_message_for_subagent(self, message):
        msg = self.cmd.parse(message['content'])
        if msg is None or msg.get('type') == 'parse_error':
            return None
        if message['role'] == 'system' and msg.get('type') == 'task':
            return {
                'role': 'assistant',
                'content': yaml.dump({
                    'type': 'assign',
                    'task': msg.get('task'),
                    'id': self.name
                })
            }
        return message

    def convert_history_for_subagent(self):
        agent_history = self.chat_session.messages[1:-1]
        #agent_history = [self.convert_message_for_subagent(h) for h in agent_history]
        return [h for h in agent_history if h is not None]

    async def handle_agent_assign(self, sub_agent_id, task):
        print(f"[ASSIGN] {sub_agent_id} {task}")
        await self.send_update()
        sub_agent = Agent(self.args, web_server=self.web_server, name=sub_agent_id, role='subagent', parent=self)
        sub_agent.chat_session.add_message(f"USER_INPUT main_goal\n{task}", "system")
        await sub_agent.run()
        last_msg = sub_agent.chat_session.messages[-1]
        last_msg_parsed = self.parse_message(last_msg)['command']
        print(f"[ASSIGN] {sub_agent_id} completed: {last_msg_parsed}")
        self.chat_session.add_message(f"OUTPUT {last_msg_parsed['args'][0]}\n{last_msg_parsed['content']}", "user")

    async def handle_agent_process(self, command):
        await self.send_update()
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
        except CancelledError:
            break
        except Exception as e:
            print(f'Error in worker: {e}')
            traceback.print_exc()


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

    session.agent = Agent(args, web_server=session)
    await session.agent.get_human_input("Main goal", "main_goal")
    await session.agent.run()
    await session.send_state({
        'state': 'completed'
    })
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
    parser.add_argument("-m", "--model", default="gpt-4", help="Specify the model to use (default: gpt-4).")
    args = parser.parse_args()
    asyncio.run(main(args))
