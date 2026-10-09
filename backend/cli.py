"""Local trusted entry points. Running an agent is separate from approving a payment."""
import argparse
import asyncio
import json

from .agents import ShopTeam
from .models import AgentRole, HumanDecision


async def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('initialize')
    run = sub.add_parser('run')
    run.add_argument('ticket_id', type=int)
    run.add_argument('task')
    run.add_argument('--agent', choices=[r.value for r in AgentRole], default='Boss')
    decide = sub.add_parser('decide')
    decide.add_argument('ticket_id', type=int)
    decide.add_argument('approval_id')
    decide.add_argument('--human-name', required=True)
    choice = decide.add_mutually_exclusive_group(required=True)
    choice.add_argument('--approve', action='store_true')
    choice.add_argument('--deny', action='store_true')
    args = parser.parse_args()
    async with ShopTeam() as team:
        if args.command == 'initialize':
            result = await team.initialize()
        elif args.command == 'run':
            result = (await team.run_ticket(args.ticket_id, args.task, AgentRole(args.agent))).model_dump(mode='json')
        else:
            result = await team.human_decision(HumanDecision(ticket_id=args.ticket_id, approval_id=args.approval_id,
                                                           approve=args.approve, human_name=args.human_name))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
