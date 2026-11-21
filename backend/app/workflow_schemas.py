from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, field_validator

class PurchaseInput(BaseModel):
    vendor: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    total_committed_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    currency: str | None = Field(default=None, max_length=3)
    business_justification: str | None = Field(default=None, max_length=10000)
    contract_term: str | None = Field(default=None, max_length=200)
    commitment_confirmed: bool = False
    @field_validator('total_committed_amount', mode='before')
    @classmethod
    def no_float(cls, value):
        if isinstance(value, float): raise ValueError('Send monetary amounts as decimal strings')
        return value
    @field_validator('vendor','description','currency','business_justification','contract_term')
    @classmethod
    def strip(cls, value): return value.strip() or None if value is not None else None
class OverrideInput(BaseModel):
    department_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=2000)
    @field_validator('reason')
    @classmethod
    def nonblank(cls, v):
        if len(v.strip())<3: raise ValueError('Provide a reason')
        return v.strip()
class ApprovalDecisionInput(BaseModel):
    decision: Literal['Approved','Rejected']
    reason: str | None = Field(default=None, max_length=2000)
    @field_validator('reason')
    @classmethod
    def strip_reason(cls, v): return v.strip() or None if v is not None else None
class ReasonInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3: raise ValueError('Provide a reason')
        return value.strip()
