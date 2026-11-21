import logging
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request as HTTPRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .models import SessionLocal, Department, User, Request, RequestEvent, AIAnalysis, PurchaseDetail, Approval, IncidentSLA, Escalation, EvaluationRun, UserCapability, PolicyDecision, utcnow
from . import schemas as s
from . import ai_schemas as ai
from . import ai_service
from . import workflows as wf
from . import workflow_schemas as ws

app = FastAPI(title="OpsPilot API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
@app.exception_handler(SQLAlchemyError)
async def database_error(request: HTTPRequest, exc: SQLAlchemyError):
    logging.getLogger(__name__).exception("Database request failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable or not initialized. Check PostgreSQL, run migrations, and seed the demo database."})
def db_session():
    with SessionLocal() as db: yield db
def current_user(x_demo_user_id: int = Header(...), db: Session = Depends(db_session)):
    user = db.get(User, x_demo_user_id)
    if not user or not user.active: raise HTTPException(401, "Select an active demo user")
    return user
DB = Depends(db_session)
UserDep = Depends(current_user)
TRANSITIONS = {
    "Submitted": {"Needs Information", "Triaged", "Cancelled"},
    "Needs Information": {"Submitted", "Triaged", "Cancelled"},
    "Triaged": {"Needs Information", "In Progress", "Cancelled"},
    "In Progress": {"Needs Information", "Resolved", "Cancelled"},
    "Resolved": {"In Progress", "Closed"}, "Closed": set(), "Cancelled": set(),
}
def visible(user):
    if user.role == "Operations Admin": return True
    clauses = [Request.requester_id == user.id]
    clauses.append(Request.id.in_(select(Approval.request_id).where(Approval.assigned_approver_id == user.id)))
    if user.role == "Department Manager": clauses.append(Request.assigned_department_id == user.department_id)
    if user.role == "Department Agent": clauses.append(Request.assigned_user_id == user.id)
    return or_(*clauses)
def can_manage(user, req):
    return user.role == "Operations Admin" or (user.role == "Department Manager" and req.assigned_department_id == user.department_id) or (user.role == "Department Agent" and req.assigned_user_id == user.id)
def get_visible(db, user, request_id):
    req = db.scalar(select(Request).where(Request.id == request_id, visible(user)))
    if not req: raise HTTPException(404, "Request not found")
    return req
def require_manage(user, req):
    if not can_manage(user, req): raise HTTPException(403, "Management permission required")
def event(db, req, user, kind, old=None, new=None):
    db.add(RequestEvent(request_id=req.id, actor_id=user.id if user else None, event_type=kind, previous_value=old, new_value=new))
    req.updated_at = utcnow()
def save(db, req):
    db.commit(); db.refresh(req); return req

def attach_analysis(db, user, req, analysis_id, accepted_fields):
    analysis = db.scalar(select(AIAnalysis).where(AIAnalysis.id == analysis_id).with_for_update())
    if not analysis or analysis.initiated_by_user_id != user.id:
        raise HTTPException(404, 'Analysis not found')
    if analysis.request_id is not None:
        raise HTTPException(409, 'Analysis has already been reviewed')
    if analysis.source_hash != ai_service.source_hash(req.description):
        raise HTTPException(409, 'The request description changed since analysis; reanalyze before attaching it')
    if len(set(accepted_fields)) != len(accepted_fields): raise HTTPException(422, 'Duplicate accepted fields')
    result = analysis.structured_result
    if req.request_type == 'IT Incident' and req.priority == 'Critical':
        flags = list(analysis.validation_flags)
        if 'Critical incident requires human review' not in flags: flags.append('Critical incident requires human review')
        analysis.validation_flags = flags
        result = {**result, 'needs_human_review': True}
        analysis.structured_result = result
    analysis.request_id = req.id
    analysis.accepted_fields = accepted_fields
    analysis.submitted_changes = {'request_type': {'suggested': result['request_type'], 'submitted': req.request_type}, 'priority': {'suggested': result['suggested_priority'], 'submitted': req.priority}, 'department': {'suggested': result['suggested_department'], 'submitted': None}}
    analysis.review_decision = 'accepted' if accepted_fields else 'dismissed'
    analysis.reviewed_at = utcnow()
    event(db, req, user, 'ai_analysis_reviewed', None, analysis.review_decision)

