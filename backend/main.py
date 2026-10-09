"""Dashboard API. Start from backend/: uvicorn main:app --reload --port 8000."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

# Support both `uvicorn main:app` from backend/ and package imports in tests.
HW_ROOT = Path(__file__).resolve().parents[1]
if str(HW_ROOT) not in sys.path:
    sys.path.insert(0, str(HW_ROOT))

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastmcp.exceptions import ToolError
from filelock import FileLock

from backend.agents import ShopTeam
from backend.api_models import RecoveryBody, QuoteDecisionBody, ResolutionProposalBody, ResolutionDecisionBody, SimulationDateBody, SimulatedReceiptBody
from backend.api_models import (ApprovalBody, DenialBody, PreparePaymentBody,
                                PreparePurchaseBody, ResetBody, RunTicketBody)


def human_token(path: Path):
    load_dotenv(HW_ROOT / '.env', override=False)
    load_dotenv(HW_ROOT.parent / '.env', override=False)
    configured = os.environ.get('CAMPUS_HUMAN_API_TOKEN', '').strip()
    if configured:
        if len(configured) < 32:
            raise ValueError('CAMPUS_HUMAN_API_TOKEN must have at least 32 characters')
        return configured
    with FileLock(str(path) + '.lock', timeout=10):
        if not path.exists():
            with path.open('x', encoding='utf-8') as file:
                file.write(secrets.token_urlsafe(32) + '\n')
        token = path.read_text(encoding='utf-8').strip()
        if len(token) < 32:
            raise ValueError('Invalid local human API token file')
        return token


def create_app(*, team_factory=ShopTeam, token: str | None = None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.human_token = token or human_token(Path(__file__).with_name('.human_api_token'))
        app.state.jobs = {}
        app.state.active_job = None
        app.state.operation_lock = asyncio.Lock()
        app.state.tasks = set()
        # MCP lifecycle stays on the same task as lifespan startup/shutdown.
        async with team_factory() as team:
            app.state.team = team
            await team.initialize()
            try:
                yield
            finally:
                tasks = list(app.state.tasks)
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title='Campus Customs Dashboard API', version='1.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[
        'http://localhost:8000', 'http://127.0.0.1:8000',
        'http://localhost:8050', 'http://127.0.0.1:8050',
        'http://localhost:5173', 'http://127.0.0.1:5173',
        'http://localhost:5174', 'http://127.0.0.1:5174',
    ], allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])
    bearer = HTTPBearer(auto_error=False)

    async def require_human(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None or credentials.scheme.lower() != 'bearer' or not hmac.compare_digest(credentials.credentials, app.state.human_token):
            raise HTTPException(401, 'Human bearer token required', headers={'WWW-Authenticate': 'Bearer'})

    def assignment_ticket(ticket_id):
        if ticket_id not in (101, 102, 103):
            raise HTTPException(404, 'Unknown assignment ticket')

    def idle():
        if app.state.active_job is not None:
            raise HTTPException(409, 'An agent run is active; wait before preparing, approving, or resetting')

    async def mcp(tool, arguments, *, ticket=None, audit=False):
        run_id = str(uuid4())
        safe_arguments = {key: value for key, value in arguments.items() if key != 'human_capability'}
        call = {'tool': tool, 'arguments': safe_arguments}
        if audit:
            app.state.team.audit.append(ticket=ticket, agent='Human', event='dashboard_tool_requested', run_id=run_id, tool_calls=[call])
        try:
            result = await app.state.team._call(tool, arguments)
        except (ToolError, ValueError) as exc:
            if audit:
                app.state.team.audit.append(ticket=ticket, agent='Human', event='dashboard_tool_failed', run_id=run_id,
                                            tool_calls=[call], results={'error': str(exc)})
            status = 404 if 'not found' in str(exc).lower() or 'does not exist' in str(exc).lower() else 409
            raise HTTPException(status, str(exc)) from exc
        if audit:
            approvals = [result['approval_request']] if result.get('human_approval_required') else []
            app.state.team.audit.append(ticket=ticket, agent='Human', event='dashboard_tool_result', run_id=run_id,
                                        tool_calls=[call], results=result, approval_requests=approvals)
        return result

    @app.get('/health')
    async def health():
        return {'status':'ok','active_run_id':app.state.active_job,'runtime':await mcp('get_runtime_identity',{})}

    @app.post('/session/verify', dependencies=[Depends(require_human)])
    async def verify_session():
        """Validate operator credentials without running an agent or changing shop data."""
        return {'authorized': True}

    @app.get('/tickets')
    async def tickets():
        return await mcp('list_shop_tickets', {})

    @app.get('/tickets/{ticket_id}')
    async def ticket_detail(ticket_id: int):
        assignment_ticket(ticket_id)
        return await mcp('get_ticket_context', {'ticket_id': ticket_id})

    async def run_job(job_id, ticket_id, body):
        job = app.state.jobs[job_id]
        job['status'] = 'running'
        try:
            async with app.state.operation_lock:
                report = await app.state.team.run_ticket(ticket_id, body.task, body.agent, run_id=job_id,
                                                        prepare_payments=body.prepare_payments)
            job['status'] = 'completed'
            job['result'] = report.model_dump(mode='json')
            app.state.team.audit.append(ticket=ticket_id, agent=body.agent.value, event='dashboard_run_completed',
                run_id=job_id, results={'report':job['result']})
        except asyncio.CancelledError:
            job['status'] = 'interrupted'
            app.state.team.audit.append(ticket=ticket_id, agent=body.agent.value, event='dashboard_run_interrupted', run_id=job_id)
            raise
        except Exception as exc:
            job['status'] = 'failed'
            job['error'] = {'type': type(exc).__name__, 'message': str(exc)[:1000] if type(exc).__name__ == 'UsageLimitExceeded' else 'Run failed; inspect the audit trail for details.'}
            app.state.team.audit.append(ticket=ticket_id, agent=body.agent.value, event='dashboard_run_failed', run_id=job_id,
                                        results={'error_type': type(exc).__name__, 'message':job['error']['message']})
        finally:
            job['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
            app.state.active_job = None

    @app.post('/tickets/{ticket_id}/run', status_code=202, dependencies=[Depends(require_human)])
    async def run_ticket(ticket_id: int, body: RunTicketBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            await mcp('get_ticket_context', {'ticket_id': ticket_id})
            job_id = str(uuid4())
            app.state.jobs[job_id] = {'run_id': job_id, 'ticket_id': ticket_id, 'agent': body.agent.value, 'status': 'queued',
                                      'created_at_utc': datetime.now(timezone.utc).isoformat()}
            app.state.active_job = job_id
            app.state.team.audit.append(ticket=ticket_id, agent=body.agent.value, event='dashboard_run_queued', run_id=job_id,
                                        results={'task': body.task, 'prepare_payments':body.prepare_payments})
            task = asyncio.create_task(run_job(job_id, ticket_id, body))
            app.state.tasks.add(task)
            task.add_done_callback(app.state.tasks.discard)
        return dict(app.state.jobs[job_id])

    def durable_runs():
        path = app.state.team.audit.path
        with FileLock(str(path)+'.lock', timeout=10):
            data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        entries = data if isinstance(data,list) else data['entries']
        reset_sequence = max((e.get('sequence',0) for e in entries if e.get('event')=='dashboard_tool_result'
            and any(t.get('tool')=='reset_working_database' for t in e.get('tool_calls',[]))
            and (e.get('results') or {}).get('reset')), default=0)
        recovered = {}
        for e in entries:
            rid = e.get('run_id'); event = e.get('event'); result = e.get('results') or {}
            if event == 'dashboard_run_queued':
                recovered[rid] = {'run_id':rid, 'ticket_id':e['ticket'], 'agent':e['agent'], 'status':'interrupted',
                    'created_at_utc':e['timestamp_utc'], 'sequence':e.get('sequence',0), 'task':result.get('task',''),
                    'prepare_payments':result.get('prepare_payments',True),
                    'error':{'type':'Restart','message':'No terminal event is recorded; review activity before continuing.'}}
            elif rid in recovered:
                job = recovered[rid]
                if event == 'dashboard_run_completed' or event in ('agent_completed','workflow_completed') and e['agent'] in (job['agent'],'Workflow'):
                    job.update(status='completed', result=result.get('report',result), finished_at_utc=e['timestamp_utc'])
                    job.pop('error',None)
                elif event in ('dashboard_run_failed','dashboard_run_interrupted'):
                    job.update(status='failed' if event.endswith('failed') else 'interrupted',
                        error={'type':result.get('error_type','Interrupted'),'message':result.get('message','Inspect the recorded activity.')})
        for rid, job in app.state.jobs.items():
            recovered[rid] = {**recovered.get(rid,{}), **job}
        for job in recovered.values():
            job['database_reset_after_run'] = job.get('sequence',0) < reset_sequence
        return recovered, reset_sequence

    @app.get('/runs')
    async def recent_runs(ticket_id: int | None = None):
        if ticket_id is not None: assignment_ticket(ticket_id)
        jobs, reset_sequence = durable_runs()
        selected = [job for job in jobs.values() if not job['database_reset_after_run']
                    and (ticket_id is None or job['ticket_id']==ticket_id)]
        return {'runs':sorted(selected,key=lambda job:job.get('sequence',0),reverse=True)[:20],
                'last_reset_sequence':reset_sequence}

    @app.get('/runs/{run_id}')
    async def run_status(run_id: str):
        jobs, _ = durable_runs()
        job = jobs.get(run_id)
        if not job:
            raise HTTPException(404, 'Run not found in this server session; use activity for durable history')
        return job

    @app.get('/activity')
    async def activity(ticket_id: int | None = None, run_id: str | None = None,
                       after_sequence: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        if ticket_id is not None:
            assignment_ticket(ticket_id)
        path = app.state.team.audit.path
        with FileLock(str(path) + '.lock', timeout=10):
            data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        entries = data if isinstance(data, list) else data.get('entries') if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise HTTPException(500, 'Audit log format invalid; existing data preserved')
        normalized = [{**entry, 'sequence': entry.get('sequence', index + 1)} for index, entry in enumerate(entries)]
        selected = [entry for entry in normalized if entry['sequence'] > after_sequence
                    and (ticket_id is None or entry.get('ticket') == ticket_id)
                    and (run_id is None or entry.get('run_id') == run_id)]
        # Cursor requests get the next page; initial requests get recent entries.
        page = selected[:limit] if after_sequence else selected[-limit:]
        return {'entries': page, 'latest_sequence': normalized[-1]['sequence'] if normalized else 0,
                'next_after_sequence': page[-1]['sequence'] if page else after_sequence}

    @app.get('/cash')
    async def cash():
        return await mcp('get_checking_balance', {})

    @app.get('/approvals')
    async def approvals(ticket_id: int | None = None):
        if ticket_id is not None:
            assignment_ticket(ticket_id)
        return await mcp('list_approval_requests', {'ticket_id': ticket_id})

    @app.post('/tickets/{ticket_id}/payments/prepare', dependencies=[Depends(require_human)])
    async def prepare_payment(ticket_id: int, body: PreparePaymentBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('request_payment_approval', {'ticket_id': ticket_id, **body.model_dump()}, ticket=ticket_id, audit=True)

    @app.post('/tickets/{ticket_id}/purchases/prepare', dependencies=[Depends(require_human)])
    async def prepare_purchase(ticket_id: int, body: PreparePurchaseBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('request_purchase_approval', {'ticket_id': ticket_id, **body.model_dump()}, ticket=ticket_id, audit=True)

    @app.post('/approvals/{approval_id}/approve', dependencies=[Depends(require_human)])
    async def approve(approval_id: str, body: ApprovalBody):
        assignment_ticket(body.ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            tool = 'approve_and_execute_payment' if body.request_type == 'payment' else 'approve_and_execute_purchase'
            return await mcp(tool, {'ticket_id': body.ticket_id, 'approval_id': approval_id, 'human_name': body.human_name,
                                    'human_capability': app.state.team._human_capability}, ticket=body.ticket_id, audit=True)

    @app.post('/approvals/{approval_id}/deny', dependencies=[Depends(require_human)])
    async def deny(approval_id: str, body: DenialBody):
        assignment_ticket(body.ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('deny_prepared_request', {'approval_id': approval_id, **body.model_dump(),
                            'human_capability': app.state.team._human_capability}, ticket=body.ticket_id, audit=True)

    @app.post('/tickets/{ticket_id}/resolution/prepare', dependencies=[Depends(require_human)])
    async def prepare_resolution(ticket_id: int, body: ResolutionProposalBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('prepare_resolution_review', {'ticket_id':ticket_id, **body.model_dump()}, ticket=ticket_id, audit=True)

    @app.post('/tickets/{ticket_id}/resolution/{review_id}/decision', dependencies=[Depends(require_human)])
    async def decide_resolution(ticket_id: int, review_id: str, body: ResolutionDecisionBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('decide_resolution_review', {'ticket_id':ticket_id,'review_id':review_id, **body.model_dump(),'human_capability':app.state.team._human_capability}, ticket=ticket_id, audit=True)

    @app.post('/tickets/{ticket_id}/resolution/{review_id}/simulated-receipt', dependencies=[Depends(require_human)])
    async def simulated_receipt(ticket_id: int, review_id: str, body: SimulatedReceiptBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('confirm_simulated_receipt_and_fulfill', {'ticket_id':ticket_id,'review_id':review_id, **body.model_dump(),'human_capability':app.state.team._human_capability}, ticket=ticket_id, audit=True)

    @app.post('/tickets/{ticket_id}/resolution/{review_id}/record-quote-decision', dependencies=[Depends(require_human)])
    async def record_quote_decision(ticket_id: int, review_id: str, body: QuoteDecisionBody):
        assignment_ticket(ticket_id)
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('record_conditional_quote_decision', {'ticket_id':ticket_id,'review_id':review_id, **body.model_dump(),'human_capability':app.state.team._human_capability}, ticket=ticket_id, audit=True)

    @app.post('/simulation/date', dependencies=[Depends(require_human)])
    async def simulation_date(body: SimulationDateBody):
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('advance_simulation_date', {**body.model_dump(),'human_capability':app.state.team._human_capability}, audit=True)

    @app.post('/recovery/committed-resolution', dependencies=[Depends(require_human)])
    async def recover_resolution(body: RecoveryBody):
        idle()
        async with app.state.operation_lock:
            idle()
            return await mcp('recover_committed_resolution', {**body.model_dump(),'human_capability':app.state.team._human_capability}, audit=True)

    @app.post('/reset', dependencies=[Depends(require_human)])
    async def reset(body: ResetBody):
        idle()
        async with app.state.operation_lock:
            idle()
            result = await mcp('reset_working_database', {**body.model_dump(), 'human_capability': app.state.team._human_capability}, audit=True)
            app.state.jobs.clear()
            return result

    return app


app = create_app()
