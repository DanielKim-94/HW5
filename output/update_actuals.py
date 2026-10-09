"""Render only stored actual audit/HTTP evidence; never infer resolution."""
from pathlib import Path
import html
import json
import re

root = Path(__file__).resolve().parents[1]
out = root / 'output'
manifest = json.loads((out/'clean_run_manifest.json').read_text(encoding='utf-8'))
diagnostic = json.loads((root/manifest['diagnostic_snapshot']/'run_summary.json').read_text(encoding='utf-8'))
page = (out/'desk_tickets.html').read_text(encoding='utf-8')
esc = lambda v: html.escape(str(v))
explanations = {
    101: 'Audit-file replacement failed with Windows PermissionError (sequence 26). No payment or fulfillment recorded.',
    102: 'Recovered invalid lease_id argument, then token limit exceeded at 24,569 (sequence 109). Rent request was prepared (94) and removed by a later reset (114–115); no payment recorded.',
    103: 'Inventory verified a 12-unit size-M shortage; Accounting identified missing discount policy. Boss exceeded the token limit at 27,679 (188). No payment or resolution recorded.',
}
for ticket in (101,102,103):
    failed = [(rid,run) for rid,run in diagnostic.items() if run['ticket']==ticket]
    body = '<h4>Earlier failed attempt</h4><p>' + esc(explanations[ticket]) + '</p>'
    for rid,run in failed:
        body += '<p><code>'+esc(rid)+'</code> · first audit sequence '+str(run['first_sequence'])+'</p>'
    body += '<h4>Clean batch</h4><p><code>'+esc(manifest['batch_id'])+'</code></p>'
    runs = [run for run in manifest['runs'] if run['ticket']==ticket]
    if not runs:
        body += '<p>Not run yet. No new result or resolution screenshot exists.</p>'
    for run in runs:
        job=run.get('latest',run['queued']); report=job.get('result',{})
        body += '<p>Run <code>'+esc(run['run_id'])+'</code>: '+esc(job['status'])+'. '+esc(report.get('summary',job.get('error',{}).get('message','')))+' </p>'
    record=next(t for t in manifest['current_tickets']['tickets'] if t['id']==ticket)
    body+='<p>Actual backend ticket status: <strong>'+esc(record['status'])+'</strong>.</p>'
    screenshot=manifest['resolved_screenshots'].get(str(ticket))
    if screenshot:
        relative=screenshot['path'].removeprefix('output/')
        body+='<p><a href="'+esc(relative)+'">Actual resolved dashboard screenshot</a> · '+esc(screenshot['captured_utc'])+'</p>'
    page=re.sub(r'(<div class="actual-body" data-ticket="'+str(ticket)+r'">).*?(</div>)',lambda m:m[1]+body+m[2],page,flags=re.S)
balance=manifest['current_cash']['account']['balance']
cash='<h2>Cash</h2><p>Clean-reset baseline: 3,400.00. Current backend checking balance: <strong>'+f'{balance:,.2f}'+'</strong>. Shop date: '+esc(manifest['current_cash']['business_date'])+'. Currency unspecified.</p>'
cash+='<p>The earlier failed-attempt snapshot records zero payments. Approval preparation does not debit cash. This section reports actual backend balances, not expected payment arithmetic.</p>'
for request in manifest['current_approvals']['payments']+manifest['current_approvals']['purchases']:
    cash+='<p>Request <code>'+esc(request['id'])+'</code> · ticket '+str(request['ticket_id'])+' · '+esc(request['status'])+' · amount '+esc(request['amount'])+'</p>'
page=re.sub(r'(<section id="panel-cash"[^>]*>).*?(</section>)',lambda m:m[1]+'<article class="card">'+cash+'</article>'+m[2],page,flags=re.S)
page=page.replace('Actual sections intentionally empty','Actual sections use recorded evidence')
(out/'desk_tickets.html').write_text(page,encoding='utf-8')
evidence={'diagnostic_snapshot':manifest['diagnostic_snapshot'],'failed_attempts':diagnostic,'clean_batch':manifest,
          'limitations':['No failed-run screenshots were supplied.','Only backend-confirmed resolved tickets have resolution screenshots.','Prepared requests are not executed payments.']}
audit=json.loads((out/'audit_trail.json').read_text(encoding='utf-8'))
audit=audit if isinstance(audit,list) else audit['entries']
run_ids={run['run_id'] for run in manifest['runs']}
evidence['clean_run_events']=[entry for entry in audit if entry['run_id'] in run_ids]
evidence['actual_model_responses']=[entry for entry in evidence['clean_run_events'] if entry['event']=='model_http_response']
(out/'run_evidence.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print('Actual/Cash updated from stored evidence.')
