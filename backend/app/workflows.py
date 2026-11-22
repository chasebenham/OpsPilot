"""Deterministic workflows. Callers own transactions and lock the request row."""
from datetime import datetime, timezone
from sqlalchemy import select, func
from fastapi import HTTPException
from .models import (Department, User, UserCapability, Request, RequestEvent, PurchaseDetail, Approval, PolicyDecision, IncidentSLA, Escalation, EvaluationRun, utcnow)
from .policy import POLICY_VERSION, ROUTES, approval_stages, response_deadline

def aware(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def audit(db, req, kind, value, actor=None):
    db.add(RequestEvent(request_id=req.id,actor_id=actor.id if actor else None,event_type=kind,new_value=value))
    req.updated_at=utcnow()
def record(db, req, kind, outcome, explanation, actor=None):
    db.add(PolicyDecision(request_id=req.id,decision_type=kind,outcome=outcome,explanation=explanation,policy_version=POLICY_VERSION,actor_id=actor.id if actor else None))
    audit(db,req,'policy_'+kind,explanation,actor)
def route(db, req):
    # Never overwrite an existing or manually overridden department on reevaluation.
    if req.assigned_department_id is not None: return False
    previous=db.scalar(select(PolicyDecision).where(PolicyDecision.request_id==req.id,PolicyDecision.decision_type=='routing',PolicyDecision.outcome=='routed'))
    if previous: return False
    destination=ROUTES.get(req.request_type)
    department=db.scalar(select(Department).where(Department.name==destination)) if destination else None
    if not department:
        last=db.scalar(select(PolicyDecision).where(PolicyDecision.request_id==req.id,PolicyDecision.decision_type=='routing').order_by(PolicyDecision.id.desc()))
        if not last or last.outcome!='manual_triage': record(db,req,'routing','manual_triage','Automatic routing unavailable: destination or request type is not configured.')
        return False
    req.assigned_department_id=department.id
    record(db,req,'routing','routed',f'Automatically routed to {department.name} intake using {POLICY_VERSION}.')
    return True

def latest_sla(db, request_id):
    return db.scalar(select(IncidentSLA).where(IncidentSLA.request_id==request_id).order_by(IncidentSLA.revision.desc()))
def add_escalation(db, req, sla, kind, explanation, now):
    db.flush()
    found=db.scalar(select(Escalation).where(Escalation.sla_id==sla.id,Escalation.kind==kind))
    if found: return False
    db.add(Escalation(request_id=req.id,sla_id=sla.id,kind=kind,explanation=explanation,policy_version=POLICY_VERSION,created_at=now))
    sla.escalation_status='Escalated'
    audit(db,req,'incident_escalated',explanation)
    return True

def evaluate_one(db, req, sla, now):
    if not sla: return
    now=aware(now); due=aware(sla.response_due_at)
    if req.status in ('Resolved','Closed','Cancelled'):
        sla.last_evaluated_at=now
        return
    if not sla.first_acknowledged_at and req.priority=='Critical': add_escalation(db,req,sla,'critical','Critical incident requires immediate manager attention and human review.',now)
    if not sla.first_acknowledged_at and now>due:
        if not sla.breached_at: sla.breached_at=due
        add_escalation(db,req,sla,'overdue','Initial response is overdue and unacknowledged.',now)
    if not sla.first_acknowledged_at and req.assigned_user_id is None:
        add_escalation(db,req,sla,'unassigned','Incident has no individual owner; manual assignment is required.',now)
    sla.last_evaluated_at=now

def make_sla(db, req, now=None):
    now=aware(now or utcnow()); old=latest_sla(db,req.id)
    # Priority revisions use the original submission time; history remains immutable.
    sla=IncidentSLA(request_id=req.id,revision=(old.revision+1 if old else 1),priority_at_evaluation=req.priority,policy_version=POLICY_VERSION,response_due_at=response_deadline(aware(req.created_at),req.priority),first_acknowledged_at=old.first_acknowledged_at if old else None,acknowledged_by_id=old.acknowledged_by_id if old else None,created_at=now)
    if sla.first_acknowledged_at:
        sla.escalation_status='Acknowledged'
        if aware(sla.first_acknowledged_at)>aware(sla.response_due_at): sla.breached_at=sla.response_due_at
    db.add(sla); db.flush()
    record(db,req,'sla','evaluated',f'{req.priority} initial response deadline calculated using {POLICY_VERSION}.')
    evaluate_one(db,req,sla,now)
    return sla

def required_fields(p):
    if p is None: return ['purchase details']
    missing=[label for name,label in [('vendor','vendor'),('description','purchase description'),('total_committed_amount','total committed amount'),('currency','currency'),('business_justification','business justification'),('contract_term','contract term')] if not getattr(p,name)]
    if p and not p.commitment_confirmed: missing.append('confirmation of full contract commitment')
    if p and p.currency and p.currency!='USD': missing.append('supported USD currency')
    return missing

def latest_cycle(db, reqid): return db.scalar(select(func.max(Approval.cycle)).where(Approval.request_id==reqid)) or 0
def stages_for(db,reqid):
    cycle=latest_cycle(db,reqid)
    return db.scalars(select(Approval).where(Approval.request_id==reqid,Approval.cycle==cycle).order_by(Approval.approval_stage)).all() if cycle else []
def overall(db,reqid):
    rows=stages_for(db,reqid)
    if not rows: return 'Needs information'
    if any(r.status=='Rejected' for r in rows): return 'Rejected'
    if all(r.status=='Approved' for r in rows): return 'Authorized'
    if any(r.status=='Invalidated' for r in rows): return 'Needs resubmission'
    if any(r.status=='Cancelled' for r in rows): return 'Cancelled'
    return 'Pending'
def approver_for(db, req, dept_id, role):
    q=select(User).where(User.active.is_(True),User.id!=req.requester_id)
    if role=='Department Manager': q=q.where(User.role==role, User.department_id==dept_id)
    elif role=='Finance Approver': q=q.where(User.role==role)
    else: q=q.join(UserCapability,UserCapability.user_id==User.id).where(UserCapability.capability==role)
    return db.scalar(q.order_by(User.id))
def is_eligible(db, req, dept_id, role, user):
    if not user.active or user.id == req.requester_id: return False
    if role == 'Department Manager': return user.role == role and user.department_id == dept_id
    if role == 'Finance Approver': return user.role == role
    if role in ('Operations Director','Executive Approver'): return db.get(UserCapability,(user.id,role)) is not None
    return False
def invalidate(db,req,actor):
    rows=stages_for(db,req.id)
    if any(r.status!='Invalidated' for r in rows):
        for row in rows:
            if row.status in ('Approved','Rejected') and row.decision_outcome is None: row.decision_outcome=row.status
            if row.status!='Invalidated': row.status='Invalidated'
        record(db,req,'approval','invalidated','Purchase details changed; a new approval cycle is required.',actor)

def generate_approvals(db,req,actor):
    details=db.get(PurchaseDetail,req.id)
    missing=required_fields(details)
    if missing:
        record(db,req,'approval','on_hold','Approval on hold: '+', '.join(missing)+'.',actor)
        return []
    if overall(db,req.id) in ('Pending','Authorized') and stages_for(db,req.id): raise HTTPException(409,'Current approval cycle is already active')
    cycle=latest_cycle(db,req.id)+1
    rows=[]
    for position,role in enumerate(approval_stages(details.total_committed_amount,details.currency),1):
        person=approver_for(db,req,details.requesting_department_id,role)
        row=Approval(request_id=req.id,cycle=cycle,approval_stage=position,required_role_or_capability=role,assigned_approver_id=person.id if person else None,status='Pending',policy_version=POLICY_VERSION)
        db.add(row); rows.append(row)
    record(db,req,'approval','generated',f'Approval cycle {cycle} created; {len(rows)} sequential stage(s) required.',actor)
    if rows:
        audit(db,req,'approval_stage_ready',f'Cycle {cycle}, stage 1: {rows[0].required_role_or_capability} ready for review.')
    return rows

def evaluate_all(db, now=None):
    now=aware(now or utcnow())
    ids=db.scalars(select(Request.id).where(Request.request_type=='IT Incident').order_by(Request.id)).all()
    for rid in ids:
        req=db.scalar(select(Request).where(Request.id==rid).with_for_update())
        evaluate_one(db,req,latest_sla(db,rid),now)
    db.add(EvaluationRun(completed_at=now,evaluated_count=len(ids)))
    return len(ids)
