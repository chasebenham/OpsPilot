from datetime import datetime, timezone
from decimal import Decimal
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, ForeignKey, String, Text, DateTime, Boolean, CheckConstraint, JSON, Numeric, Integer, UniqueConstraint, Index, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
def utcnow(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass
class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("role IN ('Employee','Department Agent','Department Manager','Finance Approver','Operations Admin')", name="ck_user_role"),)
class Request(Base):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    human_readable_id: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    request_type: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("request_type IN ('IT Incident','Purchase Request','Cross-Department Project')", name="ck_request_type"),
        CheckConstraint("priority IN ('Low','Normal','High','Critical')", name="ck_priority"),
        CheckConstraint("status IN ('Submitted','Needs Information','Triaged','In Progress','Resolved','Closed','Cancelled')", name="ck_status"),
    )
class RequestEvent(Base):
    __tablename__ = "request_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

class AIAnalysis(Base):
    __tablename__ = 'ai_analyses'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey('requests.id', ondelete='CASCADE'), index=True)
    initiated_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(100))
    model_identifier: Mapped[str | None] = mapped_column(String(150))
    analysis_status: Mapped[str] = mapped_column(String(30), default='completed')
    structured_result: Mapped[dict] = mapped_column(JSON)
    validation_flags: Mapped[list] = mapped_column(JSON)
    accepted_fields: Mapped[list | None] = mapped_column(JSON)
    submitted_changes: Mapped[dict | None] = mapped_column(JSON)
    review_decision: Mapped[str | None] = mapped_column(String(30))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class UserCapability(Base):
    __tablename__ = 'user_capabilities'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    capability: Mapped[str] = mapped_column(String(50), primary_key=True)

class PolicyDecision(Base):
    __tablename__ = 'policy_decisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id', ondelete='CASCADE'), index=True)
    decision_type: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(50))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PurchaseDetail(Base):
    __tablename__ = 'purchase_details'
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id', ondelete='CASCADE'), primary_key=True)
    vendor: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    total_committed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    business_justification: Mapped[str | None] = mapped_column(Text)
    contract_term: Mapped[str | None] = mapped_column(String(200))
    commitment_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    requesting_department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Approval(Base):
    __tablename__ = 'approvals'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id', ondelete='CASCADE'), index=True)
    cycle: Mapped[int] = mapped_column(Integer)
    approval_stage: Mapped[int] = mapped_column(Integer)
    required_role_or_capability: Mapped[str] = mapped_column(String(50))
    assigned_approver_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20), default='Pending')
    decision_outcome: Mapped[str | None] = mapped_column(String(20))
    decision_actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('request_id','cycle','approval_stage', name='uq_approval_cycle_stage'), CheckConstraint("status IN ('Pending','Approved','Rejected','Cancelled','Invalidated')",name='ck_approval_status'))

class IncidentSLA(Base):
    __tablename__ = 'incident_slas'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    priority_at_evaluation: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(String(50))
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    first_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_status: Mapped[str] = mapped_column(String(30), default='None')
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('request_id','revision',name='uq_sla_revision'),)

class Escalation(Base):
    __tablename__ = 'escalations'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id', ondelete='CASCADE'), index=True)
    sla_id: Mapped[int] = mapped_column(ForeignKey('incident_slas.id', ondelete='CASCADE'))
    kind: Mapped[str] = mapped_column(String(50))
    explanation: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('sla_id','kind',name='uq_escalation_sla_kind'),)

class EvaluationRun(Base):
    __tablename__ = 'evaluation_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    evaluated_count: Mapped[int] = mapped_column(Integer)

class AIEvaluationRun(Base):
    __tablename__ = 'ai_evaluation_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(150))
    prompt_version: Mapped[str] = mapped_column(String(80))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20))
    configuration: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index('uq_ai_evaluation_one_running', 'status', unique=True, postgresql_where=text("status = 'Running'"), sqlite_where=text("status = 'Running'")),)

