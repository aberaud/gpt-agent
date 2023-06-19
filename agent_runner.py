import asyncio
import os
import shutil
import traceback
from chat import get_total_usage, get_model_list
from web_server import WebServer, Session
from asyncio import CancelledError, Queue
from agent import Agent

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
