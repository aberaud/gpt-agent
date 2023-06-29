import asyncio
from datetime import datetime
import json
import os
import traceback
import uuid
from asyncio import CancelledError, Queue

from app.agent import Agent
from app.chat import get_total_usage, get_model_list
from app.web_server import WebServer, WebSession

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

class AgentRunner:
    def __init__(self, args, session: WebSession):
        self.args = args
        time = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.name = f"{time}-{uuid.uuid4().hex[:4]}"
        self.path = os.path.join(os.getcwd(), self.name)
        os.mkdir(self.path)
        self.session = session
        self.agents: dict[str, Agent] = {}
        self.main_agent = Agent(args, web_server=session, context=self)
        self.add_agent(self.main_agent)
        print(f"Created agent runner {self.name} in path {self.path}")
    
    async def run(self, main_goal: str | None = None):
        init_path = os.getcwd()
        os.chdir(self.path)
        try:
            await self.main_agent.init()
            if main_goal is None:
                await self.main_agent.get_human_input("Main goal", "main_goal")
            else:
                await self.main_agent.add_message(json.dumps({ "main_goal": main_goal }))
            await self.main_agent.run()
            await self.session.set_state(self.main_agent.name, 'completed', usage=get_total_usage())
        finally:
            os.chdir(init_path)

    def new_agent_id(self, proposed_name: str):
        if proposed_name in self.agents:
            i = 1
            while f"{proposed_name}_{i}" in self.agents:
                i += 1
            return f"{proposed_name}_{i}"
        return proposed_name
    
    def add_agent(self, agent: Agent):
        self.agents[agent.name] = agent

    async def stop(self):
        for agent in self.agents.values():
            await agent.stop()
        # delete the directory if it's empty
        if not os.listdir(self.path):
            os.rmdir(self.path)

    async def save_state(path: str):
        '''Save the state of the agent to a json file.'''


async def add_agent(args, session: WebSession):
    session.task = asyncio.create_task(execute_chat(args, session))
    await task_queue.put(session.task)
    

async def execute_chat(args, session: WebSession):
    await session.reset(args.model)

    context = AgentRunner(args, session)
    await session.set_agent(context)
    await session.set_property('models', await get_model_list())
    await session.set_property('usage', get_total_usage())
    await session.send_init_state()
    await context.run()
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
