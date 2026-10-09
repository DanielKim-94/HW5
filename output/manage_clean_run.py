"""Human-side evidence helper. Never approves payments; API uses MCP for changes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.audit import AuditTrail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['reset', 'run', 'status'])
    parser.add_argument('--ticket', type=int, choices=[101, 102, 103])
    parser.add_argument('--task')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env', override=False)
    load_dotenv(ROOT.parent / '.env', override=False)
    token = os.environ.get('CAMPUS_HUMAN_API_TOKEN') or (ROOT / 'backend/.human_api_token').read_text().strip()
    path = ROOT / 'output/clean_run_manifest.json'
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=30,
                      headers={'Authorization': 'Bearer ' + token}) as client:
        def get(route):
            r = client.get(route); r.raise_for_status(); return r.json()
        def post(route, body):
            r = client.post(route, json=body); r.raise_for_status(); return r.json()
        if args.action == 'reset':
            if path.exists():
                raise RuntimeError('Clean-run manifest exists; do not reset an ongoing run implicitly')
            audit = json.loads((ROOT / 'output/audit_trail.json').read_text(encoding='utf-8'))
            previous = audit if isinstance(audit, list) else audit['entries']
            prefix_hash = hashlib.sha256(json.dumps(previous, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            reset = post('/reset', {'confirmation': 'RESET_WORKING_DATABASE'})
            manifest = {'batch_id': 'clean-' + str(uuid4()), 'started_utc': datetime.now(timezone.utc).isoformat(),
                        'diagnostic_snapshot': 'output/diagnostics/20261009T040935Z',
                        'preserved_audit_count': len(previous), 'preserved_audit_prefix_sha256': prefix_hash,
                        'reset_result': reset, 'runs': [], 'resolved_screenshots': {}}
            AuditTrail(ROOT / 'output/audit_trail.json').append(ticket=None, agent='Human', event='clean_batch_started',
                run_id=manifest['batch_id'], results={'diagnostic_snapshot':manifest['diagnostic_snapshot'],
                'preserved_audit_count':len(previous), 'reset_confirmed':True})
            manifest['initial_tickets'] = get('/tickets')
            manifest['initial_cash'] = get('/cash')
            manifest['initial_approvals'] = get('/approvals')
        else:
            manifest = json.loads(path.read_text(encoding='utf-8'))
            if args.action == 'run':
                if not args.ticket or not args.task: parser.error('run requires --ticket and --task')
                task = f"Clean batch {manifest['batch_id']}. " + args.task
                job = post(f'/tickets/{args.ticket}/run', {'task':task, 'agent':'Boss'})
                manifest['runs'].append({'run_id':job['run_id'],'ticket':args.ticket,'task':task,'queued':job})
            for run in manifest['runs']:
                run['latest'] = get('/runs/' + run['run_id'])
        manifest['current_tickets'] = get('/tickets')
        manifest['current_cash'] = get('/cash')
        manifest['current_approvals'] = get('/approvals')
        audit = json.loads((ROOT / 'output/audit_trail.json').read_text(encoding='utf-8'))
        entries = audit if isinstance(audit,list) else audit['entries']
        prefix = entries[:manifest['preserved_audit_count']]
        actual = hashlib.sha256(json.dumps(prefix,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if actual != manifest['preserved_audit_prefix_sha256']:
            raise RuntimeError('Earlier audit entries changed')
        manifest['audit_prefix_verified'] = True
        path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(manifest,indent=2,ensure_ascii=True))


if __name__ == '__main__': main()
