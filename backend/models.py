"""Shared typed contracts for the five agents and trusted human entry point."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict
from pydantic_ai.usage import RunUsage


class AgentRole(str, Enum):
    BOSS = 'Boss'
    INVENTORY = 'Inventory'
    ACCOUNTING = 'Accounting'
    FACILITIES = 'Facilities'
    CUSTOMER_SERVICE = 'Customer Service'


DelegationTopic = Literal['coordination', 'stock', 'vendor_shipping', 'invoice', 'cash', 'rent', 'pricing', 'customer_draft']
ShopTool = Literal[
    'prepare_resolution_review', 'get_customer_order_context', 'get_rent_payment_context', 'get_bulk_pricing_context',
    'get_ticket_context', 'get_vendor_shipping_status', 'request_payment_approval',
    'get_payment_approval', 'execute_approved_payment', 'save_message_draft',
    'save_quote_draft', 'plan_vendor_shipment', 'fulfill_customer_order',
    'get_cash_obligations', 'request_purchase_approval', 'list_approval_requests',
]


class AgentReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticket_id: int
    agent: AgentRole
    summary: str = Field(max_length=3000)
    status: Literal['investigating', 'blocked', 'awaiting_human', 'draft_ready', 'resolved']
    evidence: list[str] = Field(default_factory=list, max_length=15)
    uncertainties: list[str] = Field(default_factory=list, max_length=15)
    approval_request_ids: list[str] = Field(default_factory=list, max_length=10)
    next_actions: list[str] = Field(default_factory=list, max_length=10)


class RunLimits(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_requests: int = Field(default=20, ge=1, le=20)
    tool_calls: int = Field(default=30, ge=1, le=50)
    total_tokens: int = Field(default=40000, ge=1000, le=40000)
    output_tokens_per_request: int = Field(default=1500, ge=200, le=2000)
    loop_steps: int = Field(default=60, ge=1, le=100)
    delegations: int = Field(default=8, ge=0, le=12)
    delegation_depth: int = Field(default=3, ge=0, le=4)
    wall_seconds: int = Field(default=180, ge=10, le=300)


@dataclass
class SharedRun:
    ticket_id: int
    ticket_type: str
    team: Any
    run_id: str = field(default_factory=lambda: str(uuid4()))
    usage: RunUsage = field(default_factory=RunUsage)
    steps: int = 0
    delegations: int = 0
    mcp_calls: int = 0
    prepare_payments: bool = True
    specialist_reports: dict = field(default_factory=dict)


@dataclass
class AgentDeps:
    shared: SharedRun
    role: AgentRole
    chain: tuple[AgentRole, ...]


class HumanDecision(BaseModel):
    ticket_id: int
    approval_id: str
    approve: bool
    human_name: str = Field(min_length=1, max_length=200)
