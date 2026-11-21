from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .schemas import Type, Priority
DepartmentName = Literal['IT', 'Finance', 'Marketing', 'Operations', 'People & HR']
class ExtractedDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    affected_system: str | None
    affected_users_or_teams: str | None
    impact_description: str | None
    outage_start_time: str | None
    workaround_available: str | None
    security_concern: str | None
    vendor: str | None
    purchase_description: str | None
    total_committed_amount: str | None
    currency: str | None
    business_justification: str | None
    contract_term: str | None
    requested_by_department: str | None
    objective: str | None
    requested_deliverables: str | None
    participating_departments: str | None
    requested_deadline: str | None
    business_impact: str | None
    known_dependencies: str | None
class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_type: Type
    suggested_priority: Priority
    suggested_department: DepartmentName
    summary: str
    business_impact: str | None
    extracted_details: ExtractedDetails
    missing_information: list[str]
    explanation: str
    needs_human_review: bool
class AnalyzeDraft(BaseModel):
    description: str = Field(min_length=1, max_length=10000)
    title: str | None = Field(default=None, max_length=200)
    request_type: Type | None = None
    @field_validator('description')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Description cannot be blank')
        return value.strip()
class ReviewInput(BaseModel):
    analysis_id: int = Field(gt=0)
    accepted_fields: list[Literal['request_type','priority','department']] = Field(default_factory=list, max_length=3)
class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_id: int | None
    initiated_by_user_id: int
    model_name: str
    model_identifier: str | None
    analysis_status: str
    structured_result: AnalysisResult
    validation_flags: list[str]
    accepted_fields: list[str] | None
    submitted_changes: dict | None
    review_decision: str | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: __import__('datetime').datetime
    reviewed_at: __import__('datetime').datetime | None
