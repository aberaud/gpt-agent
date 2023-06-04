from typing import Optional
import openai


class ChatSession:
    def __init__(self, model: str='gpt-4', system_prompt: Optional[str]=None):
        self.model = model
        self.messages = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})
    
    async def chat(self, message: Optional[str] = None, role: str = "user"):
        if message:
            self.add_message(message, role)
        response = await openai.ChatCompletion.acreate(
            model=self.model,
            messages=self.messages,
            max_tokens=1000,
        )
        rmsg = response.choices[0].message
        #print(rmsg.content)
        self.messages.append(rmsg)
        return rmsg.content

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