class AIEvaluationResult(Base):
    __tablename__ = 'ai_evaluation_results'
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('ai_evaluation_runs.id', ondelete='CASCADE'), index=True)
    case_id: Mapped[str] = mapped_column(String(80))
    expected: Mapped[dict] = mapped_column(JSON)
    actual: Mapped[dict | None] = mapped_column(JSON)
    error_category: Mapped[str | None] = mapped_column(String(50))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint('run_id', 'case_id', name='uq_ai_evaluation_case'),)

class ProjectWorkflow(Base):
    __tablename__='project_workflows'
    id: Mapped[int]=mapped_column(primary_key=True)
    request_id: Mapped[int]=mapped_column(ForeignKey('requests.id',ondelete='CASCADE'),unique=True,index=True)
    owner_user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    status: Mapped[str]=mapped_column(String(30),default='Draft',index=True)
    target_completion_date: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    __table_args__=(CheckConstraint("status IN ('Draft','Pending Review','Active','Blocked','Completed','Cancelled')",name='ck_project_workflow_status'),)
class WorkflowPlan(Base):
    __tablename__='workflow_plans'
    id: Mapped[int]=mapped_column(primary_key=True)
    workflow_id: Mapped[int]=mapped_column(ForeignKey('project_workflows.id',ondelete='CASCADE'),index=True)
    version: Mapped[int]=mapped_column(Integer)
    source: Mapped[str]=mapped_column(String(20))
    status: Mapped[str]=mapped_column(String(30),default='Draft')
    proposed_by_user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by_user_id: Mapped[int | None]=mapped_column(ForeignKey('users.id'))
    approved_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    source_hash: Mapped[str | None]=mapped_column(String(64))
    plan_data: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('workflow_id','version',name='uq_workflow_plan_version'),CheckConstraint("status IN ('Draft','Pending Review','Approved','Superseded')",name='ck_workflow_plan_status'))
class WorkflowTask(Base):
    __tablename__='workflow_tasks'
    id: Mapped[int]=mapped_column(primary_key=True)
    workflow_id: Mapped[int]=mapped_column(ForeignKey('project_workflows.id',ondelete='CASCADE'),index=True)
    plan_id: Mapped[int]=mapped_column(ForeignKey('workflow_plans.id',ondelete='CASCADE'),index=True)
    stable_task_key: Mapped[str]=mapped_column(String(80))
    title: Mapped[str]=mapped_column(String(200))
    description: Mapped[str]=mapped_column(Text)
    responsible_department_id: Mapped[int]=mapped_column(ForeignKey('departments.id'),index=True)
    assigned_user_id: Mapped[int | None]=mapped_column(ForeignKey('users.id'),index=True)
    status: Mapped[str]=mapped_column(String(30),index=True)
    priority: Mapped[str]=mapped_column(String(20))
    required: Mapped[bool]=mapped_column(Boolean,default=True)
    due_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    __table_args__=(UniqueConstraint('plan_id','stable_task_key',name='uq_workflow_task_key'),CheckConstraint("status IN ('Blocked','Ready','In Progress','Completed','Cancelled')",name='ck_workflow_task_status'))
class TaskDependency(Base):
    __tablename__='task_dependencies'
    id: Mapped[int]=mapped_column(primary_key=True)
    workflow_id: Mapped[int]=mapped_column(ForeignKey('project_workflows.id',ondelete='CASCADE'),index=True)
    predecessor_task_id: Mapped[int]=mapped_column(ForeignKey('workflow_tasks.id',ondelete='CASCADE'))
    successor_task_id: Mapped[int]=mapped_column(ForeignKey('workflow_tasks.id',ondelete='CASCADE'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('predecessor_task_id','successor_task_id',name='uq_task_dependency'),CheckConstraint('predecessor_task_id <> successor_task_id',name='ck_task_dependency_not_self'))
class WorkflowEvent(Base):
    __tablename__='workflow_events'
    id: Mapped[int]=mapped_column(primary_key=True)
    workflow_id: Mapped[int]=mapped_column(ForeignKey('project_workflows.id',ondelete='CASCADE'),index=True)
    task_id: Mapped[int | None]=mapped_column(ForeignKey('workflow_tasks.id',ondelete='CASCADE'))
    actor_id: Mapped[int | None]=mapped_column(ForeignKey('users.id'))
    event_type: Mapped[str]=mapped_column(String(60))
    structured_details: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
