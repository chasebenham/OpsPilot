from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from .models import SessionLocal, Department, User, Request, RequestEvent, utcnow
from . import schemas as s

app = FastAPI(title="OpsPilot API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
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

@app.get('/api/v1/demo-users', response_model=list[s.UserOut])
def demo_users(db: Session = DB):
    # Bootstrap directory only: no role or user supplied by the client is trusted for authorization.
    return db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)).all()
@app.get('/api/v1/departments', response_model=list[s.DepartmentOut])
def departments(db: Session = DB, user: User = UserDep): return db.scalars(select(Department).order_by(Department.name)).all()
@app.post('/api/v1/requests', response_model=s.RequestOut, status_code=201)
def create(payload: s.RequestCreate, db: Session = DB, user: User = UserDep):
    req = Request(**payload.model_dump(), status="Submitted", requester_id=user.id)
    db.add(req); db.flush(); req.human_readable_id = f"REQ-{req.id:04d}"
    event(db, req, user, "created", None, "Submitted")
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
    req = get_visible(db, user, request_id); require_manage(user, req)
    if req.status in ('Closed', 'Cancelled'): raise HTTPException(409, "Request is terminal")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None: raise HTTPException(422, f"{key} cannot be null")
        old = getattr(req, key)
        if old != value: setattr(req, key, value); event(db, req, user, key + '_changed', old, value)
    return save(db, req)
@app.put('/api/v1/requests/{request_id}/assignment', response_model=s.RequestOut)
def assign(request_id: int, payload: s.Assignment, db: Session = DB, user: User = UserDep):
    req = get_visible(db, user, request_id); require_manage(user, req)
    if req.status in ('Closed', 'Cancelled'): raise HTTPException(409, "Request is terminal")
    if user.role != 'Operations Admin' and payload.department_id != user.department_id: raise HTTPException(403, "Only admins may reassign departments")
    if payload.department_id and not db.get(Department, payload.department_id): raise HTTPException(422, "Unknown department")
    assignee = db.get(User, payload.user_id) if payload.user_id else None
    if payload.user_id and (not assignee or not assignee.active or assignee.department_id != payload.department_id or assignee.role not in ('Department Agent','Department Manager')): raise HTTPException(422, "Assignee must be an active agent or manager in the selected department")
    for attr, value in [('assigned_department_id', payload.department_id), ('assigned_user_id', payload.user_id)]:
        old = getattr(req, attr)
        if old != value:
            setattr(req, attr, value); event(db, req, user, attr + '_changed', str(old) if old else None, str(value) if value else None)
    return save(db, req)
@app.post('/api/v1/requests/{request_id}/transition', response_model=s.RequestOut)
def transition(request_id: int, payload: s.Transition, db: Session = DB, user: User = UserDep):
    req = get_visible(db, user, request_id); require_manage(user, req)
    if payload.status not in TRANSITIONS[req.status]: raise HTTPException(409, "Invalid status transition")
    # Purchasing resolution requires an approval module, which Phase 1 does not provide.
    if req.request_type == 'Purchase Request' and payload.status in ('Resolved', 'Closed'): raise HTTPException(409, "Purchase completion requires future approval functionality")
    old = req.status; req.status = payload.status
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
    return {"total": len(rows), "open": sum(r.status not in ('Resolved','Closed','Cancelled') for r in rows), "attention": sum(r.status == 'Needs Information' or (r.priority in ('High','Critical') and r.status not in ('Resolved','Closed','Cancelled')) for r in rows), "resolved": sum(r.status in ('Resolved','Closed') for r in rows), "distribution": distribution, "recent_activity": [s.EventOut.model_validate(e).model_dump(mode='json') for e in recent]}
