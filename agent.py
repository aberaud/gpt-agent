import asyncio
import subprocess
import datetime
import traceback
from typing import Optional
import yaml
from chat import ChatSession
from web_server import WebServer
from search import search

purpose_agent = """You are an autonomous agent whose purpose is to acheive a long-term goal provided by a human supervisor.
Analyse the goal and break it down into smaller subtasks that can be solved by other agents, until the goal is acheived.
Always check the result of your work and the work of other agents."""

purpose_subagent = """You are an autonomous agent whose purpose is to help acheiving a long-term goal provided by a human supervisor.
Your objective is to complete a task provided to you by another agent.
Analyse the long-term goal and the task that you have been assigned,
complete the task yourself or break it down into smaller tasks to be solved by other agents.
Always check the result of your work and the work of other agents.
After you complete, only your completion message will be preserved, along with any change you made to the system.
"""

instructions = """Always communicate in valid YAML format, directly and without any other introduction, comment or text.
Always only output a single action to take (you will have the opportunity for more actions later), one of:
* Note information for future reference:
    {"type": "info", "message": "this is some information"}
  or:
    type: info
    message: |
        this is some
        multiline information
* Lookup for information. Available sources: knowledge-graph, wikipedia, google
    {"type": "query", "source":"knowledge-graph", "query": "Paris"}
* Write to a file (overrides existing content, if any):
    type: write
    file: file.txt
    content: |
        this is some
        multiline file content
* Ask for more information to a supervisor (human or supervisor agent) - don't assign tasks or report status with this command:
    {"type": "request", "to": "human", "message": "should we use rust or go?"}
* Assign a subtask to another agent. Provide a detailed description of the task and an id.
    {"type": "assign", "id": "create", "task": "create the initial project structure"}
* Run one or more shell command and get the output. Note that the shell is reset between each command.
    {"type": "command", "command": "ls -la"}
  or
    {"type": "command", "command": "cat file.txt"}
  or:
    type: command
    command:
        - mkdir project
        - cd project && git init
* Notify task completion (either success or failure), proving your supervisor with a corresponding 'completed' message.
   Provide all relevent information about what you did in the message. If you are stuck in a loop, complete with failure.
    {"type": "complete", "status": "success", "message": "empty repo created"}
"""


def getPurpose(type='agent'):
    if type == 'agent':
        return purpose_agent
    elif type == 'subagent':
        return purpose_subagent

def getSystemPrompt(type='agent'):
    return yaml.safe_dump({
        "type": "task",
        "date": datetime.datetime.now(),
        "instructions": instructions,
        "task": getPurpose(type)
    })

