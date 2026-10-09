"""Agent tools route every shop lookup/change through the shared MCP client."""
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from .models import AgentDeps, AgentRole, DelegationTopic, ShopTool


ROLE_TOPICS = {
    AgentRole.BOSS: {'coordination', 'pricing'},
    AgentRole.INVENTORY: {'stock', 'vendor_shipping'},
    AgentRole.ACCOUNTING: {'invoice', 'cash', 'pricing'},
    AgentRole.FACILITIES: {'rent'},
    AgentRole.CUSTOMER_SERVICE: {'customer_draft'},
}
TICKET_TOPICS = {
    'customer_order': {'coordination', 'stock', 'vendor_shipping', 'invoice', 'cash', 'customer_draft'},
    'rent_notice': {'coordination', 'rent', 'cash', 'invoice', 'customer_draft'},
    'price_override': {'coordination', 'pricing', 'stock', 'vendor_shipping', 'cash', 'customer_draft'},
}


async def shop_tool(ctx: RunContext[AgentDeps], tool_name: ShopTool, arguments: dict[str, Any]) -> dict:
    """Call an MCP shop tool. Include this run's ticket_id in arguments. Available:
    context tools; vendor status(vendor_id); request_payment_approval(kind,ref_id,
    account,reason); get_payment_approval/execute_approved_payment(approval_id);
    save_message_draft(recipient,body); save_quote_draft(unit_price,rationale);
    plan_vendor_shipment(vendor_id,qty,supplier_evidence); fulfill_customer_order;
    get_cash_obligations; list_approval_requests; request_purchase_approval(vendor_id,
    qty,supplier_evidence,account). Purchase preparation never debits cash.
    No model can record a human decision or initialize the database.
    """
    if arguments.get('ticket_id') != ctx.deps.shared.ticket_id:
        raise ModelRetry('Tool calls must use the current ticket_id only')
    if 'human_capability' in arguments or 'human_name' in arguments:
        raise ModelRetry('Human approval cannot be supplied by an agent')
    return await ctx.deps.shared.team.call_shop(ctx.deps, tool_name, arguments)


async def delegate(ctx: RunContext[AgentDeps], target: AgentRole, ticket_id: int,
                   topic: DelegationTopic, task: str) -> dict:
    """Ask any other role for relevant help on this same ticket. Topic must match
    that role and ticket. No self/ancestor recursion, cross-ticket work, or unrelated tasks.
    """
    shared = ctx.deps.shared
    if ticket_id != shared.ticket_id:
        raise ModelRetry('Delegation cannot switch tickets')
    if target in ctx.deps.chain:
        raise ModelRetry('Delegate to a role outside the current call chain')
    if topic not in ROLE_TOPICS[target] or topic not in TICKET_TOPICS.get(shared.ticket_type, set()):
        raise ModelRetry('Delegation topic must fit the target role and current ticket')
    if not task.strip() or len(task) > 1500:
        raise ModelRetry('Provide a focused task of 1–1500 characters')
    limits = shared.team.limits
    if len(ctx.deps.chain) - 1 >= limits.delegation_depth or shared.delegations >= limits.delegations:
        raise ModelRetry('Delegation budget exhausted; return current findings and blockers')
    cache_key = (target.value, topic)
    if cache_key in shared.specialist_reports:
        report = shared.specialist_reports[cache_key]
        shared.team.audit.append(ticket=ticket_id, agent=ctx.deps.role.value, event='delegation_reused', run_id=shared.run_id,
            delegation={'from':ctx.deps.role.value,'to':target.value,'topic':topic,'task':task}, results=report)
        return report
    shared.delegations += 1
    delegation = {'from': ctx.deps.role.value, 'to': target.value,
                  'ticket': ticket_id, 'topic': topic, 'task': task}
    shared.team.audit.append(ticket=ticket_id, agent=ctx.deps.role.value, event='delegation_requested',
                             run_id=shared.run_id, delegation=delegation)
    child = AgentDeps(shared, target, ctx.deps.chain + (target,))
    report = await shared.team.run_agent(child, f'Ticket {ticket_id}. Topic: {topic}. Task: {task}')
    shared.team.audit.append(ticket=ticket_id, agent=ctx.deps.role.value, event='delegation_returned',
                             run_id=shared.run_id, delegation=delegation, results=report.model_dump(mode='json'))
    shared.specialist_reports[cache_key] = report.model_dump(mode='json')
    return report.model_dump(mode='json')
