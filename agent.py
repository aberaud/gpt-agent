import asyncio
import subprocess
import os
import yaml
from dotenv import load_dotenv
load_dotenv()
import openai
openai.organization = os.getenv("OPENAI_ORG_ID")
openai.api_key = os.getenv("OPENAI_API_KEY")

from chat import ChatSession
import datetime

import aiohttp
from aiohttp import web


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
  * Run a command and get the output:
      {"type": "command", "command": "ls -la"}
     or: 
      type: command
      command:
        - mkdir project
        - cd project
        - git init
  * Notify task completion:
      {"type": "complete", "message": "empty repo created"}
"""

system_prompt = """
purpose: You are an autonomous agent whose purpose is to solve a long-term task provided by a human supervisor.
  Your goal is to analyse the problem and break it down into smaller subtasks that can be solved by other agents,
  until the task is complete.
""" + system_prompt_syntax

system_prompt_subagent = """
purpose: You are an autonomous agent whose purpose is to help solving a long-term task provided by a human supervisor.
  Your goal is to complete a subtask provided to you by another agent.
  Analyse the main task and the subtask that you have been assigned,
  complete the subtask yourself or break it down into smaller subtasks that can be solved by other agents.
""" + system_prompt_syntax


async def agent(chat_session: ChatSession, name: str = "main"):
    print(f"Agent {name} ({chat_session.model}) started")
    while True:
        try:
            print(f"Agent {name} running...")
            response = await chat_session.chat()
            try:
                command = yaml.safe_load(response)
                task_complete = await handle_agent_command(command, chat_session)
                if task_complete:
                    break
            except yaml.YAMLError as e:
                print(f"[PARSE ERROR] Couldn't parse agent's message: {response}", e)
                chat_session.add_message(yaml.dump({
                    "type": "parse_error",
                    "message": str(e)
                }))
            except Exception as e:
                print(f"[ERROR] Couldn't handle agent's message: {response}", e)
                chat_session.add_message(yaml.dump({
                    "type": "error",
                    "message": str(e)
                }))
        except KeyboardInterrupt:
            print("\nExiting.")
            break
    print(f"Agent {name} ended")

async def handle_agent_command(command, chat_session):
    type = command["type"]
    if type == "info":
        print(f"[INFO] {command['message']}")
    elif type == "request":
        print(f"[REQUEST] {command['message']}")
        chat_session.add_message(yaml.dump({
            "reply": input("User: ")
        }))
    elif type == "assign":
        print(f"[ASSIGN] {command['id']} {command['task']}")
        sub_chat_session = ChatSession(chat_session.model, system_prompt_subagent)
        sub_chat_session.messages += chat_session.messages[1:]
        sub_chat_session.add_message(yaml.dump({
            'subtask': command['task']
        }))
        await agent(sub_chat_session, command['id'])
        last_msg = sub_chat_session.messages[-1].content
        #print(f"[COMPLETED] {last_msg}")
        chat_session.add_message(yaml.dump({
            "type": "completed",
            "id": command['id'],
            "message": last_msg
        }))
    elif type == "command": 
        shell_command = command['command']
        if isinstance(shell_command, list):
            for cmd in shell_command:
                print(f"[COMMAND] {cmd}")
                handle_agent_process(cmd, chat_session)
        elif isinstance(shell_command, str):
            print(f"[COMMAND] {shell_command}")
            handle_agent_process(shell_command, chat_session)

    elif type == "write":
        file_name = command['file']
        content = command['content']
        print(f"[WRITE] Writing to file {file_name} {content}")
        try:
            with open(file_name, 'w') as file:
                file.write(content)
            chat_session.add_message(yaml.dump({
                "file": file_name,
                "success": True
            }), "system")
            print(f"[SUCCESS] Successfully wrote to file {file_name}")
        except Exception as e:
            chat_session.add_message(yaml.dump({
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

def handle_agent_process(command, chat_session):
    try:
        subprocess_result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return_code = subprocess_result.returncode
        if return_code == 0:
            chat_session.add_message(yaml.dump({
                "stdout": subprocess_result.stdout
            }), "system")
            print(f"[OUTPUT] {subprocess_result.stdout}")
        else:
            chat_session.add_message(yaml.dump({
                "stderr": subprocess_result.stderr
            }), "system")
            print(f"[ERROR] Command returned exit code {return_code}\n{subprocess_result.stderr}")
    except Exception as e:
        print(f"[ERROR] Failed to run the command: {e}")


async def execute_chat(chat_session):
    chat_session.add_message('main_task: ' + input("Main task: "))
    await agent(chat_session)

connected_clients: set[web.WebSocketResponse] = set()
cached_result = None

async def send_to_client(socket: web.WebSocketResponse, input):
    try:
        await socket.send_json(input)
    except Exception as e:
        print(f'Error sending to client: {e}')

async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print(f'WebSocket connection with {request.remote} ({" ".join(request.headers["User-Agent"].split()[-2:])}) opened')

    # Send initial cached data
    if cached_result:
        await send_to_client(ws, *cached_result)
    connected_clients.add(ws)

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
        elif msg.type == aiohttp.WSMsgType.ERROR:
            print(f'WebSocket connection with {request.remote} closed with exception {ws.exception()}')
    connected_clients.remove(ws)
    print(f'WebSocket connection with {request.remote} closed')
    return ws

async def index(request):
    return web.FileResponse('/app/index.html')

async def main(args):
    chat_session = ChatSession(args.model, system_prompt)

    app = web.Application()
    app.add_routes([web.get('/', index)])
    app.add_routes([web.get('/ws', websocket_handler)])

    await asyncio.gather(
        web._run_app(app),
        execute_chat(chat_session),
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Interact with the chat session using a CLI.")
    parser.add_argument("-m", "--model", default="gpt-4", help="Specify the model to use (default: gpt-4).")
    args = parser.parse_args()
    asyncio.run(main(args))
