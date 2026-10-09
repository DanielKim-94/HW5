"""Verify actual PydanticAI configuration and routing without shop/MCP operations."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from pydantic import BaseModel
from pydantic_ai import Agent

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.agents import ShopTeam
from backend.config import MODEL_NAME, create_model, model_matches


class ProbeReport(BaseModel):
    marker: str


async def main():
    records=[]
    model,client=create_model(lambda event,data:records.append({'event':event,'data':data}))
    team=ShopTeam()
    try:
        team.build_agents()
        agent_models={role.value:agent.model.model_name for role,agent in team.agents.items()}
        probe=Agent(model, output_type=ProbeReport, model_settings={'max_tokens':256,'parallel_tool_calls':False})
        result=await probe.run('Routing test only. Return marker verified. No shop data or operations.')
        reported=[entry['data']['reported'] for entry in records if entry['event']=='model_http_response']
        evidence={'checked_utc':datetime.now(timezone.utc).isoformat(),'configured_model':MODEL_NAME,
            'agent_models':agent_models,'metadata':records,'output':result.output.model_dump(),
            'reported_models':reported,'verified':bool(reported) and all(model_matches(m) for m in reported)
                and all(m==MODEL_NAME for m in agent_models.values()),'shop_operations':False}
    except Exception as exc:
        evidence={'checked_utc':datetime.now(timezone.utc).isoformat(),'configured_model':MODEL_NAME,
            'metadata':records,'verified':False,'error':{'type':type(exc).__name__,'message':str(exc)},'shop_operations':False}
    finally:
        await client.close()
        if team._http_client: await team._http_client.close()
    (ROOT/'output/agent_model_verification.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__': asyncio.run(main())
