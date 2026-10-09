"""Verify outbound model/settings and fail-closed response handling without live AI."""
import json
import os
import unittest
from unittest.mock import patch

import httpx
from pydantic_ai import Agent

from .config import MODEL_NAME, create_model, model_matches


class ModelRouting(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, reported, *, tool_call=False):
        evidence=[]; requests=[]; actions=[]
        with patch.dict(os.environ, {'PORTKEY_API_KEY':'offline-fixture-key'}):
            model,client=create_model(lambda event,result:evidence.append((event,result)))
        def handler(request):
            body=json.loads(request.content); requests.append(body)
            message={'role':'assistant','content':'verified'}
            if tool_call:
                message={'role':'assistant','content':None,'tool_calls':[{'id':'fixture-call','type':'function',
                    'function':{'name':'touch_shop','arguments':'{}'}}]}
            data={'id':'fixture-response','object':'chat.completion','created':1791519990,
                'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if tool_call else 'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
            if reported is not None: data['model']=reported
            return httpx.Response(200,json=data,headers={'x-portkey-provider':'azure-openai',
                'x-portkey-last-used-option-index':'config.targets[2]','x-request-id':'fixture-http-request'})
        client._client._transport=httpx.MockTransport(handler)
        agent=Agent(model,output_type=str)
        @agent.tool_plain
        def touch_shop():
            actions.append(1)
            return 'Fixture should never execute when model is wrong'
        try:
            if model_matches(reported):
                result=await agent.run('Offline metadata test')
                self.assertEqual(result.output,'verified')
            else:
                with self.assertRaisesRegex(RuntimeError, 'Portkey model mismatch'): await agent.run('Offline metadata test')
            self.assertEqual(len(requests),1)
            self.assertEqual(requests[0]['model'],MODEL_NAME)
            self.assertEqual(requests[0]['reasoning_effort'],'none')
            self.assertEqual(actions,[])
            self.assertEqual(evidence[-1][1]['model_matches'],model_matches(reported))
            self.assertNotIn('api_key',json.dumps(evidence))
        finally: await client.close()

    async def test_correct_snapshot_and_settings(self):
        await self.exercise('gpt-6-luna-2026-09-22')

    async def test_wrong_model_rejected_before_tool_execution(self):
        await self.exercise('gpt-5.6-luna-2026-07-09',tool_call=True)

    async def test_missing_metadata_rejected(self):
        await self.exercise(None,tool_call=True)

    def test_only_exact_model_or_dated_snapshot(self):
        self.assertTrue(model_matches('gpt-6-luna'))
        self.assertFalse(model_matches('gpt-6.1-luna'))
        self.assertFalse(model_matches('gpt-6-luna-other'))


if __name__=='__main__': unittest.main()
