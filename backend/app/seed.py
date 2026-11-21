"""Seed fictional demo data. Reset is explicitly destructive and limited to the local demo DB."""
import argparse
from datetime import timedelta
from sqlalchemy import select, delete, text
from sqlalchemy.engine import make_url
from .models import SessionLocal, Department, User, Request, RequestEvent, AIAnalysis, utcnow, DATABASE_URL
NAMES = ['IT', 'Finance', 'Marketing', 'Operations', 'People & HR']
TITLES = [
('CRM platform outage','IT Incident'), ('Employee account access problem','IT Incident'), ('$4,500 analytics software purchase','Purchase Request'), ('Laptop replacement request','Purchase Request'), ('Marketing landing page project','Cross-Department Project'), ('Client presentation design request','Cross-Department Project'),
('VPN disconnects during meetings','IT Incident'), ('Shared mailbox access','IT Incident'), ('Conference room display issue','IT Incident'), ('New starter account setup','IT Incident'), ('Password reset loop','IT Incident'), ('Reporting dashboard unavailable','IT Incident'),
('Design software subscription','Purchase Request'), ('Team headset purchase','Purchase Request'), ('Research database license','Purchase Request'), ('Replacement monitor order','Purchase Request'), ('Training platform subscription','Purchase Request'), ('Office supplies order','Purchase Request'),
('Quarterly onboarding improvements','Cross-Department Project'), ('Client kickoff checklist','Cross-Department Project'), ('Internal newsletter refresh','Cross-Department Project'), ('Expense process review','Cross-Department Project'), ('Knowledge base restructure','Cross-Department Project'), ('Service catalog rollout','Cross-Department Project'),
('Printer queue stalled','IT Incident'), ('Calendar sync issue','IT Incident'), ('Security key enrollment','IT Incident'), ('Video meeting audio issue','IT Incident'), ('Project management tool license','Purchase Request'), ('Team workshop materials','Purchase Request'), ('New hire welcome campaign','Cross-Department Project'), ('Client handoff template','Cross-Department Project'), ('Finance reporting redesign','Cross-Department Project'), ('Accessibility review','Cross-Department Project'), ('Data export request','IT Incident'), ('Contract review coordination','Cross-Department Project')]
def seed(reset=False):
    with SessionLocal() as db:
        if reset:
            url = make_url(DATABASE_URL)
            if url.get_backend_name() != 'postgresql' or url.host not in ('localhost', '127.0.0.1', '::1') or url.database != 'opspilot':
                raise SystemExit('Reset is restricted to the local PostgreSQL database named opspilot.')
            for model in (AIAnalysis, RequestEvent, Request, User, Department): db.execute(delete(model))
            if db.bind.dialect.name == 'postgresql':
                for table in ('ai_analyses', 'request_events', 'requests', 'users', 'departments'):
                    db.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), 1, false)"), {'table': table})
            db.commit()
        if db.scalar(select(Department.id).limit(1)) is not None:
            print('Database already contains departments; seed skipped. Use --reset to restore demo data.')
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
        db.commit(); print('Seeded 5 departments, 17 fictional users, and 36 requests.')
if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--reset', action='store_true'); args = parser.parse_args(); seed(args.reset)
