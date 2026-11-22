"""Seed fictional demo data. Reset is explicitly destructive and limited to the local demo DB."""
import argparse
from datetime import timedelta
from sqlalchemy import select, delete, text
from sqlalchemy.engine import make_url
from .models import SessionLocal, Department, User, Request, RequestEvent, AIAnalysis, UserCapability, EvaluationRun, PurchaseDetail, utcnow, DATABASE_URL
NAMES = ['IT', 'Finance', 'Marketing', 'Operations', 'People & HR']
TITLES = [
('CRM platform outage','IT Incident'), ('Employee account access problem','IT Incident'), ('$4,500 analytics software purchase','Purchase Request'), ('Laptop replacement request','Purchase Request'), ('Marketing landing page project','Cross-Department Project'), ('Client presentation design request','Cross-Department Project'),
('VPN disconnects during meetings','IT Incident'), ('Shared mailbox access','IT Incident'), ('Conference room display issue','IT Incident'), ('New starter account setup','IT Incident'), ('Password reset loop','IT Incident'), ('Reporting dashboard unavailable','IT Incident'),
('Design software subscription','Purchase Request'), ('Team headset purchase','Purchase Request'), ('Research database license','Purchase Request'), ('Replacement monitor order','Purchase Request'), ('Training platform subscription','Purchase Request'), ('Office supplies order','Purchase Request'),
('Quarterly onboarding improvements','Cross-Department Project'), ('Client kickoff checklist','Cross-Department Project'), ('Internal newsletter refresh','Cross-Department Project'), ('Expense process review','Cross-Department Project'), ('Knowledge base restructure','Cross-Department Project'), ('Service catalog rollout','Cross-Department Project'),
('Printer queue stalled','IT Incident'), ('Calendar sync issue','IT Incident'), ('Security key enrollment','IT Incident'), ('Video meeting audio issue','IT Incident'), ('Project management tool license','Purchase Request'), ('Team workshop materials','Purchase Request'), ('New hire welcome campaign','Cross-Department Project'), ('Client handoff template','Cross-Department Project'), ('Finance reporting redesign','Cross-Department Project'), ('Accessibility review','Cross-Department Project'), ('Data export request','IT Incident'), ('Contract review coordination','Cross-Department Project')]
def seed_approvers(db):
    departments = {d.name:d for d in db.scalars(select(Department)).all()}
    if not all(name in departments for name in NAMES):
        print('Meridian departments are incomplete; approver seed skipped.')
        return
    for index, name in enumerate(NAMES):
        email=f'alternate.manager.{index+1}@meridian.example'
        if not db.scalar(select(User).where(User.email==email)):
            db.add(User(name=f'Alternate {name} Manager',email=email,department_id=departments[name].id,role='Department Manager',active=True))
    extras=[('Morgan Vale','alternate.finance@meridian.example','Finance Approver',None),('Drew Ellis','director@meridian.example','Employee','Operations Director'),('Skyler Hart','executive@meridian.example','Employee','Executive Approver')]
    for name,email,role,capability in extras:
        user=db.scalar(select(User).where(User.email==email))
        if not user:
            user=User(name=name,email=email,role=role,department_id=departments['Operations' if capability else 'Finance'].id,active=True);db.add(user);db.flush()
        elif user.name != name or user.role != role or user.department_id != departments['Operations' if capability else 'Finance'].id:
            print(f'Seed identity conflict for {email}; existing user left unchanged.')
            continue
        if capability and not db.get(UserCapability,(user.id,capability)): db.add(UserCapability(user_id=user.id,capability=capability))
    db.commit()

def seed_workflows(db):
    """Insert separately named fictional examples only; never rewrite existing requests."""
    from decimal import Decimal
    from . import workflows as wf
    requester=db.scalar(select(User).where(User.email=='employee.1@meridian.example'))
    admin=db.scalar(select(User).where(User.email=='admin@meridian.example'))
    if not requester or not admin:
        print('Meridian seed identities unavailable; workflow examples skipped.')
        return
    examples=[('Pending software purchase','Purchase Request','Normal','4500.00','pending'),('Partially approved purchase','Purchase Request','Normal','6500.00','partial'),('Rejected equipment purchase','Purchase Request','Normal','800.00','rejected'),('Authorized service purchase','Purchase Request','Normal','300.00','authorized'),('Overdue network incident','IT Incident','High',None,'overdue'),('Critical CRM incident','IT Incident','Critical',None,'critical'),('Acknowledged access incident','IT Incident','Normal',None,'acknowledged'),('Legacy request needing triage','Cross-Department Project','Normal',None,'triage')]
    for title,kind,priority,amount,scenario in examples:
        title='[Meridian demo] '+title
        if db.scalar(select(Request.id).where(Request.title==title,Request.requester_id==requester.id)): continue
        created=utcnow()-(timedelta(days=2) if scenario in ('overdue','critical') else timedelta())
        req=Request(title=title,description='Fictional Phase 3 demonstration request.',request_type=kind,priority=priority,status='Submitted',requester_id=requester.id,created_at=created,updated_at=created)
        db.add(req);db.flush();req.human_readable_id=f'REQ-{req.id:04d}'
        db.add(RequestEvent(request_id=req.id,actor_id=requester.id,event_type='created',new_value='Submitted',created_at=created))
        if scenario=='triage': wf.record(db,req,'routing','manual_triage','Legacy demo request awaits administrator routing review.')
        else: wf.route(db,req)
        if kind=='Purchase Request':
            db.add(PurchaseDetail(request_id=req.id,vendor='Fictional Meridian Vendor',description='Demonstration purchase',total_committed_amount=Decimal(amount),currency='USD',business_justification='Illustrate the approval workflow',contract_term='One year',commitment_confirmed=True,requesting_department_id=requester.department_id));db.flush()
            rows=wf.generate_approvals(db,req,requester);db.flush()
            count={'pending':0,'partial':1,'rejected':1,'authorized':len(rows)}[scenario]
            for stage in rows[:count]:
                if stage.assigned_approver_id is None: break
                stage.status='Rejected' if scenario=='rejected' else 'Approved';stage.decision_outcome=stage.status;stage.decision_actor_id=stage.assigned_approver_id;stage.decision_reason='Fictional review example' if scenario=='rejected' else None;stage.decided_at=utcnow()
                wf.audit(db,req,'policy_approval',f'{stage.required_role_or_capability} stage {stage.status.lower()} (demo).',db.get(User,stage.assigned_approver_id) if stage.assigned_approver_id else None)
                if scenario=='rejected':
                    for later in rows[1:]: later.status='Cancelled'
        elif kind=='IT Incident':
            sla=wf.make_sla(db,req)
            if scenario=='acknowledged':
                sla.first_acknowledged_at=utcnow();sla.acknowledged_by_id=admin.id
                wf.audit(db,req,'incident_acknowledged','Initial response acknowledged (demo).',admin)
    db.commit()
