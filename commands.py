
import asyncio
import pprint
import subprocess
from search import search

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
        "callback": write_callback,
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
        "description": "Ask for more information to a supervisor (human or agent) - don't assign tasks or report status with this function.",
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
        "callback": assign_callback,
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
        "callback": run_callback,
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
        "callback": python_callback,
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
        "properties": ['read']
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

def getCommands(role: str):
    if role == 'agent':
        return [cmd for cmd in commands if not 'properties' in cmd or 'assign' in cmd['properties']]
    elif role == 'subagent':
        return commands
