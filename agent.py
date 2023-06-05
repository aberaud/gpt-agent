import asyncio
import subprocess
import datetime
import yaml
from chat import ChatSession
from web_server import WebServer

system_prompt_syntax = f'date: "{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"' + """
instructions: |
  Always communicate in valid YAML format, directly and without any other introduction, comment or text.
  Always only output a single action to take (you will have the opportunity for more actions later), one of:
  * Note information for future reference:
      {"type": "info", "message": "this is some information"}
    or:
      type: info
      message: |
        this is some
        multiline information
  * Write to a file:
      type: write
      file: file.txt
      content: |
        this is some 
        multiline file content
  * Ask for more information to the human supervisor:
      {"type": "request", "message": "should we use rust or go?"}
  * Assign a subtask to another agent. Provide a detailed description of the task and an id.
      {"type": "assign", "id": "create", "task": "create the initial project structure"}
  * Run one or more bash commands and get the output:
      {"type": "command", "command": "ls -la"}
     or: 
      type: command
      command:
        - mkdir project
        - cd project
        - git init
  * Notify task completion. The parent agent will be provided a corresponding 'completed' message.
      {"type": "complete", "message": "empty repo created"}
"""

system_prompt = """
purpose: You are an autonomous agent whose purpose is to solve a long-term task provided by a human supervisor.
  Your goal is to analyse the problem and break it down into smaller subtasks that can be solved by other agents,
  until the task is complete.
""" + system_prompt_syntax

system_prompt_subagent = """
purpose: You are an autonomous agent whose purpose is to help solving a long-term goal provided by a human supervisor.
  Your objective is to complete a task provided to you by another agent.
  Analyse the long-term goal and the task that you have been assigned,
  complete the task yourself or break it down into smaller tasks that can be solved by other agents.
""" + system_prompt_syntax

class Agent:
    def __init__(self, chat_session: ChatSession, web_server: WebServer, name: str = "main"):
        self.chat_session = chat_session
        self.name = name
        self.web_server = web_server
        print(f"Agent {name} ({chat_session.model}) created")

    async def send_update(self):
        if self.web_server:
            await self.web_server.send_state({
                'state': 'running',
                'agents': [{
                    'id': self.name,
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
                        "message": str(e)
                    }), "system")
                except Exception as e:
                    print(f"[ERROR] Couldn't handle agent's message: {response}", e)
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
            print(f"[REQUEST] {command['message']}")
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
            sub_agent_id=command['id']
            print(f"[ASSIGN] {sub_agent_id} {command['task']}")
            await self.send_update()
            sub_chat_session = ChatSession(self.chat_session.model, system_prompt_subagent)
            sub_chat_session.messages += self.chat_session.messages[1:-1]
            sub_chat_session.add_message(yaml.dump({
                "instructions": f"You are now {sub_agent_id}. Complete your task.",
                #"date": datetime.datetime.now(),
                'task': command['task']
            }), "system")
            sub_agent = Agent(sub_chat_session, web_server=self.web_server, name=sub_agent_id)
            await sub_agent.run()
            last_msg = sub_chat_session.messages[-1].content
            try:
                last_msg_parsed = yaml.safe_load(last_msg)
                print(f"[ASSIGN] {command['id']} {command['task']} completed: {last_msg_parsed}")
                self.chat_session.add_message(yaml.dump({
                    "type": "completed",
                    "id": command['id'],
                    "message": last_msg_parsed['message']
                }))
            except yaml.YAMLError as e:
                print(e)
                self.chat_session.add_message(yaml.dump({
                    "type": "completed",
                    "id": command['id'],
                    "message": last_msg
                }))

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
                }), "system")
                print(f"[SUCCESS] Successfully wrote to file {file_name}")
            except Exception as e:
                self.chat_session.add_message(yaml.dump({
                    "file": file_name,
                    "success": False,
                    "error": str(e),
                }), "system")
                print(f"[ERROR] Failed to write to the file: {e}")
        elif type == "complete":
            print(f"[COMPLETE] {command['message']}")
            return True
        else:
            print(f"[ERROR] Unknown command type: {command['type']}")
        return False

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
    chat_session = ChatSession(args.model, system_prompt)
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
