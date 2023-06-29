import json
import os
import unittest
import aiounittest

from app.agent_runner import AgentRunner

class TestAgent(aiounittest.AsyncTestCase):

    async def test_hello_world(self):
        args = {'model': 'gpt-3.5-turbo-16k-0613'}
        context = AgentRunner(args)
        await context.run("complete with message 'hello world'")
        last_message = context.main_agent.chat_session.last_message()
        self.assertIsNotNone(last_message)
        print(last_message)
        function_call = last_message.get('function_call')
        self.assertIsNotNone(function_call)
        arguments = function_call.get('arguments')
        self.assertIsNotNone(arguments)
        parsed = json.loads(arguments)
        self.assertEqual(parsed['content'], 'hello world')
    

    async def test_create_directory(self):
        args = {'model': 'gpt-3.5-turbo-16k-0613'}
        context = AgentRunner(args)
        await context.run("create empty directory 'test'")
        last_message = context.main_agent.chat_session.last_message()
        self.assertIsNotNone(last_message)
        print(last_message)
        function_call = last_message.get('function_call')
        self.assertIsNotNone(function_call)
        test_path = os.path.join(context.path, 'test')
        self.assertTrue(os.path.exists(test_path))
        self.assertTrue(os.path.isdir(test_path))
        os.rmdir(test_path)
        os.rmdir(context.path)


if __name__ == '__main__':
    unittest.main()
