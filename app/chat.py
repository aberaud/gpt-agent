from typing import Optional
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
import openai

aclient = AsyncOpenAI()
from openai import AsyncOpenAI
from openai.types import CompletionUsage, ImagesResponse
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall, ChatCompletion

aclient = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
load_dotenv()
# TODO: The 'openai.organization' option isn't read in the client API. You will need to pass it when you instantiate the client, e.g. 'OpenAI(organization=os.getenv("OPENAI_ORG_ID"))'
# openai.organization = os.getenv("OPENAI_ORG_ID")

def get_price(model: str, usage: dict) -> float:
    PRICE_PER_MTOKEN_PROMPT = .03 if model.startswith('gpt-4') else 2.
    PRICE_PER_MTOKEN_COMPLETION = .06 if model.startswith('gpt-4') else 2.
    return (usage['prompt_tokens'] * PRICE_PER_MTOKEN_PROMPT + usage['completion_tokens'] * PRICE_PER_MTOKEN_COMPLETION) / 1000000.

total_usage = {}
models = None

def get_total_usage():
    tot_usage = {
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'total_tokens': 0,
        'total_dollars': 0,
    }
    for usage in total_usage.values():
        for key, value in usage.items():
            tot_usage[key] += value
    return tot_usage

async def get_model_list():
    global models
    if models is None:
        m = await aclient.models.list()
        models = sorted([model.id for model in m.data if model.id.startswith('gpt')], reverse=True)
    return models

async def generate_image(prompt: str):
    print('Generate image:', prompt)
    response: ImagesResponse = await aclient.images.generate(prompt=prompt,
        n=1,
        size="1024x1024")
    print(response)
    return response.data[0].url

class ChatSession:
    def __init__(self, model: str='gpt-4o', system_prompt: Optional[str | list[str]]=None, functions: dict={}):
        self.model = model
        self.messages: list[dict] = []
        self.functions = [{
            'name': c['name'], 
            'description': c['description'],
            'parameters': c['parameters']
        } for c in functions.values()]
        self.usage = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        }
        if system_prompt:
            if isinstance(system_prompt, list):
                for prompt in system_prompt:
                    self.messages.append({"role": "system", "content": prompt})
            else:
                self.messages.append({"role": "system", "content": system_prompt})

    async def chat(self, message: Optional[str] = None, role: str = "user"):
        print('Chat:', message)
        if message:
            self.add_message(message, role)
        retry = 3
        while retry:
            try:
                if self.functions:
                    response: ChatCompletion = await aclient.chat.completions.create(model=self.model,
                        messages=self.messages,
                        functions=self.functions,
                        max_tokens=1000)
                else:
                    response: ChatCompletion = await aclient.chat.completions.create(model=self.model,
                        messages=self.messages,
                        max_tokens=1000)
                print('Chat: await aclient.chat.completions END', response)

                usage: CompletionUsage = response.usage
                print(usage)
                mtot = total_usage.setdefault(self.model, {})
                for key in self.usage.keys():
                    #print(key, val)
                    #self.usage[key] += usage[key]
                    val = getattr(usage, key)
                    self.usage[key] += val
                    mtot[key] = mtot.get(key, 0) + val
                    #mtot['total_tokens'] = mtot.get('total_tokens', 0) + usage['total_tokens']
                    #mtot[key] = mtot.get(key, 0) + usage[key]
                mtot['total_dollars'] = get_price(self.model, mtot)
                print('Total:', total_usage)

                rmsg = response.choices[0].message
                dmsg = {
                    'role': rmsg.role,
                    'content': rmsg.content,
                    #'function': rmsg.tool_calls
                }
                if rmsg.function_call:
                    print('Function call:', rmsg.function_call)
                    dmsg['function_call'] = {
                        'name': rmsg.function_call.name,
                        'arguments': rmsg.function_call.arguments
                    }
                self.messages.append(dmsg)
                return dmsg
            except openai.OpenAIError as e:
                print("Error: OpenAI API Error", e)
                retry -= 1
                if retry == 0:
                    raise e

    def add_message(self, message: str, role: str = "user", name: Optional[str] = None) -> dict:
        if name:
            msg = {"role": role, "content": message, "name": name}
        else:
            msg = {"role": role, "content": message}
        self.messages.append(msg)
        return msg

    def last_message(self):
        return self.messages[-1]


async def start_chat(args):
    chat_session = ChatSession(args.model, args.system_prompt)

    print(f"{args.model} model loaded.")
    if args.system_prompt:
        print(f"System prompt: {args.system_prompt}\n")

    while True:
        try:
            user_input = input("User: ")
            if user_input.lower().strip() in ["quit", "exit"]:
                break

            response = await chat_session.chat(user_input, "user")
            print(f"{chat_session.model}: {response}")

        except KeyboardInterrupt:
            print("\nExiting.")
            break

if __name__ == "__main__":
    import asyncio
    import argparse
    parser = argparse.ArgumentParser(description="Interact with the chat session using a CLI.")
    parser.add_argument("-m", "--model", default="gpt-4o", help="Specify the model to use.")
    parser.add_argument("-sp", "--system-prompt", help="Optional system prompt to start the conversation.")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_chat(args))