@app.post('/api/v1/ai/analyze-request', response_model=ai.AnalysisOut, status_code=201)
def analyze_request(payload: ai.AnalyzeDraft, db: Session = DB, user: User = UserDep):
    try: outcome = ai_service.analyze(payload)
    except ai_service.AIServiceError as exc: raise HTTPException(exc.status, exc.message) from exc
    analysis = AIAnalysis(initiated_by_user_id=user.id, source_hash=ai_service.source_hash(payload.description), model_name=outcome.model_name, model_identifier=outcome.model_identifier, analysis_status='completed', structured_result=outcome.result.model_dump(mode='json'), validation_flags=outcome.flags, input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens)
    db.add(analysis); db.commit(); db.refresh(analysis)
    return analysis

@app.get('/api/v1/requests/{request_id}/ai-analyses', response_model=list[ai.AnalysisOut])
def analysis_history(request_id: int, db: Session = DB, user: User = UserDep):
    get_visible(db, user, request_id)
    return db.scalars(select(AIAnalysis).where(AIAnalysis.request_id == request_id).order_by(AIAnalysis.created_at.desc(), AIAnalysis.id.desc())).all()

@app.post('/api/v1/requests/{request_id}/ai-review', response_model=ai.AnalysisOut)
def review_existing(request_id: int, payload: ai.ReviewInput, db: Session = DB, user: User = UserDep):
    req = get_visible(db, user, request_id)
    require_manage(user, req)
    if req.status in ('Closed', 'Cancelled'): raise HTTPException(409, 'Request is terminal')
    attach_analysis(db, user, req, payload.analysis_id, payload.accepted_fields)
    db.commit()
    return db.get(AIAnalysis, payload.analysis_id)

@app.get('/api/v1/demo-users', response_model=list[s.UserOut])
def demo_users(db: Session = DB):
    # Bootstrap directory only: no role or user supplied by the client is trusted for authorization.
    return db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)).all()
@app.get('/api/v1/departments', response_model=list[s.DepartmentOut])
def departments(db: Session = DB, user: User = UserDep): return db.scalars(select(Department).order_by(Department.name)).all()
@app.post('/api/v1/requests', response_model=s.RequestOut, status_code=201)
def create(payload: s.RequestCreate, db: Session = DB, user: User = UserDep):
    data = payload.model_dump(exclude={'analysis_id', 'accepted_ai_fields', 'purchase_details'})
    if payload.analysis_id is None and payload.accepted_ai_fields: raise HTTPException(422, 'Accepted fields require an analysis')
    if payload.request_type != 'Purchase Request' and payload.purchase_details is not None: raise HTTPException(422, 'Purchase details require a purchase request')
    req = Request(**data, status="Submitted", requester_id=user.id)
    db.add(req); db.flush(); req.human_readable_id = f"REQ-{req.id:04d}"
    event(db, req, user, "created", None, "Submitted")
    if payload.analysis_id is not None: attach_analysis(db, user, req, payload.analysis_id, payload.accepted_ai_fields)
    wf.route(db, req)
    if req.request_type == 'IT Incident': wf.make_sla(db, req)
    if req.request_type == 'Purchase Request':
        if payload.purchase_details is not None:
            db.add(PurchaseDetail(request_id=req.id, requesting_department_id=user.department_id, **payload.purchase_details.model_dump()))
            db.flush()
        wf.generate_approvals(db,req,user)
    return save(db, req)