def seed(reset=False):
    with SessionLocal() as db:
        if reset:
            url = make_url(DATABASE_URL)
            if url.get_backend_name() != 'postgresql' or url.host not in ('localhost', '127.0.0.1', '::1') or url.database != 'opspilot':
                raise SystemExit('Reset is restricted to the local PostgreSQL database named opspilot.')
            for model in (AIAnalysis, RequestEvent, Request, UserCapability, User, Department, EvaluationRun): db.execute(delete(model))
            if db.bind.dialect.name == 'postgresql':
                for table in ('ai_analyses', 'request_events', 'requests', 'users', 'departments', 'policy_decisions', 'approvals', 'incident_slas', 'escalations', 'evaluation_runs'):
                    db.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), 1, false)"), {'table': table})
            db.commit()
        if db.scalar(select(Department.id).limit(1)) is not None:
            seed_approvers(db)
            seed_workflows(db)
            from .project_seed import seed_projects
            seed_projects(db)
            print('Existing requests preserved; Meridian approvers are present.')
            return
        departments = [Department(name=n) for n in NAMES]; db.add_all(departments); db.flush()
        users = []
        for i, dep in enumerate(departments):
            for label, role in [('Employee','Employee'), ('Agent','Department Agent'), ('Manager','Department Manager')]:
                users.append(User(name=f'{["Alex Morgan", "Jordan Bell", "Taylor Reed", "Casey Lane", "Riley Chen"][i]} ({label})', email=f'{label.lower()}.{i+1}@meridian.example', department_id=dep.id, role=role, active=True))
        users.extend([User(name='Avery Stone', email='finance.approver@meridian.example', department_id=departments[1].id, role='Finance Approver', active=True), User(name='Sam Rivera', email='admin@meridian.example', department_id=departments[3].id, role='Operations Admin', active=True)])
        db.add_all(users); db.flush()
        paths = [['Submitted'], ['Submitted','Needs Information'], ['Submitted','Triaged'], ['Submitted','Triaged','In Progress'], ['Submitted','Triaged','In Progress','Resolved'], ['Submitted','Triaged','In Progress','Resolved','Closed'], ['Submitted','Cancelled']]
        for i, (title, kind) in enumerate(TITLES):
            path = paths[i % len(paths)]
            if kind == 'Purchase Request' and path[-1] in ('Resolved','Closed'): path = paths[3]
            dep = departments[(0 if kind == 'IT Incident' else 1 if kind == 'Purchase Request' else 2 + i % 3)]
            requester = users[(i % 5)*3]; agent = users[NAMES.index(dep.name)*3+1]
            created = utcnow() - timedelta(days=40-i)
            req = Request(title=title, description=f'{title}. Please review the impact, coordinate with the appropriate team, and provide an update to the requester.', request_type=kind, priority=['Low','Normal','High','Critical'][i%4], status=path[-1], requester_id=requester.id, assigned_department_id=dep.id, assigned_user_id=agent.id, created_at=created, updated_at=created + timedelta(hours=len(path)), resolved_at=created + timedelta(hours=3) if 'Resolved' in path else None)
            db.add(req); db.flush(); req.human_readable_id=f'REQ-{req.id:04d}'
            db.add(RequestEvent(request_id=req.id, actor_id=requester.id, event_type='created', new_value='Submitted', created_at=created))
            db.add(RequestEvent(request_id=req.id, actor_id=users[-1].id, event_type='assigned_department_id_changed', new_value=str(dep.id), created_at=created+timedelta(minutes=10)))
            db.add(RequestEvent(request_id=req.id, actor_id=users[-1].id, event_type='assigned_user_id_changed', new_value=str(agent.id), created_at=created+timedelta(minutes=20)))
            for j in range(1,len(path)):
                db.add(RequestEvent(request_id=req.id, actor_id=agent.id, event_type='status_changed', previous_value=path[j-1], new_value=path[j], created_at=created+timedelta(hours=j)))
        db.commit(); seed_approvers(db); seed_workflows(db)
        from .project_seed import seed_projects
        seed_projects(db); print('Seeded Meridian departments, users, and demo requests.')
if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--reset', action='store_true'); args = parser.parse_args(); seed(args.reset)
