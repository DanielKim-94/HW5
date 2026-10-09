"""Validated dashboard request bodies; human credentials are not model inputs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .models import AgentRole


class RequestBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RunTicketBody(RequestBody):
    task: str = Field(min_length=1, max_length=4000)
    agent: AgentRole = AgentRole.BOSS
    prepare_payments: bool = True

    @field_validator('task')
    @classmethod
    def meaningful_task(cls, value):
        if not value.strip():
            raise ValueError('Task must not be blank')
        return value


class PreparePaymentBody(RequestBody):
    kind: Literal['invoice', 'rent']
    ref_id: int = Field(gt=0)
    account: str = Field(default='checking', min_length=1, max_length=100)
    reason: str = Field(default='', max_length=2000)


class PreparePurchaseBody(RequestBody):
    vendor_id: int = Field(gt=0)
    qty: int = Field(gt=0)
    supplier_evidence: str = Field(min_length=1, max_length=2000)
    account: str = Field(default='checking', min_length=1, max_length=100)


class ApprovalBody(RequestBody):
    ticket_id: int = Field(gt=0)
    request_type: Literal['payment', 'purchase']
    human_name: str = Field(min_length=1, max_length=200)
    approve: Literal[True]

    @field_validator('human_name')
    @classmethod
    def human_identity(cls, value):
        if not value.strip():
            raise ValueError('Human name must not be blank')
        return value.strip()


class DenialBody(RequestBody):
    ticket_id: int = Field(gt=0)
    request_type: Literal['payment', 'purchase']
    human_name: str = Field(min_length=1, max_length=200)


class ResetBody(RequestBody):
    confirmation: Literal['RESET_WORKING_DATABASE']


class ResolutionProposalBody(RequestBody):
    kind: Literal['simulated_restock','pricing_decision']
    rationale: str = Field(min_length=1,max_length=2000)
    unit_price: str | None = None

class ResolutionDecisionBody(RequestBody):
    approve: bool
    human_name: str = Field(min_length=1,max_length=200)
    acknowledge_completion_rule: Literal[True]

class SimulationDateBody(RequestBody):
    new_date: str
    reason: str = Field(min_length=1,max_length=2000)

class SimulatedReceiptBody(RequestBody):
    human_name: str = Field(min_length=1,max_length=200)
    confirm_simulation: Literal[True]

class QuoteDecisionBody(RequestBody):
    human_name: str = Field(min_length=1,max_length=200)

class RecoveryBody(RequestBody):
    expected_reset_sequence: int = Field(ge=0)
    reason: str = Field(min_length=1,max_length=2000)
