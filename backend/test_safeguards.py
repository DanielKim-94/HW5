"""Offline integration checks on disposable SQLite copies; no live AI or payments."""
import asyncio
from contextlib import closing
import logging
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastmcp import FastMCP, Client
from fastmcp.exceptions import ToolError
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from .agents import ShopTeam
from .audit import AuditTrail
from .config import HW_ROOT
from .models import AgentDeps, AgentRole, HumanDecision, RunLimits, SharedRun
from .tools import delegate, shop_tool
from pydantic_ai import ModelRetry
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('campus_operations_test', HW_ROOT / 'mcp_server/operations.py')
operations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operations)


logging.getLogger('fastmcp').setLevel(logging.CRITICAL)


class Safeguards(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.db = self.directory / 'shop.db'
        shutil.copy2(HW_ROOT / 'data/campus_customs.db', self.db)
        self.old_secret = os.environ.get('CAMPUS_HUMAN_APPROVAL_SECRET')
        os.environ['CAMPUS_HUMAN_APPROVAL_SECRET'] = 'offline-human-capability'
        server = FastMCP('Offline safeguard fixture')
        operations.register_operations(server, self.db)
        self.client = Client(server)
        await self.client.__aenter__()
        await self.call('initialize_shop_tools', human_capability='offline-human-capability')

    async def asyncTearDown(self):
        await self.client.__aexit__(None, None, None)
        if self.old_secret is None:
            os.environ.pop('CAMPUS_HUMAN_APPROVAL_SECRET', None)
        else:
            os.environ['CAMPUS_HUMAN_APPROVAL_SECRET'] = self.old_secret
        self.temp.cleanup()

    async def call(self, tool, **args):
        return (await self.client.call_tool(tool, args)).structured_content

    def scalar(self, sql):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute(sql).fetchone()[0]

    async def request(self, ticket=101, kind='invoice', ref=501):
        return (await self.call('request_payment_approval', ticket_id=ticket, kind=kind, ref_id=ref, reason='offline test'))['approval_request']['id']

    async def approve(self, ticket, request):
        return await self.call('record_human_payment_decision', ticket_id=ticket, approval_id=request, approve=True,
                               human_name='Offline Test Human', human_capability='offline-human-capability')

    async def test_human_gate_atomic_payment_and_replay(self):
        request = await self.request()
        with self.assertRaises(ToolError):
            await self.call('execute_approved_payment', ticket_id=101, approval_id=request)
        with self.assertRaises(ToolError):
            await self.call('record_human_payment_decision', ticket_id=101, approval_id=request, approve=True, human_name='Agent', human_capability='forged')
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)
        await self.approve(101, request)
        first = await self.call('execute_approved_payment', ticket_id=101, approval_id=request)
        replay = await self.call('execute_approved_payment', ticket_id=101, approval_id=request)
        self.assertEqual(first['payment']['id'], replay['payment']['id'])
        self.assertTrue(replay['already_executed'])
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 2560.0)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 1)
        self.assertEqual(self.scalar('SELECT status FROM invoices WHERE id=501'), 'paid')
        self.assertEqual(self.scalar('SELECT status FROM tickets WHERE id=101'), 'open')

    async def test_insufficient_cash_at_request_and_execution(self):
        request = await self.request()
        await self.approve(101, request)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE cash_accounts SET balance=100')
            c.commit()
        with self.assertRaises(ToolError):
            await self.call('execute_approved_payment', ticket_id=101, approval_id=request)
        with self.assertRaises(ToolError):
            await self.request(102, 'rent', 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 0)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 100.0)
        self.assertEqual(self.scalar('SELECT status FROM invoices'), 'open')

    async def test_changed_obligation_needs_new_approval(self):
        request = await self.request()
        await self.approve(101, request)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE invoices SET amount=850 WHERE id=501')
            c.commit()
        with self.assertRaises(ToolError):
            await self.call('execute_approved_payment', ticket_id=101, approval_id=request)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400.0)
        await self.call('record_human_payment_decision', ticket_id=101, approval_id=request, approve=False,
                        human_name='Offline Test Human', human_capability='offline-human-capability')
        replacement = await self.request()
        self.assertNotEqual(replacement, request)
        await self.approve(101, replacement)
        await self.call('execute_approved_payment', ticket_id=101, approval_id=replacement)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 2550.0)

    async def test_shipping_block_and_database_lead_days(self):
        status = await self.call('get_vendor_shipping_status', ticket_id=101, vendor_id=1)
        self.assertFalse(status['shipping_allowed'])
        with self.assertRaises(ToolError):
            await self.call('plan_vendor_shipment', ticket_id=101, vendor_id=1, qty=1, supplier_evidence='invoice 501 description')
        request = await self.request()
        await self.approve(101, request)
        await self.call('execute_approved_payment', ticket_id=101, approval_id=request)
        status = await self.call('get_vendor_shipping_status', ticket_id=101, vendor_id=1)
        self.assertTrue(status['shipping_allowed'])
        self.assertEqual(status['earliest_arrival_if_shipped_today'], '2026-09-05')
        plan = await self.call('plan_vendor_shipment', ticket_id=101, vendor_id=1, qty=1, supplier_evidence='invoice 501 description; quantity proposed, not confirmed')
        self.assertTrue(plan['draft_only'])
        self.assertEqual(self.scalar("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'"), 0)

    async def test_rent_updates_and_no_repeat_month_payment(self):
        request = await self.request(102, 'rent', 1)
        await self.approve(102, request)
        await self.call('execute_approved_payment', ticket_id=102, approval_id=request)
        self.assertEqual(self.scalar('SELECT next_due FROM leases'), '2026-10-02')
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 1000.0)
        self.assertEqual(self.scalar('SELECT status FROM tickets WHERE id=102'), 'resolved')
        with self.assertRaises(ToolError):
            await self.request(102, 'rent', 1)

    async def test_drafts_and_stock_checks(self):
        draft = await self.call('save_message_draft', ticket_id=103, recipient='Yale AI Club', body='Unsent draft only')
        self.assertEqual(draft['status'], 'draft')
        with self.assertRaises(ToolError):
            await self.call('save_quote_draft', ticket_id=103, unit_price='21.00', rationale='below cost')
        await self.call('save_quote_draft', ticket_id=103, unit_price='50.00', rationale='draft subject to policy')
        self.assertEqual(self.scalar("SELECT list_price FROM pricing WHERE sku='CC-HOOD-NAVY'"), 58.0)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400.0)
        with self.assertRaises(ToolError):
            await self.call('fulfill_customer_order', ticket_id=101)
        # Fixture-only stock change verifies the successful exact-size fulfillment path.
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE inventory SET qty=2 WHERE sku='CC-TEE-WHITE' AND size='S'")
            c.commit()
        await self.call('fulfill_customer_order', ticket_id=101)
        replay = await self.call('fulfill_customer_order', ticket_id=101)
        self.assertTrue(replay['already_fulfilled'])
        self.assertEqual(self.scalar("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'"), 1)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 3400.0)

    async def test_agent_delegation_and_append_preservation(self):
        def fake_model(messages, info):
            role = 'Inventory' if info.instructions.startswith('You are Inventory') else 'Boss'
            returns = [part for msg in messages for part in msg.parts if isinstance(part, ToolReturnPart)]
            if not returns:
                if role == 'Boss':
                    return ModelResponse(parts=[ToolCallPart('delegate', {'target': 'Inventory', 'ticket_id': 101, 'topic': 'stock', 'task': 'Check actual exact-size tee stock for ticket 101.'})])
                return ModelResponse(parts=[ToolCallPart('shop_tool', {'tool_name': 'get_ticket_context', 'arguments': {'ticket_id': 101}})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'ticket_id': 101, 'agent': role, 'summary': 'Offline integration check', 'status': 'blocked', 'evidence': ['MCP ticket 101'], 'uncertainties': ['Stock unresolved']})])

        audit = self.directory / 'audit.json'
        audit.write_text('[{"previous_entry": true}]', encoding='utf-8')
        team = ShopTeam(root=HW_ROOT, model=FunctionModel(fake_model), audit_path=audit)
        team.client = self.client
        report = await team.run_ticket(101, 'Offline delegation test')
        self.assertEqual(report.agent, AgentRole.BOSS)
        entries = json.loads(audit.read_text(encoding='utf-8'))
        self.assertEqual(entries[0], {'previous_entry': True})
        self.assertIn('delegation_returned', [entry.get('event') for entry in entries])
        self.assertIn('loop_step_completed', [entry.get('event') for entry in entries])
        self.assertIn('tool_result', [entry.get('event') for entry in entries])
        roles = {entry.get('agent') for entry in entries}
        self.assertIn('Inventory', roles)
        self.assertIn('Boss', roles)

    async def test_same_specialist_topic_reuses_report_without_model_call(self):
        from .models import AgentReport
        team = ShopTeam(root=HW_ROOT, audit_path=self.directory / 'reuse_audit.json')
        shared = SharedRun(103, 'price_override', team)
        ctx = SimpleNamespace(deps=AgentDeps(shared, AgentRole.BOSS, (AgentRole.BOSS,)))
        calls = []
        async def specialist(deps, prompt):
            calls.append(prompt)
            return AgentReport(ticket_id=103,agent=AgentRole.INVENTORY,status='blocked',summary='8 available; 20 requested; supplier unknown')
        team.run_agent = specialist
        first = await delegate(ctx, AgentRole.INVENTORY,103,'stock','Check exact size stock')
        second = await delegate(ctx, AgentRole.INVENTORY,103,'stock','Confirm the stock again')
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(shared.delegations, 1)

    async def test_simulated_restock_requires_human_plan_date_and_confirmation(self):
        approval = await self.request()
        await self.call('approve_and_execute_payment', ticket_id=101, approval_id=approval, human_name='Fixture Human',human_capability='offline-human-capability')
        proposal = await self.call('prepare_resolution_review',ticket_id=101,kind='simulated_restock',rationale='Classroom-only one-tee simulation; quantity assumption explicit')
        rid=proposal['review']['id']
        payload=json.loads(proposal['review']['payload'])
        self.assertEqual(payload['earliest_arrival'],'2026-09-05')
        self.assertEqual(self.scalar("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'"),0)
        with self.assertRaises(ToolError):
            await self.call('decide_resolution_review',ticket_id=101,review_id=rid,approve=True,human_name='AI',acknowledge_completion_rule=True,human_capability='wrong')
        await self.call('decide_resolution_review',ticket_id=101,review_id=rid,approve=True,human_name='Fixture Human',acknowledge_completion_rule=True,human_capability='offline-human-capability')
        with self.assertRaises(ToolError):
            await self.call('confirm_simulated_receipt_and_fulfill',ticket_id=101,review_id=rid,human_name='Fixture Human',confirm_simulation=True,human_capability='offline-human-capability')
        await self.call('advance_simulation_date',new_date='2026-09-05',reason='Explicit classroom time advance',human_capability='offline-human-capability')
        result=await self.call('confirm_simulated_receipt_and_fulfill',ticket_id=101,review_id=rid,human_name='Fixture Human',confirm_simulation=True,human_capability='offline-human-capability')
        self.assertTrue(result['simulation'])
        self.assertFalse(result['physical_delivery_claimed'])
        self.assertEqual(result['ticket']['status'],'resolved')
        replay=await self.call('confirm_simulated_receipt_and_fulfill',ticket_id=101,review_id=rid,human_name='Fixture Human',confirm_simulation=True,human_capability='offline-human-capability')
        self.assertTrue(replay['already_executed'])
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'),2560)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'),1)

    async def test_human_price_decision_resolves_pricing_only_without_stock_or_cash_change(self):
        proposal=await self.call('prepare_resolution_review',ticket_id=103,kind='pricing_decision',rationale='Human-selected proposal; no existing policy asserted',unit_price='50.00')
        rid=proposal['review']['id']
        self.assertEqual(self.scalar("SELECT status FROM tickets WHERE id=103"),'open')
        with self.assertRaises(ToolError):
            await self.call('decide_resolution_review',ticket_id=103,review_id=rid,approve=True,human_name='Fixture Human',acknowledge_completion_rule=False,human_capability='offline-human-capability')
        result=await self.call('decide_resolution_review',ticket_id=103,review_id=rid,approve=True,human_name='Fixture Human',acknowledge_completion_rule=True,human_capability='offline-human-capability')
        self.assertEqual(result['ticket']['status'],'resolved')
        self.assertEqual(self.scalar("SELECT qty FROM inventory WHERE sku='CC-HOOD-NAVY' AND size='M'"),8)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'),3400)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'),0)
        self.assertEqual(self.scalar('SELECT status FROM quote_drafts'),'draft')

    async def test_record_price_choice_preserves_open_status_and_conditional_stock(self):
        proposal=await self.call('prepare_resolution_review',ticket_id=103,kind='pricing_decision',rationale='Human retains list price',unit_price='58.00')
        result=await self.call('record_conditional_quote_decision',ticket_id=103,review_id=proposal['review']['id'],human_name='Fixture Human',human_capability='offline-human-capability')
        self.assertEqual(result['ticket']['status'],'open')
        self.assertFalse(result['resolution_applied'])
        self.assertIn('Only 8 of the requested 20',result['conditional_quote'])
        self.assertIn('Fulfillment of all 20 is not guaranteed',result['conditional_quote'])
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'),3400)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'),0)
        final=await self.call('decide_resolution_review',ticket_id=103,review_id=proposal['review']['id'],approve=True,human_name='Fixture Human',acknowledge_completion_rule=True,human_capability='offline-human-capability')
        self.assertEqual(final['ticket']['status'],'resolved')
        self.assertIn('Only 8 of the requested 20',self.scalar('SELECT rationale FROM quote_drafts'))

    async def test_recovery_restores_committed_records_without_replaying_cash_or_stock(self):
        shutil.copy2(HW_ROOT/'data/campus_customs.db',self.db.with_name('campus_customs.db'))
        for tid,kind,ref in [(101,'invoice',501),(102,'rent',1)]:
            aid=await self.request(ticket=tid,kind=kind,ref=ref)
            await self.call('approve_and_execute_payment',ticket_id=tid,approval_id=aid,human_name='Fixture Human',human_capability='offline-human-capability')
        proposal=await self.call('prepare_resolution_review',ticket_id=101,kind='simulated_restock',rationale='Explicit simulation')
        rid=proposal['review']['id']
        await self.call('decide_resolution_review',ticket_id=101,review_id=rid,approve=True,human_name='Fixture Human',acknowledge_completion_rule=True,human_capability='offline-human-capability')
        await self.call('advance_simulation_date',new_date='2026-09-05',reason='Explicit simulation',human_capability='offline-human-capability')
        receipt=await self.call('confirm_simulated_receipt_and_fulfill',ticket_id=101,review_id=rid,human_name='Fixture Human',confirm_simulation=True,human_capability='offline-human-capability')
        price=await self.call('prepare_resolution_review',ticket_id=103,kind='pricing_decision',unit_price='58.00',rationale='Human choice58')
        await self.call('record_conditional_quote_decision',ticket_id=103,review_id=price['review']['id'],human_name='Fixture Human',human_capability='offline-human-capability')
        decision=await self.call('decide_resolution_review',ticket_id=103,review_id=price['review']['id'],approve=True,human_name='Fixture Human',acknowledge_completion_rule=True,human_capability='offline-human-capability')
        with closing(sqlite3.connect(self.db)) as c:
            c.row_factory=sqlite3.Row
            source={t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in ['tickets','resolution_reviews','quote_drafts','fulfillments','inventory','desk']}
        out=self.directory/'output';out.mkdir()
        (out/'resolution_completion_evidence.json').write_text(json.dumps({'actions':{'101_simulated_receipt_fulfillment':receipt,'103_pricing_completion':decision},'verified_rows':source}))
        reset=await self.call('reset_working_database',confirmation='RESET_WORKING_DATABASE',human_capability='offline-human-capability')
        records=[{'sequence':1,'event':'dashboard_tool_result','tool_calls':[{'tool':'confirm_simulated_receipt_and_fulfill'}],'results':receipt},
                 {'sequence':2,'event':'dashboard_tool_result','tool_calls':[{'tool':'decide_resolution_review'}],'results':decision},
                 {'sequence':3,'event':'dashboard_tool_result','tool_calls':[{'tool':'reset_working_database'}],'results':reset}]
        (out/'audit_trail.json').write_text(json.dumps(records))
        for tid,kind,ref in [(101,'invoice',501),(102,'rent',1)]:
            aid=await self.request(ticket=tid,kind=kind,ref=ref)
            await self.call('approve_and_execute_payment',ticket_id=tid,approval_id=aid,human_name='Fixture Human',human_capability='offline-human-capability')
        with self.assertRaises(ToolError):
            await self.call('recover_committed_resolution',expected_reset_sequence=2,reason='Recover existing commit',human_capability='offline-human-capability')
        with self.assertRaises(ToolError):
            await self.call('recover_committed_resolution',expected_reset_sequence=3,reason='Recover existing commit',human_capability='wrong')
        recovered=await self.call('recover_committed_resolution',expected_reset_sequence=3,reason='Recover existing commit without replay',human_capability='offline-human-capability')
        self.assertTrue(recovered['recovery_only'])
        self.assertFalse(recovered['simulation_repeated'])
        self.assertFalse(recovered['inventory_changed'])
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'),160)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'),2)
        self.assertEqual(self.scalar("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'"),0)
        self.assertEqual(self.scalar('SELECT count(*) FROM fulfillments'),1)
        self.assertEqual(self.scalar("SELECT status FROM tickets WHERE id=101"),'resolved')
        self.assertEqual(self.scalar('SELECT unit_price FROM quote_drafts'),'58.00')

    async def test_scope_delegation_and_loop_limits(self):
        team = ShopTeam(root=HW_ROOT, audit_path=self.directory / 'scope_audit.json')
        shared = SharedRun(101, 'customer_order', team)
        deps = AgentDeps(shared, AgentRole.BOSS, (AgentRole.BOSS,))
        ctx = SimpleNamespace(deps=deps)
        with self.assertRaises(ModelRetry):
            await shop_tool(ctx, 'get_ticket_context', {'ticket_id': 102})
        with self.assertRaises(ModelRetry):
            await delegate(ctx, AgentRole.FACILITIES, 101, 'rent', 'Unrelated rent task')
        with self.assertRaises(ModelRetry):
            await delegate(ctx, AgentRole.INVENTORY, 102, 'stock', 'Different ticket')
        with self.assertRaises(ModelRetry):
            await delegate(ctx, AgentRole.BOSS, 101, 'coordination', 'Cycle')
        shared.delegations = team.limits.delegations
        with self.assertRaises(ModelRetry):
            await delegate(ctx, AgentRole.INVENTORY, 101, 'stock', 'Stock question')

        def output_model(messages, info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'ticket_id': 101, 'agent': 'Boss', 'summary': 'Offline limit test', 'status': 'blocked'})])
        limited = ShopTeam(root=HW_ROOT, model=FunctionModel(output_model), limits=RunLimits(loop_steps=1),
                           audit_path=self.directory / 'limit_audit.json')
        limited.client = self.client
        with self.assertRaisesRegex(RuntimeError, 'step budget'):
            await limited.run_ticket(101, 'Exercise loop budget')
        events = json.loads((self.directory / 'limit_audit.json').read_text(encoding='utf-8'))
        self.assertIn('agent_stopped', [entry['event'] for entry in events])

    async def test_concurrent_payment_replay(self):
        request = await self.request()
        await self.approve(101, request)
        results = await asyncio.gather(*[self.call('execute_approved_payment', ticket_id=101, approval_id=request) for _ in range(2)])
        self.assertEqual(sum(not result['already_executed'] for result in results), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM payments'), 1)
        self.assertEqual(self.scalar('SELECT balance FROM cash_accounts'), 2560.0)


class AuditReliability(unittest.TestCase):
    def test_transient_windows_replace_failure_preserves_previous_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.json'
            audit = AuditTrail(path)
            audit.append(ticket=101, agent='Boss', event='before', run_id='fixture')
            previous = json.loads(path.read_text(encoding='utf-8'))
            real_replace = os.replace
            attempts = []
            def replace(source, target):
                attempts.append(1)
                if len(attempts) < 3: raise PermissionError('Fixture sharing violation')
                return real_replace(source, target)
            with patch('backend.audit.os.replace', side_effect=replace), patch('backend.audit.time.sleep'):
                audit.append(ticket=101, agent='Boss', event='after', run_id='fixture')
            records = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(records[:-1], previous)
            self.assertEqual(records[-1]['sequence'], 2)
            self.assertEqual(len(attempts), 3)

    def test_persistent_replace_failure_does_not_truncate_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.json'
            audit = AuditTrail(path)
            audit.append(ticket=101, agent='Boss', event='before', run_id='fixture')
            previous = path.read_bytes()
            with patch('backend.audit.os.replace', side_effect=PermissionError('Fixture locked')), patch('backend.audit.time.sleep'):
                with self.assertRaises(PermissionError):
                    audit.append(ticket=101, agent='Boss', event='after', run_id='fixture')
            self.assertEqual(path.read_bytes(), previous)


if __name__ == '__main__':
    unittest.main()
