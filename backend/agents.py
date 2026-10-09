"""Five PydanticAI roles sharing MCP, usage budgets, and append-only audit events."""
import asyncio
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import secrets
from typing import get_args
from uuid import uuid4

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from .audit import AuditTrail
from .config import HW_ROOT, MODEL_NAME, MODEL_CALL_CONTEXT, create_model, model_matches
from .models import AgentDeps, AgentReport, AgentRole, HumanDecision, RunLimits, SharedRun, ShopTool
from .tools import delegate, shop_tool

PROMPT_FILES = {role: role.value.lower().replace(' ', '_') + '.md' for role in AgentRole}


class ApprovalPause(Exception):
    """A durable pending request ends this run before another model request."""
    def __init__(self, request, agent):
        self.request = request
        self.agent = agent
        super().__init__('Pending human approval: ' + request['id'])


class ShopTeam:
    def __init__(self, limits: RunLimits | None = None, *, root: Path = HW_ROOT,
                 model=None, audit_path: Path | None = None):
        self.root = root.resolve()
        self.limits = limits or RunLimits()
        self.audit = AuditTrail(audit_path or self.root / 'output/audit_trail.json')
        self._http_client = None
        if model is not None and not isinstance(model, FunctionModel):
            raise ValueError('Only an offline FunctionModel may override the fixed Portkey model')
        self._test_model = model  # Offline simulation only; no alternate live AI.
        self.agents = {}
        self.client = None
        self._human_capability = secrets.token_urlsafe(32)
        self._run_lock = asyncio.Lock()
        self.tool_contracts = {}

    def build_agents(self):
        model = self._test_model
        if model is None:
            model, self._http_client = create_model(self.record_model_evidence)
        for role in AgentRole:
            agent = Agent(model, name=role.value, deps_type=AgentDeps, output_type=AgentReport,
                          instructions=(self.root / 'backend/prompts' / PROMPT_FILES[role]).read_text(encoding='utf-8')
                          + '\nStop after the necessary specialists return. Reuse returned evidence. Missing supplier/discount authority is a blocker, not a reason for repeated investigation. Keep tool reads minimal and final findings concise.\nActual MCP argument contracts (include ticket_id; no extra keys):\n'
                          + json.dumps(self.tool_contracts, separators=(',', ':')),
                          model_settings={'max_tokens': self.limits.output_tokens_per_request,
                                          'parallel_tool_calls': False}, retries=1, tool_timeout=45)
            agent.tool(shop_tool, sequential=True)
            agent.tool(delegate, sequential=True)

            async def validate_report(ctx, report):
                if report.ticket_id != ctx.deps.shared.ticket_id or report.agent != ctx.deps.role:
                    raise ModelRetry('Output must identify the current ticket and your current agent role')
                if report.status == 'resolved':
                    context = await self.call_shop(ctx.deps, 'get_ticket_context', {'ticket_id': report.ticket_id})
                    if context['ticket']['status'] != 'resolved':
                        raise ModelRetry('The database ticket is not resolved. Report the remaining blocker or pending human decision.')
                return report

            agent.output_validator(validate_report)
            self.agents[role] = agent

    def record_model_evidence(self, event, result):
        context = MODEL_CALL_CONTEXT.get()
        if context:
            self.audit.append(ticket=context['ticket'], agent=context['agent'], event=event,
                              run_id=context['run_id'], results=result)

    async def __aenter__(self):
        python = self.root / '.venv/Scripts/python.exe'
        transport = StdioTransport(command=str(python), args=[str(self.root / 'mcp_server/server.py')],
                                   cwd=str(self.root), env={'CAMPUS_HUMAN_APPROVAL_SECRET': self._human_capability},
                                   keep_alive=False)
        self.client = Client(transport, timeout=30, init_timeout=30)
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args):
        try:
            if self.client:
                await self.client.__aexit__(*args)
        finally:
            if self._http_client:
                await self._http_client.close()

    async def _call(self, tool_name, arguments):
        if self.client is None:
            raise RuntimeError('Use ShopTeam as an async context manager')
        result = await self.client.call_tool(tool_name, arguments)
        if result.is_error:
            raise ValueError(f'MCP tool {tool_name} failed')
        if result.structured_content is not None:
            return result.structured_content
        return json.loads(next(block.text for block in result.content if block.type == 'text'))

    async def initialize(self):
        for tool in await self.client.list_tools():
            if tool.name in get_args(ShopTool):
                schema = tool.inputSchema
                self.tool_contracts[tool.name] = {
                    'required': schema.get('required', []),
                    'fields': {key: {k: v for k, v in field.items() if k in ('type', 'enum', 'default')}
                               for key, field in schema.get('properties', {}).items()},
                }
        result = await self._call('initialize_shop_tools', {'human_capability': self._human_capability})
        self.audit.append(ticket=None, agent='Human', event='schema_initialized', run_id=str(uuid4()), results=result)
        return result

    async def call_shop(self, deps, tool_name, arguments):
        shared = deps.shared
        if tool_name in ('request_payment_approval', 'request_purchase_approval') and not shared.prepare_payments:
            raise ModelRetry('Payment preparation is disabled for this run; report the decision needed without preparing a request')
        if 'vendor_id' in arguments and (not isinstance(arguments['vendor_id'], int) or arguments['vendor_id'] <= 0):
            raise ModelRetry('Use a real positive vendor ID from supplied evidence; if unknown, report the missing supplier instead of guessing an ID')
        if tool_name not in get_args(ShopTool) or arguments.get('ticket_id') != shared.ticket_id:
            raise ModelRetry('Only allowlisted tools on this ticket are available')
        contract = self.tool_contracts.get(tool_name)
        if contract:
            extra = set(arguments) - set(contract['fields'])
            missing = set(contract['required']) - set(arguments)
            if extra or missing:
                raise ModelRetry(f"Use the exact MCP contract for {tool_name}: extra={sorted(extra)}, missing={sorted(missing)}; fields={list(contract['fields'])}")
        shared.mcp_calls += 1
        if shared.mcp_calls > self.limits.tool_calls:
            raise RuntimeError('MCP call budget exhausted')
        call = {'tool': tool_name, 'arguments': arguments}
        self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='tool_requested',
                          run_id=shared.run_id, tool_calls=[call])
        try:
            result = await self._call(tool_name, arguments)
        except Exception as exc:
            self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='tool_failed',
                              run_id=shared.run_id, tool_calls=[call], results={'error': str(exc)})
            raise ModelRetry(str(exc)) from exc
        if not tool_name.startswith(('get_', 'list_')):
            shared.specialist_reports.clear()
        approvals = [result['approval_request']] if result.get('human_approval_required') else []
        self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='tool_result',
                          run_id=shared.run_id, tool_calls=[call], results=result, approval_requests=approvals)
        if approvals and approvals[0].get('status') == 'pending':
            raise ApprovalPause(approvals[0], deps.role)
        return result

    async def run_agent(self, deps: AgentDeps, prompt: str) -> AgentReport:
        shared = deps.shared
        if not self.agents:
            self.build_agents()
        usage_limits = UsageLimits(request_limit=self.limits.model_requests, tool_calls_limit=self.limits.tool_calls,
                                   total_tokens_limit=self.limits.total_tokens)
        self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='agent_started',
                          run_id=shared.run_id, results={'task': prompt, 'chain': [r.value for r in deps.chain]})
        context_token = MODEL_CALL_CONTEXT.set({'ticket':shared.ticket_id, 'agent':deps.role.value, 'run_id':shared.run_id})
        try:
            async with self.agents[deps.role].iter(prompt, deps=deps, usage=shared.usage, usage_limits=usage_limits) as run:
                node = run.next_node
                while not Agent.is_end_node(node):
                    shared.steps += 1
                    if shared.steps > self.limits.loop_steps:
                        raise RuntimeError('Shared agent-loop step budget exhausted')
                    step = shared.steps
                    self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='loop_step_started',
                                      run_id=shared.run_id, results={'step': step, 'node': type(node).__name__})
                    try:
                        next_node = await run.next(node)
                    except BaseException as exc:
                        self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='loop_step_paused' if isinstance(exc, ApprovalPause) else 'loop_step_failed',
                                          run_id=shared.run_id, results={'step': step, 'node': type(node).__name__,
                                                                      'error_type': type(exc).__name__, 'message': str(exc)[:2000]})
                        raise
                    # The next node carries the previous model response/tool results.
                    payload = asdict(next_node) if is_dataclass(next_node) else {'node': type(next_node).__name__}
                    response = payload.get('model_response', {})
                    if response.get('model_name') and self._test_model is None:
                        reported = response['model_name']
                        self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='provider_model_verified',
                                          run_id=shared.run_id, results={'requested': MODEL_NAME, 'reported': reported})
                        if not model_matches(reported):
                            raise RuntimeError(f'Portkey model mismatch: requested {MODEL_NAME}, reported {reported}; no response tools executed')
                    self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='loop_step_completed',
                                      run_id=shared.run_id, results={'step': step, 'next': payload, 'usage': asdict(shared.usage)})
                    node = next_node
                result = run.result.output
            self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='agent_completed',
                              run_id=shared.run_id, results=result.model_dump(mode='json'))
            return result
        except BaseException as exc:
            self.audit.append(ticket=shared.ticket_id, agent=deps.role.value, event='agent_paused' if isinstance(exc, ApprovalPause) else 'agent_stopped',
                              run_id=shared.run_id, results={'error_type': type(exc).__name__, 'message': str(exc)[:2000]})
            raise
        finally:
            MODEL_CALL_CONTEXT.reset(context_token)

    async def enforce_payment_preparation(self, shared, report):
        """Workflow postcondition, not a fabricated model decision or payment approval."""
        async def call(name, arguments):
            shared.mcp_calls += 1
            if shared.mcp_calls > self.limits.tool_calls:
                raise RuntimeError('MCP call budget exhausted during payment preparation')
            tool = {'tool':name, 'arguments':arguments}
            self.audit.append(ticket=shared.ticket_id, agent='Workflow', event='tool_requested', run_id=shared.run_id, tool_calls=[tool])
            try:
                result = await self._call(name, arguments)
            except Exception as exc:
                self.audit.append(ticket=shared.ticket_id, agent='Workflow', event='tool_failed', run_id=shared.run_id,
                    tool_calls=[tool], results={'error':str(exc)})
                raise
            approvals = [result['approval_request']] if result.get('human_approval_required') else []
            self.audit.append(ticket=shared.ticket_id, agent='Workflow', event='tool_result', run_id=shared.run_id,
                tool_calls=[tool], results=result, approval_requests=approvals)
            return result

        context = await call('get_ticket_context', {'ticket_id':shared.ticket_id})
        t = context['ticket']
        if not shared.prepare_payments or t['status'] != 'open' or t['type'] not in ('customer_order','rent_notice'):
            return report
        pending = [r for r in context.get('payment_approvals',[]) if r['status']=='pending']
        if pending:
            request = pending[0]
        else:
            details = await call('get_cash_obligations', {'ticket_id':shared.ticket_id})
            if t['type']=='customer_order':
                invoice = next((r for r in details.get('open_invoices',[]) if r['id']==t['invoice_id']), None)
                if not invoice or invoice['status'] != 'open': return report
                kind, ref_id = 'invoice', t['invoice_id']
            else:
                if not any(r['id']==t['lease_id'] for r in details.get('leases',[])): return report
                kind, ref_id = 'rent', t['lease_id']
            due = invoice['due_date'] if kind == 'invoice' else next(r['next_due'] for r in details['leases'] if r['id']==ref_id)
            if any(r['status']=='denied' and r['kind']==kind and r['ref_id']==ref_id and r['due_date']==due for r in context.get('payment_approvals',[])):
                return report.model_copy(update={'status':'blocked', 'summary':report.summary+'\nHuman declined this obligation; automatic preparation will not recreate it.', 'next_actions':['Use Prepare payment request only if you explicitly decide to reconsider.']})
            try:
                result = await call('request_payment_approval', {'ticket_id':shared.ticket_id, 'kind':kind, 'ref_id':ref_id,
                    'reason':'Progress-run workflow prepares the recorded linked obligation for human review only. Preparation is not approval; future due dates do not prohibit preparation.'})
            except Exception as exc:
                return report.model_copy(update={'status':'blocked','summary':report.summary + '\nPayment preparation was refused: '+str(exc),
                    'next_actions':['Review the recorded obligation/cash refusal before preparing again.']+report.next_actions})
            request = result['approval_request']
        return report.model_copy(update={'status':'awaiting_human',
            'summary':report.summary + f"\nPending human review: {request['kind']} {request['ref_id']}, amount {request['amount']}. No payment executed.",
            'approval_request_ids':[request['id']], 'next_actions':['Review the prepared request; after the human decision, continue this ticket using fresh MCP records.']+report.next_actions})

    async def run_ticket(self, ticket_id: int, task: str, start_role: AgentRole = AgentRole.BOSS, *, run_id: str | None = None, prepare_payments: bool = True):
        if not task.strip() or len(task) > 4000:
            raise ValueError('Ticket task must contain 1–4000 characters')
        async with self._run_lock:
            # Bootstrap is MCP-only. No backend SQLite access.
            run_id = run_id or str(uuid4())
            context = await self._call('get_ticket_context', {'ticket_id': ticket_id})
            self.audit.append(ticket=ticket_id, agent=start_role.value, event='ticket_loaded', run_id=run_id,
                              tool_calls=[{'tool': 'get_ticket_context', 'arguments': {'ticket_id': ticket_id}}], results=context)
            shared = SharedRun(ticket_id, context['ticket']['type'], self, run_id=run_id, mcp_calls=1, prepare_payments=prepare_payments)
            deps = AgentDeps(shared, start_role, (start_role,))
            try:
                async with asyncio.timeout(self.limits.wall_seconds):
                    report = await self.run_agent(deps, f'Ticket {ticket_id}. Work only on this ticket. Payment preparation enabled: {prepare_payments}. Task: {task}')
                    report = await self.enforce_payment_preparation(shared, report)
                    self.audit.append(ticket=ticket_id, agent='Workflow', event='workflow_completed', run_id=run_id,
                                      results=report.model_dump(mode='json'))
                    return report
            except ApprovalPause as pause:
                report = AgentReport(ticket_id=ticket_id, agent=start_role, status='awaiting_human',
                    summary=f"Paused for human approval of {pause.request.get('kind', 'purchase')} request {pause.request['id']} for {pause.request['amount']}. No payment executed.",
                    evidence=['Durable MCP approval request recorded by ' + pause.agent.value],
                    approval_request_ids=[pause.request['id']], next_actions=['Human must review the request in the dashboard. Resume this ticket after the decision.'])
                self.audit.append(ticket=ticket_id, agent=start_role.value, event='agent_completed', run_id=run_id,
                                  results=report.model_dump(mode='json'), approval_requests=[pause.request])
                return report
            except TimeoutError:
                self.audit.append(ticket=ticket_id, agent=start_role.value, event='run_timeout', run_id=run_id)
                raise

    async def human_decision(self, decision: HumanDecision):
        """Trusted application/CLI entry point. Never registered as an agent tool."""
        run_id = str(uuid4())
        safe = decision.model_dump()
        self.audit.append(ticket=decision.ticket_id, agent='Human', event='human_decision_requested', run_id=run_id,
                          tool_calls=[{'tool': 'record_human_payment_decision', 'arguments': safe}])
        try:
            result = await self._call('record_human_payment_decision', {**safe, 'human_capability': self._human_capability})
        except Exception as exc:
            self.audit.append(ticket=decision.ticket_id, agent='Human', event='human_decision_failed',
                              run_id=run_id, results={'error': str(exc)})
            raise
        self.audit.append(ticket=decision.ticket_id, agent='Human', event='human_decision_recorded', run_id=run_id, results=result)
        if decision.approve:
            arguments = {'ticket_id': decision.ticket_id, 'approval_id': decision.approval_id}
            self.audit.append(ticket=decision.ticket_id, agent='Human', event='approved_payment_requested', run_id=run_id,
                              tool_calls=[{'tool': 'execute_approved_payment', 'arguments': arguments}])
            try:
                result = await self._call('execute_approved_payment', arguments)
            except Exception as exc:
                self.audit.append(ticket=decision.ticket_id, agent='Human', event='approved_payment_failed',
                                  run_id=run_id, results={'error': str(exc)})
                raise
            self.audit.append(ticket=decision.ticket_id, agent='Human', event='approved_payment_result', run_id=run_id,
                              tool_calls=[{'tool': 'execute_approved_payment', 'arguments': {'ticket_id': decision.ticket_id, 'approval_id': decision.approval_id}}], results=result)
        return result
