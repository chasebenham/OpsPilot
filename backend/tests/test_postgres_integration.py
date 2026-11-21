import os
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.main import app, db_session
from app.models import Base, Department, User

@pytest.fixture
def pg_client():
    url = os.environ.get('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Set TEST_POSTGRES_URL to a disposable PostgreSQL database for integration tests')
    schema = 'opspilot_test_' + uuid4().hex
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    engine = None
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as db:
            db.add_all([Department(id=1, name='IT'), Department(id=2, name='Finance')]); db.flush()
            db.add_all([
                User(id=1, name='Requester', email='requester@example.test', department_id=1, role='Employee', active=True),
                User(id=2, name='Other', email='other@example.test', department_id=2, role='Employee', active=True),
                User(id=3, name='IT Agent', email='agent@example.test', department_id=1, role='Department Agent', active=True),
                User(id=4, name='Admin', email='admin@example.test', department_id=1, role='Operations Admin', active=True),
            ]); db.commit()
        def override():
            with Session() as db: yield db
        app.dependency_overrides[db_session] = override
        with TestClient(app) as client: yield client
    finally:
        app.dependency_overrides.clear()
        if engine: engine.dispose()
        # Only the randomly named schema created by this fixture is removed.
        with admin.connect() as conn: conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()

def h(user_id): return {'X-Demo-User-Id': str(user_id)}

def test_postgres_request_lifecycle_and_dashboard(pg_client):
    c = pg_client
    assert len(c.get('/api/v1/demo-users').json()) == 4
    created = []
    for kind in ('IT Incident', 'Purchase Request', 'Cross-Department Project'):
        response = c.post('/api/v1/requests', headers=h(1), json={'title': f'{kind} integration', 'description': 'Persistent PostgreSQL test', 'request_type': kind, 'priority': 'High'})
        assert response.status_code == 201
        assert response.json()['status'] == 'Submitted'
        created.append(response.json())
    before = c.get('/api/v1/dashboard', headers=h(4)).json()
    assert (before['total'], before['open'], before['attention'], before['resolved']) == (3, 3, 3, 0)
    rid = created[0]['id']
    assert c.get(f'/api/v1/requests/{rid}', headers=h(2)).status_code == 404
    assert c.get(f'/api/v1/requests/{rid}/events', headers=h(2)).status_code == 404
    assert c.put(f'/api/v1/requests/{rid}/assignment', headers=h(1), json={'department_id': 1, 'user_id': 3}).status_code == 403
    assert c.put(f'/api/v1/requests/{rid}/assignment', headers=h(4), json={'department_id': 1, 'user_id': 3, 'reason':'Test routing override'}).status_code == 200
    assert c.post(f'/api/v1/requests/{rid}/transition', headers=h(3), json={'status': 'Resolved'}).status_code == 409
    for status in ('Triaged', 'In Progress', 'Resolved'):
        assert c.post(f'/api/v1/requests/{rid}/transition', headers=h(3), json={'status': status}).status_code == 200
    details = c.get(f'/api/v1/requests/{rid}', headers=h(1)).json()
    assert details['status'] == 'Resolved' and details['resolved_at'] is not None
    events = c.get(f'/api/v1/requests/{rid}/events', headers=h(1)).json()
    assert {e['event_type'] for e in events} >= {'created', 'policy_routing', 'assigned_user_id_changed', 'status_changed'}
    assert len([e for e in events if e['event_type'] == 'status_changed']) == 3
    assert c.get('/api/v1/requests?search=integration&request_type=IT%20Incident&department_id=1', headers=h(4)).json()['total'] == 1
    assert c.get('/api/v1/requests', headers=h(2)).json()['total'] == 0
    summary = c.get('/api/v1/dashboard', headers=h(4)).json()
    assert (summary['total'], summary['open'], summary['attention'], summary['resolved']) == (3, 2, 2, 1)
    assert summary['distribution'] == {'IT Incident': 1, 'Purchase Request': 1, 'Cross-Department Project': 1}
    assert any(e['request_reference'] == created[0]['human_readable_id'] for e in summary['recent_activity'])
    assert c.get('/api/v1/dashboard', headers=h(2)).json()['total'] == 0
    # A new session/request reads the committed state after all mutations.
    assert c.get(f'/api/v1/requests/{rid}', headers=h(3)).json()['status'] == 'Resolved'

def test_postgres_ai_review_persists_and_is_scoped(pg_client, monkeypatch):
    from app import ai_service
    from app.ai_schemas import AnalysisResult, ExtractedDetails
    details={key:None for key in ExtractedDetails.model_fields}; details['affected_system']='CRM'
    result=AnalysisResult(request_type='IT Incident',suggested_priority='High',suggested_department='IT',summary='CRM unavailable',business_impact=None,extracted_details=details,missing_information=['When did it start?'],explanation='Outage',needs_human_review=False)
    monkeypatch.setattr(ai_service,'analyze',lambda draft:ai_service.ProviderResult(result,[],'test','test-v1',30,20))
    c=pg_client
    aid=c.post('/api/v1/ai/analyze-request',headers=h(1),json={'description':'CRM outage'}).json()['id']
    body={'title':'CRM','description':'CRM outage','request_type':'IT Incident','priority':'Critical','analysis_id':aid,'accepted_ai_fields':['priority']}
    assert c.post('/api/v1/requests',headers=h(2),json=body).status_code==404
    response=c.post('/api/v1/requests',headers=h(1),json=body); assert response.status_code==201
    rid=response.json()['id']
    saved=c.get(f'/api/v1/requests/{rid}/ai-analyses',headers=h(1)).json()[0]
    assert saved['model_identifier']=='test-v1' and saved['structured_result']['needs_human_review']
    assert 'Critical incident requires human review' in saved['validation_flags']
    assert saved['submitted_changes']['priority']=={'suggested':'High','submitted':'Critical'}
    assert c.get(f'/api/v1/requests/{rid}/ai-analyses',headers=h(2)).status_code==404

