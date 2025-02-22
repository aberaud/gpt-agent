import asyncio
import json
import os
import unittest
import aiounittest

from .agent_runner import AgentRunner

class dotdict(dict):
  """dot.notation access to dictionary attributes"""
  def __getattr__(*args):
     val = dict.get(*args)
     return dotdict(val) if type(val) is dict else val
  __setattr__ = dict.__setitem__
  __delattr__ = dict.__delitem__


class TestAgent(aiounittest.AsyncTestCase):

    def check_complete(self, context: AgentRunner, expected: str | None = None):
        last_message = context.main_agent.chat_session.last_message()
        self.assertIsNotNone(last_message)
        print(last_message)
        function_call = last_message.get('function_call')
        self.assertIsNotNone(function_call)
        arguments = function_call.get('arguments')
        self.assertIsNotNone(arguments)
        parsed = json.loads(arguments)
        if expected is not None:
            self.assertEqual(parsed['content'], expected)

    async def test_hello_world(self):
        args = dotdict({'model': 'gpt-4o'})
        context = AgentRunner(args)
        await context.run("complete with message 'hello world'")
        self.check_complete(context, 'hello world')
    
    async def test_create_directory(self):
        args = dotdict({'model': 'gpt-4o'})
        context = AgentRunner(args)
        await context.run("create empty directory 'test'")
        self.check_complete(context)
        test_path = os.path.join(context.path, 'test')
        self.assertTrue(os.path.exists(test_path))
        self.assertTrue(os.path.isdir(test_path))
        os.rmdir(test_path)
        os.rmdir(context.path)

    async def test_simple_script(self):
        args = dotdict({'model': 'gpt-4o'})
        context = AgentRunner(args)
        await context.run("create a simple python script 'test.py' that just prints 'hello world'")
        self.check_complete(context)
        test_script = os.path.join(context.path, 'test.py')
        self.assertTrue(os.path.exists(test_script))
        self.assertTrue(os.path.isfile(test_script))
        process = await asyncio.create_subprocess_exec('python3', test_script, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()    
        return_code = process.returncode
        process = None
        self.assertEqual(return_code, 0)
        self.assertEqual(stdout.decode().strip().lower(), 'hello world')
        os.remove(test_script)
        os.rmdir(context.path)

if __name__ == '__main__':
    unittest.main()
