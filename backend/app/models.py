from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, ForeignKey, String, Text, DateTime, Boolean, CheckConstraint, JSON
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