def test_postgres_approval_decisions_are_serialized(pg_client):
    from concurrent.futures import ThreadPoolExecutor
    from app.models import User
    for db in app.dependency_overrides[db_session]():
        db.add(User(id=5,name='Manager',email='manager@example.test',department_id=1,role='Department Manager',active=True));db.commit()
    details={'vendor':'North','description':'License','total_committed_amount':'999.99','currency':'USD','business_justification':'Needed','contract_term':'Annual','commitment_confirmed':True}
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'Purchase','description':'License','request_type':'Purchase Request','purchase_details':details});assert r.status_code==201
    rid=r.json()['id'];aid=pg_client.get(f'/api/v1/requests/{rid}/automation',headers=h(1)).json()['approvals'][0]['id']
    def decide(_):
        return pg_client.post(f'/api/v1/approvals/{aid}/decision',headers=h(5),json={'decision':'Approved'})
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(decide,range(2)))
    assert all(response.status_code==200 for response in responses)
    assert sorted(response.json()['idempotent'] for response in responses)==[False,True]
    assert pg_client.get(f'/api/v1/requests/{rid}/automation',headers=h(1)).json()['approval_state']=='Authorized'

def test_postgres_executive_cycle_and_status_gate(pg_client):
    from app.models import User, UserCapability
    for db in app.dependency_overrides[db_session]():
        db.add_all([User(id=5,name='Manager',email='manager2@example.test',department_id=1,role='Department Manager',active=True),User(id=6,name='Finance approver',email='finance2@example.test',department_id=2,role='Finance Approver',active=True),User(id=7,name='Executive',email='executive2@example.test',department_id=1,role='Employee',active=True)])
        db.add(UserCapability(user_id=7,capability='Executive Approver'));db.commit()
    details={'vendor':'Example','description':'Annual service','total_committed_amount':'20000.00','currency':'USD','business_justification':'Needed','contract_term':'One year','commitment_confirmed':True}
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'Service','description':'Service request','request_type':'Purchase Request','purchase_details':details});assert r.status_code==201
    rid=r.json()['id']; rows=pg_client.get(f'/api/v1/requests/{rid}/automation',headers=h(1)).json()['approvals']
    assert [a['required_role_or_capability'] for a in rows]==['Department Manager','Finance Approver','Executive Approver']
    assert pg_client.post(f'/api/v1/requests/{rid}/transition',headers=h(4),json={'status':'Triaged'}).status_code==200
    assert pg_client.post(f'/api/v1/requests/{rid}/transition',headers=h(4),json={'status':'In Progress'}).status_code==409
    assert pg_client.post(f"/api/v1/approvals/{rows[0]['id']}/decision",headers=h(1),json={'decision':'Approved'}).status_code==403
    for row,actor in zip(rows,[5,6,7]):
        assert pg_client.post(f"/api/v1/approvals/{row['id']}/decision",headers=h(actor),json={'decision':'Approved'}).status_code==200
    assert pg_client.post(f'/api/v1/requests/{rid}/transition',headers=h(4),json={'status':'In Progress'}).status_code==200
    assert pg_client.put(f'/api/v1/requests/{rid}/purchase-details',headers=h(1),json={**details,'total_committed_amount':'21000.00'}).status_code==200
    state=pg_client.get(f'/api/v1/requests/{rid}/automation',headers=h(1)).json()
    assert state['approval_state']=='Needs resubmission' and all(x['status']=='Invalidated' and x['decision_outcome']=='Approved' for x in state['approvals'])
    assert pg_client.post(f'/api/v1/requests/{rid}/transition',headers=h(4),json={'status':'Resolved'}).status_code==409

def test_postgres_escalation_worker_repeat_and_acknowledgement(pg_client):
    from datetime import timedelta
    from sqlalchemy import select
    from app.models import Escalation, utcnow
    from app.workflows import evaluate_all, latest_sla
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'System outage','description':'Multiple users affected','request_type':'IT Incident','priority':'High'});assert r.status_code==201
    rid=r.json()['id'];now=utcnow()
    for db in app.dependency_overrides[db_session]():
        sla=latest_sla(db,rid);sla.response_due_at=now-timedelta(minutes=1);db.commit()
        evaluate_all(db,now);db.commit();evaluate_all(db,now);db.commit()
        escalations=db.scalars(select(Escalation).where(Escalation.request_id==rid)).all()
        assert len([e for e in escalations if e.kind=='overdue'])==1
        assert len([e for e in escalations if e.kind=='unassigned'])==1
    assert pg_client.post(f'/api/v1/requests/{rid}/acknowledge',headers=h(4)).status_code==200
    state=pg_client.get(f'/api/v1/requests/{rid}/automation',headers=h(1)).json()
    assert state['slas'][0]['breached_at'] is not None and state['slas'][0]['first_acknowledged_at'] is not None
    assert state['slas'][0]['escalation_status']=='Acknowledged'
    assert pg_client.get('/api/v1/incidents/attention',headers=h(4)).json()['items']==[]
