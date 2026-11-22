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

def test_postgres_analytics_and_synthetic_evaluation_persistence(pg_client, monkeypatch):
    from app import ai_service
    from test_api import mock_analysis
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    monkeypatch.setattr(ai_service, 'analyze', lambda draft: mock_analysis())
    c=pg_client
    created=c.post('/api/v1/requests', headers=h(1), json={'title':'Test incident','description':'CRM issue','request_type':'IT Incident','priority':'High'})
    assert created.status_code == 201
    summary=c.get('/api/v1/analytics/overview', headers=h(4))
    assert summary.status_code == 200, summary.text
    assert summary.json()['requests']['total'] == '0–4'
    assert c.get('/api/v1/analytics/overview?request_type=IT%20Incident', headers=h(4)).status_code == 403
    assert c.get('/api/v1/analytics/overview',headers=h(1)).status_code == 403
    run=c.post('/api/v1/analytics/evaluations',headers=h(4),json={'case_limit':1,'budget_usd':10,'input_usd_per_million':1,'output_usd_per_million':5})
    assert run.status_code==201, run.text
    assert c.get('/api/v1/analytics/evaluations',headers=h(4)).json()[0]['id']==run.json()['id']

def test_postgres_synthetic_analytics_trends_and_filters(pg_client, monkeypatch):
    from contextlib import contextmanager
    from app import synthetic_dataset
    @contextmanager
    def test_dataset():
        yield from app.dependency_overrides[db_session]()
    monkeypatch.setattr(synthetic_dataset,'open_dataset',test_dataset)
    c=pg_client
    for kind in ('IT Incident','Purchase Request'):
        assert c.post('/api/v1/requests',headers=h(1),json={'title':kind,'description':'Fictional test request','request_type':kind,'priority':'High'}).status_code==201
    report=c.get('/api/v1/analytics/synthetic',headers=h(4))
    assert report.status_code==200, report.text
    assert report.json()['requests']['total']==2
    assert sum(x['count'] for x in report.json()['requests']['monthly_volume'])==2
    assert c.get('/api/v1/analytics/synthetic?request_type=IT%20Incident',headers=h(4)).json()['requests']['total']==1
    assert c.get('/api/v1/analytics/synthetic?start=2999-01-01',headers=h(4)).json()['requests']['total']==0
    assert c.get('/api/v1/analytics/synthetic',headers=h(1)).status_code==403

