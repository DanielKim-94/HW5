"""Minimal Portkey routing diagnostics. No shop data, MCP changes, or alternate model."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-6-luna'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--responses', action='store_true')
    parser.add_argument('--provider', action='store_true')
    args = parser.parse_args()
    load_dotenv(ROOT.parent / '.env', override=False)
    key = os.environ['PORTKEY_API_KEY'].strip()
    headers = {'Authorization':'Bearer '+key, 'x-portkey-api-key':key,
               'x-portkey-trace-id':'hw5-model-check-'+str(uuid4())}
    if args.provider: headers['x-portkey-provider']='openai'
    endpoint='/responses' if args.responses else '/chat/completions'
    function={'name':'record_probe','description':'Return the diagnostic marker only; no operation will be executed.',
              'parameters':{'type':'object','properties':{'marker':{'type':'string'}},'required':['marker'],'additionalProperties':False},'strict':True}
    prompt='Routing diagnostic only. Call record_probe with marker verified. No shop data or operational action.'
    if args.responses:
        body={'model':MODEL,'input':prompt,'tools':[{'type':'function',**function}],
              'tool_choice':{'type':'function','name':'record_probe'},'max_output_tokens':256,'reasoning':{'effort':'low'},'store':False}
    else:
        body={'model':MODEL,'messages':[{'role':'user','content':prompt}],
              'tools':[{'type':'function','function':function}], 'tool_choice':{'type':'function','function':{'name':'record_probe'}},
              'max_completion_tokens':256,'reasoning_effort':'none'}
    evidence={'checked_utc':datetime.now(timezone.utc).isoformat(),'requested_model':MODEL,
              'endpoint':'https://api.portkey.ai/v1'+endpoint,'request_body':body,
              'request_headers':{k:('[redacted]' if k in ('Authorization','x-portkey-api-key') else v) for k,v in headers.items()},
              'shop_data_sent':False,'tools_executed':False}
    with httpx.Client(base_url='https://api.portkey.ai/v1',timeout=40,trust_env=False) as client:
        try:
            response=client.post(endpoint,headers=headers,json=body)
            evidence['http_status']=response.status_code
            safe_names=('x-request-id','request-id','x-portkey-trace-id','x-portkey-provider','x-portkey-config',
                        'x-portkey-cache-status','x-portkey-last-used-option-index','x-portkey-retry-attempt-count','x-portkey-response-status')
            evidence['response_headers']={k:v for k,v in response.headers.items() if k in safe_names}
            data=response.json()
            evidence['response_metadata']={k:data[k] for k in ('id','model','created','created_at','usage','status','error','system_fingerprint') if k in data}
            evidence['response_tool_calls']=data.get('choices',[{}])[0].get('message',{}).get('tool_calls',[]) if not args.responses else [o for o in data.get('output',[]) if o.get('type')=='function_call']
            returned=data.get('model','')
            evidence['model_matches']=returned==MODEL or returned.startswith(MODEL+'-')
            evidence['function_call_received']=bool(evidence['response_tool_calls'])
            evidence['verified']=response.is_success and evidence['model_matches'] and evidence['function_call_received']
        except Exception as exc:
            evidence['error']={'type':type(exc).__name__,'message':str(exc).replace(key,'[redacted]')}
            evidence['verified']=False
    path=ROOT/'output/model_routing_checks.json'
    records=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    records.append(evidence)
    path.write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(evidence,indent=2,ensure_ascii=True))


if __name__=='__main__': main()