class Agent:
    def __init__(self, chat_session: ChatSession, web_server: WebServer, name: str = "main", parent: Optional['Agent']=None):
        self.chat_session = chat_session
        self.name = name
        self.web_server = web_server
        self.parent = parent
        self.supervisor_path = ['human'] if parent is None else parent.supervisor_path + [parent.name]
        print(f"Agent {name} ({chat_session.model}) created")

    async def send_update(self):
        if self.web_server:
            await self.web_server.send_state({
                'state': 'running',
                'agents': [{
                    'id': self.name,
                    'path': self.supervisor_path,
                    'messages': self.chat_session.messages
                }]
            })

    async def run(self):
        while True:
            try:
                await self.send_update()
                print(f"Agent {self.name} running...")
                response = await self.chat_session.chat()
                try:
                    command = yaml.safe_load(response)
                    task_complete = await self.handle_agent_command(command)
                    if task_complete:
                        break
                except yaml.YAMLError as e:
                    print(f"[PARSE ERROR] Couldn't parse agent's message: {response}", e)
                    self.chat_session.add_message(yaml.dump({
                        "type": "parse_error",
                        "message": f"YAMLError: {e}",
                        "hint": "Make sure you are using valid YAML format. Careful with multiline strings."
                    }), "system")
                except Exception as e:
                    print(f"[ERROR] Couldn't handle agent's message: {response}")
                    print(traceback.format_exc())
                    self.chat_session.add_message(yaml.dump({
                        "type": "error",
                        "message": str(e)
                    }), "system")
            except KeyboardInterrupt:
                print("\nExiting.")
                break
        await self.send_update()
        print(f"Agent {self.name} ended")

    async def handle_agent_command(self, command):
        type = command["type"]
        if type == "info":
            print(f"[INFO] {command['message']}")
        elif type == "request":
            request = command['message']
            to = command['to']
            print(f"[REQUEST] for {to}: {request}")
            user_input = await self.web_server.get_input({
                'state': 'request',
                'id': self.name,
                'message': command['message']
            })
            self.chat_session.add_message(yaml.dump({
                "type": "reply",
                "message": user_input
            }))
        elif type == "assign":
            await self.handle_agent_assign(command)

        elif type == "query":
            source = command['source']
            query = command['query']
            print(f"[QUERY] {source} {query}")
            results = await search(query, source=source)
            self.chat_session.add_message(yaml.dump({
                "type": "results",
                #"source": source,
                #"query": query,
                "results": results
            }), "user")

        elif type == "command": 
            shell_command = command['command']
            if isinstance(shell_command, list):
                for cmd in shell_command:
                    print(f"[COMMAND] {cmd}")
                    self.handle_agent_process(cmd)
            elif isinstance(shell_command, str):
                print(f"[COMMAND] {shell_command}")
                self.handle_agent_process(shell_command)

        elif type == "write":
            file_name = command['file']
            content = command['content']
            print(f"[WRITE] Writing to file {file_name} {content}")
            try:
                with open(file_name, 'w') as file:
                    file.write(content)
                self.chat_session.add_message(yaml.dump({
                    "file": file_name,
                    "success": True
                }), "user")
                print(f"[SUCCESS] Successfully wrote to file {file_name}")
            except Exception as e:
                self.chat_session.add_message(yaml.dump({
                    "file": file_name,
                    "success": False,
                    "error": str(e),
                }), "user")
                print(f"[ERROR] Failed to write to the file: {e}")
        elif type == "complete":
            print(f"[COMPLETE] {command['message']}")
            return True
        else:
            print(f"[ERROR] Unknown command type: {command['type']}")
        return False

    @staticmethod
    def parse_message(message):
        try:
            return yaml.safe_load(message)
        except yaml.YAMLError as e:
            #print(f"[PARSE ERROR] Couldn't parse agent's message: {message}", e)
            return None

    def convert_message_for_subagent(self, message):
        #print('convert_message_for_subagent', message)
        msg = Agent.parse_message(message['content'])
        if msg is None or msg['type'] == 'parse_error':
            return None
        if message['role'] == 'system' and msg['type'] == 'task':
            return {
                'role': 'assistant',
                'content': yaml.dump({
                    'type': 'assign',
                    'task': msg['task'],
                    'id': self.name
                })
            }
        return message

    def convert_history_for_subagent(self):
        agent_history = self.chat_session.messages[1:-1]
        agent_history = [self.convert_message_for_subagent(h) for h in agent_history]
        return [h for h in agent_history if h is not None]

    async def handle_agent_assign(self, command):
        sub_agent_id=command['id']
        task=command['task']
        print(f"[ASSIGN] {sub_agent_id} {task}")
        await self.send_update()
        sub_chat_session = ChatSession(self.chat_session.model, getSystemPrompt('subagent'))
        sub_chat_session.messages += self.convert_history_for_subagent()#self.chat_session.messages[1:-1]
        sub_chat_session.add_message(yaml.dump({
            "type": "task",
            "instructions": f"You are now the Agent '{sub_agent_id}'. Complete your task.",
            "supervisor_path": self.supervisor_path + [self.name],
            "date": datetime.datetime.now(),
            'task': task
        }), "system")
        sub_agent = Agent(sub_chat_session, web_server=self.web_server, name=sub_agent_id, parent=self)
        await sub_agent.run()
        last_msg = sub_chat_session.messages[-1].content
        last_msg_parsed = Agent.parse_message(last_msg)
        print(f"[ASSIGN] {sub_agent_id} {task} completed: {last_msg_parsed}")
        self.chat_session.add_message(yaml.dump({
            "type": "completed",
            "id": sub_agent_id,
            "message": last_msg_parsed['message'] if last_msg_parsed is not None else last_msg,
            "status": last_msg_parsed['status'] if last_msg_parsed is not None else 'success'
        }))


    def handle_agent_process(self, command):
        try:
            subprocess_result = subprocess.run(command, shell=True, capture_output=True, text=True)
            return_code = subprocess_result.returncode
            if return_code == 0:
                self.chat_session.add_message(yaml.dump({
                    "stdout": subprocess_result.stdout
                }), "system")
                print(f"[OUTPUT] {subprocess_result.stdout}")
            else:
                self.chat_session.add_message(yaml.dump({
                    "stderr": subprocess_result.stderr
                }), "system")
                print(f"[ERROR] Command returned exit code {return_code}\n{subprocess_result.stderr}")
        except Exception as e:
            print(f"[ERROR] Failed to run the command: {e}")


async def execute_chat(chat_session, web_server):
    main_task = await web_server.get_input({
        'state': 'request',
        'id': 'main',
        'message': "Main task"
    })
    print(f"Main task: {main_task}")
    chat_session.add_message(yaml.dump({
        "type": "main_task",
        "task": main_task
    }))
    agent = Agent(chat_session, web_server=web_server)
    await agent.run()
    await web_server.send_state({
        'state': 'completed'
    })
    print("Completed")


async def main(args):
    chat_session = ChatSession(args.model, getSystemPrompt())
    web_server = WebServer()
    await asyncio.gather(
        web_server.run(),
        execute_chat(chat_session, web_server),
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Interact with the chat session using a CLI.")
    parser.add_argument("-m", "--model", default="gpt-4", help="Specify the model to use (default: gpt-4).")
    args = parser.parse_args()
    asyncio.run(main(args))