@app.get('/api/v1/requests', response_model=s.RequestPage)
def list_requests(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), search: str | None = Query(None, max_length=200), request_type: s.Type | None = None, priority: s.Priority | None = None, status: s.Status | None = None, department_id: int | None = Query(None, gt=0), db: Session = DB, user: User = UserDep):
    conditions = [visible(user)]
    for column, value in [(Request.request_type, request_type), (Request.priority, priority), (Request.status, status), (Request.assigned_department_id, department_id)]:
        if value is not None: conditions.append(column == value)
    if search:
        term = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        conditions.append(or_(*(c.ilike(term, escape='\\') for c in (Request.human_readable_id, Request.title, Request.description))))
    total = db.scalar(select(func.count()).select_from(Request).where(*conditions))
    items = db.scalars(select(Request).where(*conditions).order_by(Request.created_at.desc(), Request.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return dict(items=items, total=total, page=page, page_size=page_size)
@app.get('/api/v1/requests/{request_id}', response_model=s.RequestOut)
def detail(request_id: int, db: Session = DB, user: User = UserDep): return get_visible(db, user, request_id)
@app.patch('/api/v1/requests/{request_id}', response_model=s.RequestOut)
def update(request_id: int, payload: s.RequestUpdate, db: Session = DB, user: User = UserDep):
    req = db.scalar(select(Request).where(Request.id == request_id, visible(user)).with_for_update())
    if not req: raise HTTPException(404, 'Request not found')
    require_manage(user, req)
    if req.status in ('Closed', 'Cancelled'): raise HTTPException(409, "Request is terminal")
    old_priority = req.priority
    if req.request_type == 'IT Incident' and payload.priority is not None and payload.priority != old_priority:
        wf.evaluate_one(db,req,wf.latest_sla(db,req.id),utcnow())
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None: raise HTTPException(422, f"{key} cannot be null")
        old = getattr(req, key)
        if old != value: setattr(req, key, value); event(db, req, user, key + '_changed', old, value)
    if req.request_type == 'IT Incident' and old_priority != req.priority: wf.make_sla(db, req)
    return save(db, req)
@app.put('/api/v1/requests/{request_id}/assignment', response_model=s.RequestOut)
def assign(request_id: int, payload: s.Assignment, db: Session = DB, user: User = UserDep):
    req = db.scalar(select(Request).where(Request.id == request_id, visible(user)).with_for_update())
    if not req: raise HTTPException(404, 'Request not found')
    require_manage(user, req)
    if req.status in ('Closed', 'Cancelled'): raise HTTPException(409, "Request is terminal")
    if user.role != 'Operations Admin' and payload.department_id != user.department_id: raise HTTPException(403, "Only admins may reassign departments")
    if req.assigned_department_id != payload.department_id and (not payload.reason or len(payload.reason.strip()) < 3): raise HTTPException(422, 'A reason is required to override department routing')
    if payload.department_id and not db.get(Department, payload.department_id): raise HTTPException(422, "Unknown department")
    assignee = db.get(User, payload.user_id) if payload.user_id else None
    if payload.user_id and (not assignee or not assignee.active or assignee.department_id != payload.department_id or assignee.role not in ('Department Agent','Department Manager')): raise HTTPException(422, "Assignee must be an active agent or manager in the selected department")
    department_changed = req.assigned_department_id != payload.department_id
    for attr, value in [('assigned_department_id', payload.department_id), ('assigned_user_id', payload.user_id)]:
        old = getattr(req, attr)
        if old != value:
            setattr(req, attr, value); event(db, req, user, attr + '_changed', str(old) if old else None, str(value) if value else None)
    if department_changed: wf.record(db,req,'routing','overridden',f'Manual routing override: {payload.reason.strip()}',user)
    return save(db, req)
@app.post('/api/v1/requests/{request_id}/transition', response_model=s.RequestOut)
def transition(request_id: int, payload: s.Transition, db: Session = DB, user: User = UserDep):
    req = db.scalar(select(Request).where(Request.id == request_id, visible(user)).with_for_update())
    if not req: raise HTTPException(404, 'Request not found')
    require_manage(user, req)
    if payload.status not in TRANSITIONS[req.status]: raise HTTPException(409, "Invalid status transition")
    # Purchasing resolution requires an approval module, which Phase 1 does not provide.
    if req.request_type == 'Purchase Request' and payload.status in ('In Progress', 'Resolved', 'Closed') and wf.overall(db,req.id) != 'Authorized': raise HTTPException(409, "Purchase fulfillment requires completed approval")
    if req.request_type == 'IT Incident' and payload.status in ('Resolved','Closed','Cancelled'):
        wf.evaluate_one(db,req,wf.latest_sla(db,req.id),utcnow())
    old = req.status; req.status = payload.status
    if payload.status == 'Cancelled' and req.request_type == 'Purchase Request':
        for stage in wf.stages_for(db,req.id):
            if stage.status == 'Pending': stage.status = 'Cancelled'
    req.resolved_at = utcnow() if payload.status == 'Resolved' else (None if old == 'Resolved' and payload.status == 'In Progress' else req.resolved_at)
    event(db, req, user, 'status_changed', old, req.status)
    return save(db, req)
@app.post('/api/v1/requests/{request_id}/clarifications', response_model=s.RequestOut)
def clarify(request_id: int, payload: s.Clarification, db: Session = DB, user: User = UserDep):
    req = get_visible(db, user, request_id)
    if user.id != req.requester_id: raise HTTPException(403, "Only the requester can clarify")
    if req.status in ('Closed', 'Cancelled'): raise HTTPException(409, "Request is terminal")
    event(db, req, user, 'clarification', None, payload.message); return save(db, req)
@app.get('/api/v1/requests/{request_id}/events', response_model=list[s.EventOut])
def events(request_id: int, db: Session = DB, user: User = UserDep):
    get_visible(db, user, request_id)
    return db.scalars(select(RequestEvent).where(RequestEvent.request_id == request_id).order_by(RequestEvent.created_at.desc(), RequestEvent.id.desc())).all()
@app.get('/api/v1/dashboard')
def dashboard(db: Session = DB, user: User = UserDep):
    condition = visible(user)
    rows = db.scalars(select(Request).where(condition)).all()
    ids = [r.id for r in rows]
    recent = db.scalars(select(RequestEvent).where(RequestEvent.request_id.in_(ids)).order_by(RequestEvent.created_at.desc(), RequestEvent.id.desc()).limit(8)).all() if ids else []
    distribution = {t: sum(r.request_type == t for r in rows) for t in ('IT Incident','Purchase Request','Cross-Department Project')}
    references = {r.id: r.human_readable_id for r in rows}
    routed=set(db.scalars(select(PolicyDecision.request_id).where(PolicyDecision.request_id.in_(ids),PolicyDecision.decision_type=='routing',PolicyDecision.outcome=='routed')).all()) if ids else set()
    manual=set()
    for req in rows:
        routing=db.scalar(select(PolicyDecision).where(PolicyDecision.request_id==req.id,PolicyDecision.decision_type=='routing').order_by(PolicyDecision.id.desc()))
        if routing and routing.outcome=='manual_triage': manual.add(req.id)
    purchases=[r for r in rows if r.request_type=='Purchase Request']
    purchase_states=[wf.overall(db,r.id) for r in purchases]
    incident_slas=[wf.latest_sla(db,r.id) for r in rows if r.request_type=='IT Incident' and r.status not in ('Resolved','Closed','Cancelled')]
    manual.update(r.id for r,state in zip(purchases,purchase_states) if state in ('Needs information','Needs resubmission'))
    manual.update(r.id for r,state in zip(purchases,purchase_states) if state=='Pending' and any(a.status=='Pending' and a.assigned_approver_id is None for a in wf.stages_for(db,r.id)))
    manual.update(sla.request_id for sla in incident_slas if sla and sla.priority_at_evaluation=='Critical' and not sla.first_acknowledged_at)
    automation={'automatically_routed':len(routed),'awaiting_approval':purchase_states.count('Pending'),'purchases_authorized':purchase_states.count('Authorized'),'purchases_rejected':purchase_states.count('Rejected'),'overdue_incidents':sum(bool(x and x.breached_at and not x.first_acknowledged_at) for x in incident_slas),'escalated_incidents':sum(bool(x and x.escalation_status=='Escalated' and not x.first_acknowledged_at) for x in incident_slas),'manual_review':len(manual)}
    return {"total": len(rows), "open": sum(r.status not in ('Resolved','Closed','Cancelled') for r in rows), "attention": sum(r.status == 'Needs Information' or (r.priority in ('High','Critical') and r.status not in ('Resolved','Closed','Cancelled')) for r in rows), "resolved": sum(r.status in ('Resolved','Closed') for r in rows), "distribution": distribution, 'automation':automation, "recent_activity": [{**s.EventOut.model_validate(e).model_dump(mode='json'), "request_reference": references[e.request_id]} for e in recent]}

# Phase 3 workflow endpoints. Monetary decisions are based solely on structured fields.
@app.post('/api/v1/requests/{request_id}/routing/reevaluate')
def reevaluate_routing(request_id: int, db: Session = DB, user: User = UserDep):
    if user.role != 'Operations Admin': raise HTTPException(403,'Operations admin required')
    req = db.scalar(select(Request).where(Request.id==request_id).with_for_update())
    if not req: raise HTTPException(404,'Request not found')
    if req.status in ('Resolved','Closed','Cancelled'): raise HTTPException(409,'Request is terminal')
    changed=wf.route(db,req)
    if req.request_type=='IT Incident' and not wf.latest_sla(db,req.id): wf.make_sla(db,req)
    db.commit()
    return {'routed':changed,'assigned_department_id':req.assigned_department_id}

@app.put('/api/v1/requests/{request_id}/purchase-details')
def put_purchase(request_id: int, payload: ws.PurchaseInput, db: Session = DB, user: User = UserDep):
    req=db.scalar(select(Request).where(Request.id==request_id,visible(user)).with_for_update())
    if not req: raise HTTPException(404,'Request not found')
    if req.requester_id!=user.id and not can_manage(user,req): raise HTTPException(403,'Purchase editing is not permitted')
    if req.request_type!='Purchase Request': raise HTTPException(409,'Not a purchase request')
    if req.status in ('Resolved','Closed','Cancelled'): raise HTTPException(409,'Request is terminal')
    requester=db.get(User,req.requester_id)
    detail=db.get(PurchaseDetail,req.id)
    data=payload.model_dump()
    if detail is None:
        detail=PurchaseDetail(request_id=req.id,requesting_department_id=requester.department_id,**data);db.add(detail)
        wf.audit(db,req,'purchase_details_updated','Purchase details recorded.',user)
    elif any(getattr(detail,k)!=v for k,v in data.items()):
        wf.invalidate(db,req,user)
        for k,v in data.items(): setattr(detail,k,v)
        detail.updated_at=utcnow()
        wf.audit(db,req,'purchase_details_updated','Purchase details changed; prior approvals require review.',user)
    db.flush();missing=wf.required_fields(detail)
    db.commit()
    return {'missing_information':missing,'approval_state':wf.overall(db,req.id)}

@app.post('/api/v1/requests/{request_id}/purchase/submit-approvals')
def submit_approvals(request_id: int, db: Session = DB, user: User = UserDep):
    req=db.scalar(select(Request).where(Request.id==request_id,visible(user)).with_for_update())
    if not req: raise HTTPException(404,'Request not found')
    if req.requester_id!=user.id and not can_manage(user,req): raise HTTPException(403,'Purchase submission is not permitted')
    if req.request_type!='Purchase Request' or req.status in ('Resolved','Closed','Cancelled'): raise HTTPException(409,'Purchase cannot be submitted')
    rows=wf.generate_approvals(db,req,user); db.flush()
    result={'approval_state':wf.overall(db,req.id),'missing_information':wf.required_fields(db.get(PurchaseDetail,req.id)),'stages_created':len(rows)}
    db.commit();return result

@app.post('/api/v1/requests/{request_id}/purchase/regenerate-approvals')
def regenerate_approvals(request_id: int, payload: ws.ReasonInput, db: Session = DB, user: User = UserDep):
    req=db.scalar(select(Request).where(Request.id==request_id,visible(user)).with_for_update())
    if not req: raise HTTPException(404,'Request not found')
    require_manage(user,req)
    if req.request_type!='Purchase Request' or req.status in ('Resolved','Closed','Cancelled'): raise HTTPException(409,'Purchase cannot be regenerated')
    wf.invalidate(db,req,user)
    wf.record(db,req,'approval','regenerated',f'Approval cycle regenerated: {payload.reason}',user)
    rows=wf.generate_approvals(db,req,user);db.flush()
    result={'approval_state':wf.overall(db,req.id),'missing_information':wf.required_fields(db.get(PurchaseDetail,req.id)),'stages_created':len(rows)}
    db.commit();return result

@app.get('/api/v1/requests/{request_id}/automation')
def automation_detail(request_id: int, db: Session = DB, user: User = UserDep):
    req=get_visible(db,user,request_id)
    details=db.get(PurchaseDetail,req.id)
    approvals=db.scalars(select(Approval).where(Approval.request_id==req.id).order_by(Approval.cycle,Approval.approval_stage)).all()
    slas=db.scalars(select(IncidentSLA).where(IncidentSLA.request_id==req.id).order_by(IncidentSLA.revision.desc())).all()
    escalations=db.scalars(select(Escalation).where(Escalation.request_id==req.id).order_by(Escalation.created_at.desc())).all()
    decisions=db.scalars(select(PolicyDecision).where(PolicyDecision.request_id==req.id).order_by(PolicyDecision.created_at.desc())).all()
    return {'purchase':details,'approval_state':wf.overall(db,req.id) if req.request_type=='Purchase Request' else None,'approvals':approvals,'slas':slas,'escalations':escalations,'decisions':decisions,'can_acknowledge':can_manage(user,req)}

@app.post('/api/v1/requests/{request_id}/acknowledge')
def acknowledge(request_id: int, db: Session = DB, user: User = UserDep):
    req=db.scalar(select(Request).where(Request.id==request_id,visible(user)).with_for_update())
    if not req: raise HTTPException(404,'Request not found')
    require_manage(user,req)
    if req.request_type!='IT Incident' or req.status in ('Resolved','Closed','Cancelled'): raise HTTPException(409,'Incident cannot be acknowledged')
    sla=wf.latest_sla(db,req.id)
    if not sla: raise HTTPException(409,'SLA has not been evaluated; request an admin reevaluation')
    if not sla.first_acknowledged_at:
        now=utcnow();wf.evaluate_one(db,req,sla,now);sla.first_acknowledged_at=now;sla.acknowledged_by_id=user.id
        if sla.escalation_status=='Escalated': sla.escalation_status='Acknowledged'
        wf.audit(db,req,'incident_acknowledged','Initial response acknowledged.',user)
    db.commit();return {'acknowledged_at':sla.first_acknowledged_at}

@app.get('/api/v1/approvals')
def approval_queue(db: Session = DB, user: User = UserDep):
    # Only approvals assigned to the selected user are visible, except for the admin oversight view.
    query=select(Approval).order_by(Approval.created_at.desc(),Approval.approval_stage)
    if user.role!='Operations Admin': query=query.where(Approval.assigned_approver_id==user.id)
    rows=db.scalars(query).all();result=[]
    for row in rows:
        req=db.get(Request,row.request_id);purchase=db.get(PurchaseDetail,row.request_id)
        current=wf.stages_for(db,req.id)
        active=next((a for a in current if a.status=='Pending'),None) if wf.overall(db,req.id)=='Pending' else None
        result.append({'approval':row,'request':req,'purchase':purchase,'approval_state':wf.overall(db,req.id),'actionable':bool(active and active.id==row.id and row.assigned_approver_id==user.id and purchase and wf.is_eligible(db,req,purchase.requesting_department_id,row.required_role_or_capability,user))})
    return result

@app.post('/api/v1/approvals/{approval_id}/decision')
def approval_decision(approval_id: int, payload: ws.ApprovalDecisionInput, db: Session = DB, user: User = UserDep):
    # Lock order is always request then stage, serializing concurrent stages and revisions.
    request_id=db.scalar(select(Approval.request_id).where(Approval.id==approval_id))
    if request_id is None: raise HTTPException(404,'Approval not found')
    req=db.scalar(select(Request).where(Request.id==request_id).with_for_update())
    row=db.scalar(select(Approval).where(Approval.id==approval_id).with_for_update())
    if row.assigned_approver_id != user.id or req.requester_id==user.id: raise HTTPException(403,'You are not the eligible approver')
    if req.status in ('Cancelled','Closed','Resolved'): raise HTTPException(409,'Request is terminal')
    if row.status==payload.decision and row.decision_actor_id==user.id:
        if row.decision_reason != payload.reason: raise HTTPException(409,'A different decision was already recorded')
        return {'status':row.status,'approval_state':wf.overall(db,req.id),'idempotent':True}
    if row.status!='Pending' or wf.overall(db,req.id)!='Pending': raise HTTPException(409,'Approval is no longer pending')
    stages=wf.stages_for(db,req.id); current=next((a for a in stages if a.status=='Pending'),None)
    if not current or current.id!=row.id: raise HTTPException(409,'A prior approval stage must be completed first')
    # Assigned users must remain eligible; changing eligibility never silently transfers ownership.
    purchase=db.get(PurchaseDetail,req.id)
    if not purchase or not wf.is_eligible(db,req,purchase.requesting_department_id,row.required_role_or_capability,user): raise HTTPException(403,'Approver is no longer eligible')
    if payload.decision=='Rejected' and not payload.reason: raise HTTPException(422,'A rejection reason is required')
    row.status=payload.decision;row.decision_outcome=payload.decision;row.decision_actor_id=user.id;row.decision_reason=payload.reason;row.decided_at=utcnow();db.flush()
    if payload.decision=='Rejected':
        for later in stages:
            if later.id!=row.id and later.status=='Pending': later.status='Cancelled'
    wf.record(db,req,'approval',row.status,f'{row.required_role_or_capability} stage {row.status.lower()}'+(f': {payload.reason}' if payload.reason else '.'),user)
    db.flush();state=wf.overall(db,req.id);db.commit()
    return {'status':row.status,'approval_state':state,'idempotent':False}

@app.get('/api/v1/incidents/attention')
def attention_incidents(db: Session = DB, user: User = UserDep):
    if user.role not in ('Operations Admin','Department Manager'): raise HTTPException(403,'Manager or admin required')
    requests=db.scalars(select(Request).where(Request.request_type=='IT Incident',Request.status.not_in(('Resolved','Closed','Cancelled')),visible(user))).all();result=[]
    for req in requests:
        sla=wf.latest_sla(db,req.id)
        if sla and not sla.first_acknowledged_at and (sla.escalation_status=='Escalated' or sla.breached_at): result.append({'request':req,'sla':sla,'escalations':db.scalars(select(Escalation).where(Escalation.request_id==req.id)).all()})
    last=db.scalar(select(EvaluationRun).order_by(EvaluationRun.completed_at.desc()))
    return {'items':result,'last_successful_evaluation':last.completed_at if last else None}