def test_postgres_evaluation_concurrent_run_protection(pg_client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app import ai_service
    from test_api import mock_analysis
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    entered=Event(); release=Event()
    def slow(_draft):
        entered.set()
        assert release.wait(10)
        return mock_analysis()
    monkeypatch.setattr(ai_service,'analyze',slow)
    body={'case_limit':1,'budget_usd':10,'input_usd_per_million':1,'output_usd_per_million':5}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(pg_client.post,'/api/v1/analytics/evaluations',headers=h(4),json=body)
        assert entered.wait(10)
        second=pool.submit(pg_client.post,'/api/v1/analytics/evaluations',headers=h(4),json=body)
        try: assert second.result(timeout=10).status_code==409
        finally: release.set()
        assert first.result(timeout=10).status_code==201

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

def test_postgres_concurrent_project_task_completion(pg_client):
    from concurrent.futures import ThreadPoolExecutor
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'Project','description':'Launch','request_type':'Cross-Department Project'}).json()
    wid=pg_client.post(f"/api/v1/requests/{r['id']}/workflow",headers=h(1)).json()['id']
    plan={'objective':'Launch','tasks':[{'key':'first','title':'First','description':'First task','department_id':1,'depends_on':[]},{'key':'next','title':'Next','description':'Next task','department_id':1,'depends_on':['first']}]}
    assert pg_client.put(f'/api/v1/workflows/{wid}/plan',headers=h(1),json=plan).status_code==200
    assert pg_client.post(f'/api/v1/workflows/{wid}/submit',headers=h(1)).status_code==200
    assert pg_client.post(f'/api/v1/workflows/{wid}/activate',headers=h(1)).status_code==200
    tasks=pg_client.get(f'/api/v1/workflows/{wid}',headers=h(1)).json()['tasks'];tid=tasks[0]['id']
    assert pg_client.post(f'/api/v1/workflows/{wid}/tasks/{tid}/transition',headers=h(4),json={'status':'In Progress'}).status_code==200
    def finish(_): return pg_client.post(f'/api/v1/workflows/{wid}/tasks/{tid}/transition',headers=h(4),json={'status':'Completed'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=sorted(pool.map(finish,range(2)))
    assert results==[200,409]
    snap=pg_client.get(f'/api/v1/workflows/{wid}',headers=h(1)).json()
    assert len([e for e in snap['events'] if e['event_type']=='task_unblocked'])==1
    assert snap['tasks'][1]['status']=='Ready'
    next_id=snap['tasks'][1]['id']
    assert pg_client.post(f'/api/v1/workflows/{wid}/complete',headers=h(1)).status_code==409
    assert pg_client.post(f'/api/v1/workflows/{wid}/tasks/{next_id}/transition',headers=h(4),json={'status':'In Progress'}).status_code==200
    assert pg_client.post(f'/api/v1/workflows/{wid}/tasks/{next_id}/transition',headers=h(4),json={'status':'Completed'}).status_code==200
    assert pg_client.post(f'/api/v1/workflows/{wid}/complete',headers=h(1)).json()['status']=='Completed'
    assert pg_client.get(f"/api/v1/requests/{r['id']}",headers=h(1)).json()['status']=='Resolved'

@pytest.mark.parametrize('change', ['plan','description','activation','deactivate_user'])
def test_postgres_ai_planning_does_not_lock_or_overwrite_changes(pg_client,monkeypatch,change):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from app import project_ai
    from app.models import User
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'Concurrent project','description':'Original project','request_type':'Cross-Department Project'}).json()
    wid=pg_client.post(f"/api/v1/requests/{r['id']}/workflow",headers=h(1)).json()['id']
    original={'objective':'Original plan','tasks':[{'key':'one','title':'Original','description':'Work','department_id':1,'depends_on':[]}]}
    assert pg_client.put(f'/api/v1/workflows/{wid}/plan',headers=h(1),json=original).status_code==200
    if change=='activation': assert pg_client.post(f'/api/v1/workflows/{wid}/submit',headers=h(1)).status_code==200
    entered=Event();release=Event()
    proposed=project_ai.SuggestedPlan(objective='AI proposal',tasks=[project_ai.SuggestedTask(key='ai',title='AI task',description='Work',department='IT',priority='Normal',required=True,depends_on=[])],deliverables=[],missing_information=[],risks=[],explanation='Review')
    def slow_provider(*args):
        entered.set()
        if not release.wait(8): raise RuntimeError('Test provider release timed out')
        return proposed,'test',SimpleNamespace(input_tokens=1,output_tokens=1)
    monkeypatch.setattr(project_ai,'generate',slow_provider)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ai=pool.submit(pg_client.post,f'/api/v1/workflows/{wid}/generate-plan',headers=h(1))
        try:
            assert entered.wait(5)
            if change=='plan':
                edit=pool.submit(pg_client.put,f'/api/v1/workflows/{wid}/plan',headers=h(1),json={**original,'objective':'Concurrent manual edit'})
            elif change=='description':
                edit=pool.submit(pg_client.patch,f"/api/v1/requests/{r['id']}",headers=h(4),json={'description':'Changed description'})
            elif change=='activation':
                edit=pool.submit(pg_client.post,f'/api/v1/workflows/{wid}/activate',headers=h(1))
            else:
                def deactivate():
                    for db in app.dependency_overrides[db_session]():
                        db.get(User,1).active=False;db.commit()
                    return 200
                edit=pool.submit(deactivate)
            changed=edit.result(timeout=4)
            assert (changed if change=='deactivate_user' else changed.status_code)==200
        finally:
            release.set()
        response=ai.result(timeout=8)
    assert response.status_code==(401 if change=='deactivate_user' else 409)
    # The admin remains able to inspect the workflow if the initiating user was deactivated.
    saved=pg_client.get(f'/api/v1/workflows/{wid}',headers=h(4)).json()
    assert saved['plan']['source']=='manual'
    assert saved['plan']['plan_data']['objective']==('Concurrent manual edit' if change=='plan' else 'Original plan')
    assert saved['workflow']['status']==('Active' if change=='activation' else 'Draft')

