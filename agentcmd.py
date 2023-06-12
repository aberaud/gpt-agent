
class ParseError(BaseException):
    """The command could not be parsed."""

class CommandParser:
    def __init__(self, commands: list[dict]):
        self.commands = {}
        for commands in commands:
            self.register_command(commands)

    def register_command(self, command: dict):
        self.commands[command['name']] = command


    @staticmethod
    def parse_syntax(input_str):
        parsed_commands = []
        lines = input_str.split("\n")
        while lines:
            line = lines.pop(0)
            command_parts = line.split(maxsplit=1)
            if command_parts:
                command_name, args = command_parts[0], command_parts[1:]
                content = None
                if lines:
                    if lines[0]:
                        content = "\n".join(lines)
                        lines = []
                    else:
                        lines.pop(0)

                parsed_commands.append({
                    "command": command_name,
                    "args": args[0].split() if args else [],
                    "content": content
                })

        return parsed_commands

    def handle_commands(self, parsed_commands):
        handled_commands = []
        for parsed_command in parsed_commands:
            command_name = parsed_command["command"]
            if command_name not in self.commands:
                raise ParseError(f"Unrecognized command: {command_name}")

            command = self.commands[command_name]
            args = parsed_command["args"]
            if len(args) != len(command["args"]):
                raise ParseError(f"Invalid number of arguments for command: {command_name}")

            handled_commands.append({
                "command": command,
                "args": dict(zip(command["args"], args)),
                "content": parsed_command["content"]
            })

        return handled_commands

    def parse(self, input_str):
        parsed_commands = self.parse_syntax(input_str)
        return self.handle_commands(parsed_commands)
    
    def generate_documentation(self)-> str:
        documentation = []
        for command_name, command_info in self.commands.items():
            arglist = command_info['args']
            args = "".join((f' <{a}>' for a in arglist))
            command = f"{command_name}{args}"
            body = ''
            if command_info.get("has_content", True):
                body = f' (with content starting next line)'
            documentation.append(f"* {command_info['description']}: `{command}`{body}. For instance:")
            documentation.append(f"{command_info['example']}\n")
        return "\n".join(documentation)


if __name__ == "__main__":
    # Usage example
    def write_callback(args, content):
        print(f"Writing to {args['filename']} with content:\n{content}")
    def read_callback(args):
        print(f"Reading {args['filename']}")

    parser = CommandParser([
        {
            "name": "WRITE",
            "args": ["filename"],
            "callback": write_callback,
            "has_content": True,
            "description": "Write text to a file",
            "example": '''WRITE dir/file.txt
file content
can be multiline'''
        },
        {
            "name": "READ",
            "args": ["filename"],
            "callback": read_callback,
            "has_content": False,
            "description": "Read text from a file",
            "example": '''READ dir/file.txt'''
        }
    ])

    print(parser.generate_documentation())

    input_str = '''WRITE file.txt
this is some
multiline file content

READ file.txt'''

    parser.parse(input_str)
