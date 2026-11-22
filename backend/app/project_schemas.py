from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .schemas import Priority
class TaskDraft(BaseModel):
    key: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(min_length=1,max_length=5000)
    department_id: int = Field(gt=0)
    assigned_user_id: int | None = Field(default=None,gt=0)
    priority: Priority = 'Normal'
    required: bool = True
    due_at: datetime | None = None
    depends_on: list[str] = Field(default_factory=list,max_length=50)
    @field_validator('title','description')
    @classmethod
    def nonblank(cls,v):
        if not v.strip(): raise ValueError('Must not be blank')
        return v.strip()
    @field_validator('due_at')
    @classmethod
    def aware_time(cls,v):
        if v and v.tzinfo is None: raise ValueError('Due date must include a timezone')
        return v
class PlanDraft(BaseModel):
    objective: str = Field(min_length=1,max_length=5000)
    tasks: list[TaskDraft] = Field(min_length=1,max_length=50)
    risks: list[str] = Field(default_factory=list,max_length=30)
    missing_information: list[str] = Field(default_factory=list,max_length=30)
    explanation: str = Field(default='',max_length=5000)
    target_completion_date: datetime | None = None
    @field_validator('objective')
    @classmethod
    def nonblank(cls,v):
        if not v.strip(): raise ValueError('Objective must not be blank')
        return v.strip()
    @field_validator('target_completion_date')
    @classmethod
    def aware_time(cls,v):
        if v and v.tzinfo is None: raise ValueError('Target date must include a timezone')
        return v
class TaskTransition(BaseModel):
    status: Literal['In Progress','Completed','Cancelled']
    note: str | None = Field(default=None,max_length=5000)
class TaskAssignment(BaseModel):
    assigned_user_id: int | None = Field(default=None,gt=0)
class TaskDepartment(BaseModel):
    department_id: int = Field(gt=0)
class TaskNote(BaseModel):
    note: str = Field(min_length=1,max_length=5000)
    @field_validator('note')
    @classmethod
    def nonblank(cls,v):
        if not v.strip(): raise ValueError('Note must not be blank')
        return v.strip()
