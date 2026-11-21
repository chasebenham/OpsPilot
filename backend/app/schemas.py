from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
Type = Literal["IT Incident", "Purchase Request", "Cross-Department Project"]
Priority = Literal["Low", "Normal", "High", "Critical"]
Status = Literal["Submitted", "Needs Information", "Triaged", "In Progress", "Resolved", "Closed", "Cancelled"]
class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)
class DepartmentOut(ORM):
    id: int
    name: str
class UserOut(ORM):
    id: int
    name: str
    email: str
    role: str
    department_id: int
    active: bool
class RequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    request_type: Type
    priority: Priority = "Normal"
    analysis_id: int | None = Field(default=None, gt=0)
    accepted_ai_fields: list[Literal['request_type', 'priority', 'department']] = Field(default_factory=list, max_length=3)
    @field_validator("title", "description")
    @classmethod
    def strip_nonempty(cls, v):
        v = v.strip()
        if not v: raise ValueError("Must not be blank")
        return v
class RequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    priority: Priority | None = None
    @field_validator("title", "description")
    @classmethod
    def nonblank(cls, v):
        if v is not None and not v.strip(): raise ValueError("Must not be blank")
        return v.strip() if v else v
class Assignment(BaseModel):
    department_id: int | None
    user_id: int | None = None
class Transition(BaseModel):
    status: Status
class Clarification(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    @field_validator("message")
    @classmethod
    def nonblank(cls, v):
        if not v.strip(): raise ValueError("Must not be blank")
        return v.strip()
class RequestOut(ORM):
    id: int
    human_readable_id: str
    title: str
    description: str
    request_type: str
    priority: str
    status: str
    requester_id: int
    assigned_department_id: int | None
    assigned_user_id: int | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
class EventOut(ORM):
    id: int
    request_id: int
    actor_id: int | None
    event_type: str
    previous_value: str | None
    new_value: str | None
    created_at: datetime
class RequestPage(BaseModel):
    items: list[RequestOut]
    total: int
    page: int
    page_size: int