def test_postgres_simultaneous_ai_drafts_do_not_overwrite(pg_client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from types import SimpleNamespace
    from app import project_ai
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'Project','description':'Coordinate','request_type':'Cross-Department Project'}).json()
    wid=pg_client.post(f"/api/v1/requests/{r['id']}/workflow",headers=h(1)).json()['id']
    barrier=Barrier(2)
    plan=project_ai.SuggestedPlan(objective='AI proposal',tasks=[project_ai.SuggestedTask(key='a',title='Task',description='Work',department='IT',priority='Normal',required=True,depends_on=[])],deliverables=[],missing_information=[],risks=[],explanation='Review')
    def provider(*args):
        barrier.wait(timeout=8)
        return plan,'test',SimpleNamespace(input_tokens=1,output_tokens=1)
    monkeypatch.setattr(project_ai,'generate',provider)
    def request(_): return pg_client.post(f'/api/v1/workflows/{wid}/generate-plan',headers=h(1)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: statuses=sorted(pool.map(request,range(2)))
    assert statuses==[200,409]
    snapshot=pg_client.get(f'/api/v1/workflows/{wid}',headers=h(1)).json()
    assert snapshot['plan']['version']==1 and snapshot['plan']['source']=='AI-assisted'

def test_postgres_ai_rechecks_workflow_after_waiting_for_request_lock(pg_client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from sqlalchemy import event, select
    from app import project_ai
    from app.models import Request, ProjectWorkflow, WorkflowPlan, utcnow
    r=pg_client.post('/api/v1/requests',headers=h(1),json={'title':'Project','description':'Coordinate','request_type':'Cross-Department Project'}).json()
    wid=pg_client.post(f"/api/v1/requests/{r['id']}/workflow",headers=h(1)).json()['id']
    plan={'objective':'Manual','tasks':[{'key':'one','title':'One','description':'Work','department_id':1,'depends_on':[]}]}
    assert pg_client.put(f'/api/v1/workflows/{wid}/plan',headers=h(1),json=plan).status_code==200
    entered=Event();provider_release=Event();lock_query=Event()
    proposal=project_ai.SuggestedPlan(objective='AI',tasks=[project_ai.SuggestedTask(key='a',title='Task',description='Work',department='IT',priority='Normal',required=True,depends_on=[])],deliverables=[],missing_information=[],risks=[],explanation='Review')
    def provider(*args):
        entered.set()
        if not provider_release.wait(8): raise RuntimeError('Test provider timed out')
        return proposal,'test',SimpleNamespace(input_tokens=1,output_tokens=1)
    monkeypatch.setattr(project_ai,'generate',provider)
    generator=app.dependency_overrides[db_session]();session=next(generator);engine=session.get_bind()
    def observe(conn,cursor,statement,parameters,context,executemany):
        query=statement.upper()
        if 'FROM REQUESTS' in query and 'FOR UPDATE' in query: lock_query.set()
    listener_installed=False
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(pg_client.post,f'/api/v1/workflows/{wid}/generate-plan',headers=h(1))
        try:
            assert entered.wait(5)
            session.scalar(select(Request).where(Request.id==r['id']).with_for_update())
            workflow=session.get(ProjectWorkflow,wid);workflow.status='Pending Review';workflow.updated_at=utcnow()
            saved=session.scalar(select(WorkflowPlan).where(WorkflowPlan.workflow_id==wid));saved.status='Pending Review'
            session.flush()
            event.listen(engine,'before_cursor_execute',observe)
            listener_installed=True
            provider_release.set()
            assert lock_query.wait(5), 'AI request did not reach the request lock'
            session.commit()
            assert future.result(timeout=8).status_code==409
        finally:
            provider_release.set();session.rollback()
            if listener_installed: event.remove(engine,'before_cursor_execute',observe)
            generator.close()
    final=pg_client.get(f'/api/v1/workflows/{wid}',headers=h(1)).json()
    assert final['workflow']['status']=='Pending Review' and final['plan']['status']=='Pending Review'
