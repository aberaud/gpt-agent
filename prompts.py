
import datetime
import os


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
