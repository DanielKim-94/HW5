"""HTTP-to-MCP integration tests on disposable databases, with no live AI."""
import asyncio
from contextlib import closing
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import get_args
import unittest

from fastmcp import FastMCP, Client
import httpx
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from .agents import ShopTeam
from .config import HW_ROOT
from .main import create_app
from .models import ShopTool

logging.getLogger('fastmcp').setLevel(logging.CRITICAL)
spec = importlib.util.spec_from_file_location('api_operations_fixture', HW_ROOT / 'mcp_server/operations.py')
operations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operations)


class DashboardAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.original = self.directory / 'campus_customs.db'
        self.db = self.directory / 'campus_customs_new.db'
        shutil.copy2(HW_ROOT / 'data/campus_customs.db', self.original)
        shutil.copy2(self.original, self.db)
        self.original_hash = hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.old_secret = os.environ.get('CAMPUS_HUMAN_APPROVAL_SECRET')
        os.environ['CAMPUS_HUMAN_APPROVAL_SECRET'] = 'api-fixture-human-capability'
        server = FastMCP('API fixture')
        operations.register_operations(server, self.db)
        self.fake_handler = None

        def fake_model(messages, info):
            if self.fake_handler:
                return self.fake_handler(messages, info)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                {'ticket_id': 101, 'agent': 'Boss', 'summary': 'Offline API run', 'status': 'blocked'})])

        directory = self.directory
        class FixtureTeam(ShopTeam):
            def __init__(self):
                super().__init__(root=HW_ROOT, model=FunctionModel(fake_model), audit_path=directory / 'audit.json')
                self._human_capability = 'api-fixture-human-capability'
            async def __aenter__(self):
                self.client = Client(server)
                await self.client.__aenter__()
                return self

        self.token = 'offline-human-token-' + 'x' * 32
        self.app = create_app(team_factory=FixtureTeam, token=self.token)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.auth = {'Authorization': 'Bearer ' + self.token}

    async def asyncTearDown(self):
        await self.http.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), self.original_hash)
        if self.old_secret is None:
            os.environ.pop('CAMPUS_HUMAN_APPROVAL_SECRET', None)
        else:
            os.environ['CAMPUS_HUMAN_APPROVAL_SECRET'] = self.old_secret
        self.temp.cleanup()

    def scalar(self, sql):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute(sql).fetchone()[0]

    async def prepare(self, ticket=101, kind='invoice', ref_id=501):
        response = await self.http.post(f'/tickets/{ticket}/payments/prepare', headers=self.auth,
                                        json={'kind': kind, 'ref_id': ref_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['approval_request']['id']

    async def approve(self, approval_id, ticket=101, request_type='payment', headers=None):
        return await self.http.post(f'/approvals/{approval_id}/approve', headers=self.auth if headers is None else headers,
                                    json={'ticket_id': ticket, 'request_type': request_type, 'human_name': 'Fixture Human', 'approve': True})

    async def test_read_routes_and_human_auth(self):
        self.assertEqual((await self.http.post('/session/verify')).status_code, 401)
        self.assertEqual((await self.http.post('/session/verify', headers=self.auth)).json(), {'authorized': True})
        preflight = await self.http.options('/tickets', headers={'Origin': 'http://localhost:5174', 'Access-Control-Request-Method': 'GET'})
        self.assertEqual(preflight.headers.get('access-control-allow-origin'), 'http://localhost:5174')
        tickets = (await self.http.get('/tickets')).json()
        self.assertEqual([t['id'] for t in tickets['tickets']], [101,102,103])
        self.assertEqual((await self.http.get('/cash')).json()['account']['balance'], 3400)
        self.assertEqual((await self.http.get('/tickets/999')).status_code, 404)
        response = await self.http.post('/tickets/101/payments/prepare', json={'kind': 'invoice', 'ref_id': 501})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.scalar('SELECT count(*) FROM payment_approvals'), 0)
        self.assertNotIn('approve_and_execute_payment', get_args(ShopTool))
        self.assertNotIn('approve_and_execute_purchase', get_args(ShopTool))
        self.assertNotIn('record_human_payment_decision', get_args(ShopTool))

    async def test_prepare_approve_replay_and_wrong_ticket(self):
        approval_id = await self.prepare()
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)
        self.assertEqual((await self.approve(approval_id, headers={})).status_code, 401)
        self.assertEqual((await self.approve(approval_id, ticket=102)).status_code, 404)
        first = await self.approve(approval_id)
        self.assertEqual(first.status_code, 200, first.text)
        replay = await self.approve(approval_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()['already_executed'])
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 1)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 2560)

    async def test_cash_changed_atomic_rollback_and_stale_amount(self):
        approval_id = await self.prepare()
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE cash_accounts SET balance=100')
            c.commit()
        failure = await self.approve(approval_id)
        self.assertEqual(failure.status_code, 409)
        self.assertEqual(self.scalar('SELECT status FROM payment_approvals'), 'pending')
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)

    async def test_stale_payment_and_denial(self):
        approval_id = await self.prepare()
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE invoices SET amount=850')
            c.commit()
        self.assertEqual((await self.approve(approval_id)).status_code, 409)
        self.assertEqual(self.scalar('SELECT status FROM payment_approvals'), 'pending')
        denied = await self.http.post(f'/approvals/{approval_id}/deny', headers=self.auth,
                                     json={'ticket_id':101, 'request_type':'payment', 'human_name':'Fixture Human'})
        self.assertEqual(denied.status_code, 200)
        self.assertEqual((await self.approve(approval_id)).status_code, 409)
        replacement = await self.prepare()
        self.assertNotEqual(replacement, approval_id)

    async def test_purchase_block_cash_out_and_idempotency(self):
        response = await self.http.post('/tickets/103/purchases/prepare', headers=self.auth,
            json={'vendor_id':1, 'qty':12, 'supplier_evidence':'Fixture-only human supplied supplier confirmation'})
        self.assertEqual(response.status_code, 200, response.text)
        purchase_id = response.json()['approval_request']['id']
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400)
        blocked = await self.approve(purchase_id, ticket=103, request_type='purchase')
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(self.scalar('SELECT status FROM purchase_approvals'), 'pending')
        invoice_request = await self.prepare()
        self.assertEqual((await self.approve(invoice_request)).status_code, 200)
        purchased = await self.approve(purchase_id, ticket=103, request_type='purchase')
        self.assertEqual(purchased.status_code, 200, purchased.text)
        replay = await self.approve(purchase_id, ticket=103, request_type='purchase')
        self.assertTrue(replay.json()['already_executed'])
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 2296)
        self.assertEqual(self.scalar('SELECT count(*) FROM purchases'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 2)
        self.assertEqual(self.scalar("SELECT qty FROM inventory WHERE sku='CC-HOOD-NAVY' AND size='M'"), 8)
        self.assertEqual(purchased.json()['purchase']['earliest_arrival'], '2026-09-05')

    async def test_run_activity_and_reset_history(self):
        run = await self.http.post('/tickets/101/run', headers=self.auth, json={'task':'Offline API test only'})
        self.assertEqual(run.status_code, 202, run.text)
        run_id = run.json()['run_id']
        for _ in range(100):
            result = (await self.http.get('/runs/' + run_id)).json()
            if result['status'] in ('completed','failed'):
                break
            await asyncio.sleep(.01)
        self.assertEqual(result['status'], 'completed', result)
        before = (await self.http.get('/activity', params={'run_id':run_id})).json()['entries']
        self.assertIn('agent_completed', [entry['event'] for entry in before])
        cursor = before[0]['sequence']
        page = (await self.http.get('/activity', params={'after_sequence':cursor, 'limit':2})).json()
        self.assertEqual(len(page['entries']), 2)
        approval_id = await self.prepare()
        self.assertEqual((await self.approve(approval_id)).status_code, 200)
        self.assertEqual((await self.http.post('/reset', json={'confirmation':'RESET_WORKING_DATABASE'})).status_code, 401)
        reset = await self.http.post('/reset', headers=self.auth, json={'confirmation':'RESET_WORKING_DATABASE'})
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM payment_approvals'), 0)
        after = (await self.http.get('/activity', params={'run_id':run_id})).json()['entries']
        self.assertEqual(before, after)

    async def test_pending_approval_stops_before_another_model_call(self):
        calls = []
        def prepare_model(messages, info):
            calls.append(1)
            return ModelResponse(parts=[ToolCallPart('shop_tool', {'tool_name':'request_payment_approval',
                'arguments':{'ticket_id':102,'kind':'rent','ref_id':1,'reason':'Offline pause test'}})])
        self.fake_handler = prepare_model
        run = await self.http.post('/tickets/102/run', headers=self.auth, json={'task':'Prepare rent and pause'})
        self.assertEqual(run.status_code, 202, run.text)
        for _ in range(100):
            result = (await self.http.get('/runs/' + run.json()['run_id'])).json()
            if result['status'] in ('completed', 'failed'): break
            await asyncio.sleep(.01)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['result']['status'], 'awaiting_human')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payment_approvals'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400)

    async def test_progress_prepares_future_rent_and_recovers_run(self):
        self.fake_handler = lambda messages, info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'ticket_id':102,'agent':'Boss','summary':'No request prepared by model','status':'blocked'})])
        response = await self.http.post('/tickets/102/run', headers=self.auth, json={'task':'Prepare rent for human review'})
        run_id = response.json()['run_id']
        while self.app.state.active_job:
            await asyncio.sleep(0.01)
        approvals = (await self.http.get('/approvals')).json()['payments']
        self.assertEqual(len(approvals), 1)
        self.assertEqual(float(approvals[0]['amount']), 2400)
        self.assertEqual(self.scalar("SELECT balance FROM cash_accounts"), 3400)
        self.app.state.jobs.clear()
        recovered = (await self.http.get('/runs/'+run_id)).json()
        self.assertEqual(recovered['result']['status'], 'awaiting_human')
        self.assertEqual((await self.http.get('/runs')).json()['runs'][0]['run_id'], run_id)

    async def test_investigation_only_does_not_prepare(self):
        await self.http.post('/tickets/101/run', headers=self.auth, json={'task':'Investigate only', 'prepare_payments':False})
        while self.app.state.active_job:
            await asyncio.sleep(0.01)
        self.assertEqual((await self.http.get('/approvals')).json()['payments'], [])

    async def test_continuation_does_not_repay_invoice(self):
        approval = await self.prepare()
        self.assertEqual((await self.approve(approval)).status_code, 200)
        await self.http.post('/tickets/101/run', headers=self.auth, json={'task':'Continue after approved invoice; no receipt invented'})
        while self.app.state.active_job:
            await asyncio.sleep(.01)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payment_approvals'), 1)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 2560)
        self.assertEqual(self.scalar("SELECT status FROM tickets WHERE id=101"), 'open')

    async def test_decline_is_not_automatically_recreated(self):
        approval = await self.prepare()
        denied = await self.http.post('/approvals/'+approval+'/deny', headers=self.auth, json={'ticket_id':101,'request_type':'payment','human_name':'Fixture Human'})
        self.assertEqual(denied.status_code, 200)
        await self.http.post('/tickets/101/run', headers=self.auth, json={'task':'Continue after human decline'})
        while self.app.state.active_job:
            await asyncio.sleep(.01)
        self.assertEqual(self.scalar('SELECT count(*) FROM payment_approvals'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)

    async def test_business_resolution_routes_require_human_and_explicit_scope(self):
        payload={'kind':'pricing_decision','unit_price':'50.00','rationale':'Human proposed conditional quote'}
        self.assertEqual((await self.http.post('/tickets/103/resolution/prepare',json=payload)).status_code,401)
        prepared=await self.http.post('/tickets/103/resolution/prepare',headers=self.auth,json=payload)
        self.assertEqual(prepared.status_code,200,prepared.text)
        rid=prepared.json()['review']['id']
        self.assertEqual(self.scalar("SELECT status FROM tickets WHERE id=103"),'open')
        refusal=await self.http.post('/tickets/103/resolution/'+rid+'/decision',headers=self.auth,json={'approve':True,'human_name':'Fixture Human','acknowledge_completion_rule':False})
        self.assertEqual(refusal.status_code,422)
        result=await self.http.post('/tickets/103/resolution/'+rid+'/decision',headers=self.auth,json={'approve':True,'human_name':'Fixture Human','acknowledge_completion_rule':True})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['ticket']['status'],'resolved')
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'),3400)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'),0)
