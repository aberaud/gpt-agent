
import asyncio
import json
import subprocess

from app.search import search, get_wikipedia_data
from app.scrape import scrapeText
from app.chat import generate_image

class AgentParseError(Exception):
    pass

async def info_callback(agent, args):
    print(f"INFO: {args}")

async def search_callback(agent, args):
    print(f"QUERY: {args}")
    source = args.get('source')
    query = args['query']
    results = await search(query=query, source=source)
    print(f"RESULTS: {results}")
    return json.dumps(results, indent=2)
    # agent_id = f'search_agent_{query}'
    # result = await agent.handle_agent_assign(agent_id, args.get('request'), [json.dumps(results, indent=4)], role='search')
    # print(f"RESULT: {result}")
    # return result

async def get_callback(agent, args):
    print(f"GET: {args}")
    source = args.get('source')
    url = args['id']
    if source == 'web':
        results = await scrapeText(url)
    else: #elif source == 'wikipedia':
        results = await get_wikipedia_data(url)
    
    print(f"RESULTS: {results}")
    if results is None:
        return 'No results found.'
    result = await agent.handle_agent_assign('search_agent', args.get('request'), [results], role='search')
    print(f"RESULT: {result}")
    return result

async def draw_callback(agent, args):
    print(f"DRAW: {args}")
    prompt = args['description']
    image = await generate_image(prompt)
    print(f"IMAGE: {image}")
    return image

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
    if agent.name == 'main' and agent.web_server:
        await agent.get_human_input("Evaluate the agent's performance and provide feedback.", reply_type="evaluation")
    else:
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
        "name": "DRAW",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A detailed, graphic description of the image to generate, in English"
                },
            },
            "required": ["description"],
        },
        "description": "Generate an image from a prompt. The prompt should be a detailed, graphic description of the image to generate, in English. The resulting image will be displayed to the user instead of the result you will see. Never repeat the url, and don't link to the result.",
        "callback": draw_callback,
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
                "role": {
                    "type": "string",
                    "description": "The role of the agent. Can be 'searcher', 'engineer' or 'worker' (the default)."
                },
                "content": {
                    "type": "string",
                    "description": "A complete description of the task to assign to the agent. Note that the agent won't have access to any other information or context about the task."
                }
            },
            "required": ["agent_id", "content"],
        },
        "description": "Assign a task to another independent agent. Provide an id and a detailed description of the task including all required context for the agent, because the agent won't have access to any other information.",
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
        "name": "SEARCH",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "The source to query ('wikipedia' or 'google')",
                },
                "query": {
                    "type": "string",
                    "description": "The query to send to the source",
                },
                "request": {
                    "type": "string",
                    "description": "The information to extract from the result. This is a prompt that will be provided to the search agent with the result.",
                }
            },
            "required": ["source", "content", "request"],
        },
        "description": "Search for information online and get a list of results.",
        "example": "QUERY google\nParis",
        "callback": search_callback,
    },
    {
        "name": "GET",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "The source to get the url from ('web' or 'wikipedia')",
                },
                "id": {
                    "type": "string",
                    "description": "The identifier of the content to get (url or wikipedia page name)",
                },
                "request": {
                    "type": "string",
                    "description": "The information to extract from the result. This is a prompt that will be provided to the search agent with the result",
                }
            },
            "required": ["source", "id", "request"],
        },
        "description": "Get information from a specific piece of content online, like any webpage or wikipedia page. The result is provided to the search agent with the request as a prompt",
        "callback": get_callback,
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
                    "description": "The message to send to the supervisor. This should include all relevant information to evaluate the task completion.",
                }
            },
            "required": ["status", "content"],
        },
        "description": "Notify task completion (either success or failure), providing your supervisor with a corresponding 'completed' message. Provide all relevent information about what you did in the message, because your supervisor won't have access to any other message you wrote. If you are stuck in a loop, complete with failure.",
        "callback": complete_callback
    }
]

def getCommands(role: str):
    if role == 'agent':
        return [cmd for cmd in commands if not 'properties' in cmd or 'assign' in cmd['properties']]
    elif role == 'subagent':
        return commands
