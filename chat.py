from typing import Optional
import os
from dotenv import load_dotenv
import openai
load_dotenv()
openai.organization = os.getenv("OPENAI_ORG_ID")
openai.api_key = os.getenv("OPENAI_API_KEY")

class ChatSession:
    def __init__(self, model: str='gpt-4', system_prompt: Optional[str | list[str]]=None):
        self.model = model
        self.messages = []
        if system_prompt:
            if isinstance(system_prompt, list):
                for prompt in system_prompt:
                    self.messages.append({"role": "system", "content": prompt})
            else:
                self.messages.append({"role": "system", "content": system_prompt})
    
    async def chat(self, message: Optional[str] = None, role: str = "user"):
        if message:
            self.add_message(message, role)
        retry = 3
        while retry > 0:
            try:
                response = await openai.ChatCompletion.acreate(
                    model=self.model,
                    messages=self.messages,
                    max_tokens=1000,
                )
                rmsg = response.choices[0].message
                self.messages.append(rmsg)
                return rmsg.content
            except openai.OpenAIError as e:
                print("Error: OpenAI API Error", e)
                retry -= 1
        if retry == 0:
            raise e

    def add_message(self, message: str, role: str = "user"):
        self.messages.append({"role": role, "content": message})


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
    parser.add_argument("-m", "--model", default="gpt-4", help="Specify the model to use (default: gpt-4).")
    parser.add_argument("-sp", "--system-prompt", help="Optional system prompt to start the conversation.")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_chat(args))

