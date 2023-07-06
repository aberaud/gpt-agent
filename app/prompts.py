
import datetime
import os
from app.commands import commands

purpose_agent = """Analyze the goal, define a plan to achieve it, and delegate the required actions to other agents or perform them yourself, until the goal is achieved.
Always only use functions, and without introduction or explaination. Use functions directly and without any other text.
What you say will not be preserved, only the content provided to the 'COMPLETE' function will be used to judge or use your work.
Always use the 'COMPLETE' function directly to report completion of a task."""

#You are an autonomous agent whose objective is to achieve a provided goal.
# Analyze the goal, plan to acheive it, breaking it down into smaller specific tasks to assign to other agents, until the goal is achieved.
# Take time to think and inspect your environment before acting.

purpose_planner = """Your objective is to acheive a long-term goal.

"""

purpose_engineer = """You are a pragmatic software engineer.
"""

purpose_spec = """
You are a super smart developer. You have been asked to make a specification for a program.

Think step by step to make sure we get a high quality specification and we don't miss anything.
First, be super explicit about what the program should do, which features it should have
and give details about anything that might be unclear. **Don't leave anything unclear or undefined.**

Second, lay out the names of the core classes, functions, methods that will be necessary,
as well as a quick comment on their purpose.

This specification will be used later as the basis for the implementation.
"""

purpose_searcher = """Your objective is to find information by performing online searches and requesting other agents to analyze results."""


purpose_search = """Analyze the provided content, then directly use the 'COMPLETE' function to provide the requested information."""


purpose_subagent = """Your objective is to acheive a goal assigned to you, as part of a larger plan.
Complete the task yourself or break it down into smaller tasks to be solved by other agents.
Take time to think and inspect your environemnt before acting since other agents might have already done some work.
Always check the result of your work and the work of other agents.
After you complete, only your completion message and filesystem changes will be preserved.
Never report directly, instead use the 'COMPLETE' function to report completion of a task.
"""

purpose_single_agent = """You are an experienced engineer whose purpose is to achieve a provided goal.
Analyze the goal and, if required, break it down into smaller tasks to be solved, and use your own experience and the provided tools to acheive the goal.
Take time to think and inspect your environment before acting.
Always check the result of your work."""


AGENT_TYPES={
    'agent': {
        'prompt': [purpose_agent],
        'commands': '*'
    },
    'worker': {
        'prompt': [purpose_subagent],
        'commands': '*'
    },
    'search': {
        'prompt': [purpose_search],
        'commands': ['COMPLETE']
    },
    'searcher': {
        'prompt': [purpose_searcher],
        'commands': ['SEARCH', 'GET', 'COMPLETE']
    },
    'engineer': {
        'prompt': [purpose_engineer],
        'commands': ['WRITE', 'RUN', 'PYTHON', 'ASSIGN', 'REQUEST', 'COMPLETE']
    },
}


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

# def getSystemPrompt(name, path, type='agent'):
#     if type == 'search':
#         return [purpose_search]
#     elif type == 'searcher':
#         return [purpose_searcher]
#     return [purpose_agent if type == 'agent' else purpose_subagent,
#            f"""You are running in a Alpine Linux container, in your home directory.
# Use functions directly with no introduction. 
# Never report directly, instead use the 'COMPLETE' function to report completion of a task.
# """,f"""
# date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# name: {name}
# supervisor_path: {path}
# directory_content:\n{list_files(os.getcwd())}
# """]

def getSystemPrompt(name, path, type='agent'):
    agent_type = AGENT_TYPES[type]
    return agent_type['prompt']

def getCommands(type='agent'):
    agent_type = AGENT_TYPES[type]
    if agent_type['commands'] == '*':
        return commands
    else:
        return [cmd for cmd in commands if cmd['name'] in agent_type['commands']]
