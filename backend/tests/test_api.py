import os
os.environ['DATABASE_URL'] = 'sqlite://'
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Base, Department, User
from app.main import app, db_session

@pytest.fixture
def env():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record): connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        db.add_all([Department(id=1,name='IT'),Department(id=2,name='Finance')]); db.flush()
        db.add_all([User(id=1,name='Requester',email='a@example.test',department_id=1,role='Employee',active=True), User(id=2,name='Other',email='b@example.test',department_id=1,role='Employee',active=True), User(id=3,name='Agent',email='c@example.test',department_id=1,role='Department Agent',active=True), User(id=4,name='Manager',email='d@example.test',department_id=1,role='Department Manager',active=True), User(id=5,name='Admin',email='e@example.test',department_id=1,role='Operations Admin',active=True), User(id=6,name='Finance',email='f@example.test',department_id=2,role='Department Agent',active=True)]); db.commit()
    def override():
        with Session() as db: yield db
    app.dependency_overrides[db_session] = override
    with TestClient(app) as client: yield client
    app.dependency_overrides.clear(); engine.dispose()
def headers(id): return {'X-Demo-User-Id': str(id)}
def create(c, title='Printer broken'):
    result=c.post('/api/v1/requests',headers=headers(1),json={'title':title,'description':'Please help','request_type':'IT Incident','priority':'High'})
    assert result.status_code==201
    return result.json()
def assign(c,id):
    return c.put(f'/api/v1/requests/{id}/assignment',headers=headers(5),json={'department_id':1,'user_id':3,'reason':'Test routing override'})
def test_create_validation_and_audit(env):
    r=create(env); assert r['status']=='Submitted' and r['human_readable_id'].startswith('REQ-')
    assert env.post('/api/v1/requests',headers=headers(1),json={'title':'  ','description':'x','request_type':'IT Incident'}).status_code==422
    assert env.post('/api/v1/requests',json={}).status_code==422
    events=env.get(f"/api/v1/requests/{r['id']}/events",headers=headers(1)).json()
    assert any(e['event_type']=='created' for e in events)
def test_transitions_and_assignment(env):
    r=create(env); id=r['id']; assert env.put(f'/api/v1/requests/{id}/assignment',headers=headers(1),json={'department_id':1,'user_id':3}).status_code==403
    assert assign(env,id).status_code==200
    assert env.put(f'/api/v1/requests/{id}/assignment',headers=headers(5),json={'department_id':1,'user_id':6}).status_code==422
    assert env.post(f'/api/v1/requests/{id}/transition',headers=headers(3),json={'status':'Resolved'}).status_code==409
    assert env.post(f'/api/v1/requests/{id}/transition',headers=headers(3),json={'status':'Triaged'}).status_code==200
    assert env.post(f'/api/v1/requests/{id}/transition',headers=headers(3),json={'status':'In Progress'}).status_code==200
    assert env.post(f'/api/v1/requests/{id}/transition',headers=headers(3),json={'status':'Resolved'}).status_code==200
    events=env.get(f'/api/v1/requests/{id}/events',headers=headers(3)).json()
    assert sum(e['event_type']=='status_changed' for e in events)==3
    assert any(e['event_type']=='assigned_user_id_changed' for e in events)
def test_visibility_filters_dashboard_and_pagination(env):
    first=create(env); create(env,'Network down'); assign(env,first['id'])
    assert env.get(f"/api/v1/requests/{first['id']}",headers=headers(2)).status_code==404
    assert env.get(f"/api/v1/requests/{first['id']}/events",headers=headers(2)).status_code==404
    assert env.get('/api/v1/requests',headers=headers(2)).json()['total']==0
    assert env.get('/api/v1/requests?search=printer&priority=High&department_id=1',headers=headers(5)).json()['total']==1
    page=env.get('/api/v1/requests?page=2&page_size=1',headers=headers(5)).json(); assert page['total']==2 and len(page['items'])==1
    dashboard=env.get('/api/v1/dashboard',headers=headers(5)).json(); assert dashboard['total']==2 and dashboard['open']==2 and dashboard['attention']==2
    assert env.get('/api/v1/dashboard',headers=headers(2)).json()['total']==0
def test_purchase_cannot_complete_without_approval(env):
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'Software','description':'Need license','request_type':'Purchase Request'}).json(); assign(env,r['id'])
    assert env.post(f"/api/v1/requests/{r['id']}/transition",headers=headers(3),json={'status':'Triaged'}).status_code==200
    assert env.post(f"/api/v1/requests/{r['id']}/transition",headers=headers(3),json={'status':'In Progress'}).status_code==409

def test_demo_user_directory_reports_database_failure(env):
    from sqlalchemy.exc import OperationalError
    class BrokenDatabase:
        def scalars(self, statement):
            raise OperationalError('select users', {}, Exception('database offline'))
    def unavailable(): yield BrokenDatabase()
    app.dependency_overrides[db_session] = unavailable
    response = env.get('/api/v1/demo-users')
    assert response.status_code == 503
    assert 'Database unavailable or not initialized' in response.json()['detail']
    assert 'database offline' not in response.text

def mock_analysis():
    from app.ai_schemas import AnalysisResult, ExtractedDetails
    from app.ai_service import ProviderResult
    details = {key: None for key in ExtractedDetails.model_fields}; details['affected_system'] = 'CRM'
    result = AnalysisResult(request_type='IT Incident', suggested_priority='High', suggested_department='IT', summary='CRM unavailable', business_impact=None, extracted_details=details, missing_information=['How many users?'], explanation='Service issue', needs_human_review=True)
    return ProviderResult(result, ['Model recommends human review'], 'test-model', 'test-model-v1', 100, 50)

def test_ai_review_ownership_staleness_and_history(env, monkeypatch):
    from app import ai_service
    monkeypatch.setattr(ai_service, 'analyze', lambda draft: mock_analysis())
    response=env.post('/api/v1/ai/analyze-request',headers=headers(1),json={'description':'CRM is down'})
    assert response.status_code==201
    aid=response.json()['id']
    body={'title':'CRM','description':'CRM is down','request_type':'IT Incident','priority':'Normal','analysis_id':aid,'accepted_ai_fields':['priority']}
    assert env.post('/api/v1/requests',headers=headers(2),json=body).status_code==404
    assert env.post('/api/v1/requests',headers=headers(1),json={**body,'description':'Different description'}).status_code==409
    assert env.get('/api/v1/requests',headers=headers(1)).json()['total']==0
    created=env.post('/api/v1/requests',headers=headers(1),json=body); assert created.status_code==201
    rid=created.json()['id']; saved=env.get(f'/api/v1/requests/{rid}/ai-analyses',headers=headers(1)).json()[0]
    assert saved['review_decision']=='accepted' and saved['accepted_fields']==['priority']
    assert saved['submitted_changes']['priority']=={'suggested':'High','submitted':'Normal'}
    assert env.get(f'/api/v1/requests/{rid}/ai-analyses',headers=headers(2)).status_code==404
    assert env.post('/api/v1/requests',headers=headers(1),json=body).status_code==409
    assert any(e['event_type']=='ai_analysis_reviewed' for e in env.get(f'/api/v1/requests/{rid}/events',headers=headers(1)).json())

def test_ai_missing_key_and_dismissed_analysis(env, monkeypatch):
    from app import ai_service
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    assert env.post('/api/v1/ai/analyze-request',headers=headers(1),json={'description':'CRM is down'}).status_code==503
    assert create(env)['status']=='Submitted'
    monkeypatch.setattr(ai_service, 'analyze', lambda draft: mock_analysis())
    aid=env.post('/api/v1/ai/analyze-request',headers=headers(1),json={'description':'CRM is down'}).json()['id']
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'CRM','description':'CRM is down','request_type':'IT Incident','analysis_id':aid,'accepted_ai_fields':[]})
    assert r.status_code==201
    assert env.get(f"/api/v1/requests/{r.json()['id']}/ai-analyses",headers=headers(1)).json()[0]['review_decision']=='dismissed'
    assert env.post('/api/v1/ai/analyze-request',json={'description':'CRM is down'}).status_code==422
    assert env.post('/api/v1/ai/analyze-request',headers=headers(1),json={'description':'x'*10001}).status_code==422

def test_ai_service_flags_security_and_handles_refusal(env, monkeypatch):
    from types import SimpleNamespace
    from app import ai_service
    from app.ai_schemas import AnalyzeDraft
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    parsed=mock_analysis().result; parsed.suggested_priority='Critical'; parsed.needs_human_review=False
    response=SimpleNamespace(status='completed',output=[],output_parsed=parsed,usage=SimpleNamespace(input_tokens=2,output_tokens=3),model='test-v1')
    fake=SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs:response))
    monkeypatch.setattr(ai_service,'OpenAI',lambda **kwargs:fake)
    outcome=ai_service.analyze(AnalyzeDraft(description='Suspected phishing'))
    assert outcome.result.needs_human_review and len(outcome.flags)==2
    response.output=[SimpleNamespace(content=[SimpleNamespace(type='refusal')])]
    with pytest.raises(ai_service.AIServiceError,match='declined'): ai_service.analyze(AnalyzeDraft(description='test'))
    response.output=[]; response.status='incomplete'
    with pytest.raises(ai_service.AIServiceError,match='incomplete'): ai_service.analyze(AnalyzeDraft(description='test'))

def test_ai_provider_timeout_invalid_and_input_limit(env, monkeypatch):
    from types import SimpleNamespace
    import httpx
    from openai import APITimeoutError
    from app import ai_service
    from app.ai_schemas import AnalyzeDraft
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    def timeout(**kwargs): raise APITimeoutError(request=httpx.Request('POST','https://example.test'))
    fake=SimpleNamespace(responses=SimpleNamespace(parse=timeout))
    monkeypatch.setattr(ai_service,'OpenAI',lambda **kwargs:fake)
    with pytest.raises(ai_service.AIServiceError) as exc: ai_service.analyze(AnalyzeDraft(description='test'))
    assert exc.value.category=='timeout' and exc.value.status==504
    fake.responses.parse=lambda **kwargs:SimpleNamespace(status='completed',output=[],output_parsed=None)
    with pytest.raises(ai_service.AIServiceError) as exc: ai_service.analyze(AnalyzeDraft(description='test'))
    assert exc.value.category=='invalid_output'
    monkeypatch.setenv('OPENAI_MAX_INPUT_CHARS','3')
    with pytest.raises(ai_service.AIServiceError) as exc: ai_service.analyze(AnalyzeDraft(description='test'))
    assert exc.value.category=='input_too_long' and exc.value.status==422

def test_policy_thresholds_and_business_hours():
    from datetime import datetime, timezone
    from decimal import Decimal
    from app.policy import approval_stages, response_deadline
    assert approval_stages(Decimal('999.99'),'USD')==['Department Manager']
    assert approval_stages(Decimal('1000.00'),'USD')==['Department Manager','Finance Approver']
    assert approval_stages(Decimal('4999.99'),'USD')[-1]=='Finance Approver'
    assert approval_stages(Decimal('5000.00'),'USD')[-1]=='Operations Director'
    assert approval_stages(Decimal('19999.99'),'USD')[-1]=='Operations Director'
    assert approval_stages(Decimal('20000.00'),'USD')[-1]=='Executive Approver'
    with pytest.raises(ValueError): approval_stages(Decimal('1'),'EUR')
    friday=datetime(2026,11,20,23,0,tzinfo=timezone.utc)
    assert response_deadline(friday,'Critical')==datetime(2026,11,20,23,15,tzinfo=timezone.utc)
    assert response_deadline(friday,'High')==datetime(2026,11,21,0,0,tzinfo=timezone.utc)
    assert response_deadline(friday,'Normal')==datetime(2026,11,23,19,0,tzinfo=timezone.utc)
    assert response_deadline(friday,'Low')==datetime(2026,11,23,23,0,tzinfo=timezone.utc)

def test_approval_lifecycle_and_invalidation(env):
    from app.main import app, db_session
    from app.models import User, UserCapability
    for db in app.dependency_overrides[db_session]():
        db.add_all([User(id=7,name='Finance approver',email='fin@example.test',department_id=2,role='Finance Approver',active=True),User(id=8,name='Director',email='dir@example.test',department_id=1,role='Employee',active=True),User(id=9,name='Executive',email='exec@example.test',department_id=1,role='Employee',active=True)])
        db.add_all([UserCapability(user_id=8,capability='Operations Director'),UserCapability(user_id=9,capability='Executive Approver')]);db.commit()
    result=env.post('/api/v1/requests',headers=headers(1),json={'title':'New software','description':'Software needed','request_type':'Purchase Request'});assert result.status_code==201
    rid=result.json()['id'];assert result.json()['assigned_department_id']==2
    assert env.post(f'/api/v1/requests/{rid}/purchase/submit-approvals',headers=headers(1)).json()['approval_state']=='Needs information'
    detail={'vendor':'Example','description':'License','total_committed_amount':'5000.00','currency':'USD','business_justification':'Research','contract_term':'One year','commitment_confirmed':True}
    assert env.put(f'/api/v1/requests/{rid}/purchase-details',headers=headers(1),json=detail).status_code==200
    started=env.post(f'/api/v1/requests/{rid}/purchase/submit-approvals',headers=headers(1));assert started.json()['stages_created']==3
    rows=env.get(f'/api/v1/requests/{rid}/automation',headers=headers(1)).json()['approvals'];assert [x['required_role_or_capability'] for x in rows]==['Department Manager','Finance Approver','Operations Director']
    assert env.post(f"/api/v1/approvals/{rows[1]['id']}/decision",headers=headers(7),json={'decision':'Approved'}).status_code==409
    assert env.post(f"/api/v1/approvals/{rows[0]['id']}/decision",headers=headers(1),json={'decision':'Approved'}).status_code==403
    for row,actor in zip(rows,[4,7,8]):
        response=env.post(f"/api/v1/approvals/{row['id']}/decision",headers=headers(actor),json={'decision':'Approved'});assert response.status_code==200
        assert env.post(f"/api/v1/approvals/{row['id']}/decision",headers=headers(actor),json={'decision':'Approved'}).json()['idempotent']
    assert response.json()['approval_state']=='Authorized'
    assert env.put(f'/api/v1/requests/{rid}/purchase-details',headers=headers(1),json={**detail,'vendor':'Different vendor'}).json()['approval_state']=='Needs resubmission'

def test_routing_override_and_critical_escalation(env):
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'Outage','description':'System down','request_type':'IT Incident','priority':'Critical'}).json();rid=r['id']
    assert r['assigned_department_id']==1
    a=env.get(f'/api/v1/requests/{rid}/automation',headers=headers(1)).json()
    assert any(e['kind']=='critical' for e in a['escalations'])
    assert env.post(f'/api/v1/requests/{rid}/routing/reevaluate',headers=headers(1)).status_code==403
    assert env.post(f'/api/v1/requests/{rid}/routing/reevaluate',headers=headers(5)).json()['routed'] is False
    assert env.put(f'/api/v1/requests/{rid}/assignment',headers=headers(5),json={'department_id':2,'user_id':None}).status_code==422
    assert env.put(f'/api/v1/requests/{rid}/assignment',headers=headers(5),json={'department_id':2,'user_id':None,'reason':'Special routing'}).status_code==200

def test_missing_purchase_data_currency_and_rejection(env):
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'Subscription','description':'License','request_type':'Purchase Request'}).json();rid=r['id']
    incomplete={'vendor':'','description':'License','total_committed_amount':None,'currency':'EUR','business_justification':'Needed','contract_term':'Monthly','commitment_confirmed':False}
    hold=env.put(f'/api/v1/requests/{rid}/purchase-details',headers=headers(1),json=incomplete).json()['missing_information']
    assert 'vendor' in hold and 'total committed amount' in hold and 'confirmation of full contract commitment' in hold and 'supported USD currency' in hold
    assert env.post(f'/api/v1/requests/{rid}/purchase/submit-approvals',headers=headers(1)).json()['stages_created']==0
    complete={**incomplete,'vendor':'Acme','total_committed_amount':'500.00','currency':'USD','commitment_confirmed':True}
    assert env.put(f'/api/v1/requests/{rid}/purchase-details',headers=headers(1),json=complete).status_code==200
    assert env.post(f'/api/v1/requests/{rid}/purchase/submit-approvals',headers=headers(1)).json()['stages_created']==1
    aid=env.get(f'/api/v1/requests/{rid}/automation',headers=headers(1)).json()['approvals'][0]['id']
    assert env.post(f'/api/v1/approvals/{aid}/decision',headers=headers(4),json={'decision':'Rejected'}).status_code==422
    assert env.post(f'/api/v1/approvals/{aid}/decision',headers=headers(4),json={'decision':'Rejected','reason':'Not justified'}).json()['approval_state']=='Rejected'
    assert env.post(f'/api/v1/approvals/{aid}/decision',headers=headers(4),json={'decision':'Approved'}).status_code==409
    assert env.post(f'/api/v1/requests/{rid}/purchase/submit-approvals',headers=headers(1)).json()['stages_created']==1

def test_self_approval_and_missing_approver(env):
    details={'vendor':'Acme','description':'License','total_committed_amount':'300.00','currency':'USD','business_justification':'Needed','contract_term':'Annual','commitment_confirmed':True}
    r=env.post('/api/v1/requests',headers=headers(4),json={'title':'Manager purchase','description':'License','request_type':'Purchase Request','purchase_details':details}).json()
    a=env.get(f"/api/v1/requests/{r['id']}/automation",headers=headers(4)).json()['approvals'][0]
    assert a['assigned_approver_id'] is None
    assert env.post(f"/api/v1/approvals/{a['id']}/decision",headers=headers(4),json={'decision':'Approved'}).status_code==403

def test_sla_worker_idempotency_and_acknowledgement(env):
    from datetime import timedelta
    from app.main import app, db_session
    from app.models import Escalation, Request
    from app.workflows import evaluate_all, latest_sla, aware
    from sqlalchemy import select
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'High incident','description':'Issue','request_type':'IT Incident','priority':'High'}).json()
    for db in app.dependency_overrides[db_session]():
        sla=latest_sla(db,r['id']); simulated=aware(sla.response_due_at)+timedelta(minutes=1)
        evaluate_all(db,simulated);db.commit();evaluate_all(db,simulated);db.commit()
        rows=db.scalars(select(Escalation).where(Escalation.request_id==r['id'])).all()
        assert len([x for x in rows if x.kind=='overdue'])==1
        assert len([x for x in rows if x.kind=='unassigned'])==1
        assert latest_sla(db,r['id']).breached_at is not None
    assert env.post(f"/api/v1/requests/{r['id']}/acknowledge",headers=headers(1)).status_code==403
    assert env.post(f"/api/v1/requests/{r['id']}/acknowledge",headers=headers(5)).status_code==200
    assert env.post(f"/api/v1/requests/{r['id']}/acknowledge",headers=headers(5)).status_code==200

def test_all_routing_categories(env):
    from app.main import app, db_session
    from app.models import Department
    for db in app.dependency_overrides[db_session](): db.add(Department(id=3,name='Operations'));db.commit()
    for kind,department in [('IT Incident',1),('Purchase Request',2),('Cross-Department Project',3)]:
        r=env.post('/api/v1/requests',headers=headers(1),json={'title':'Test','description':'Detail','request_type':kind})
        assert r.status_code==201 and r.json()['assigned_department_id']==department
    assert env.post('/api/v1/requests',headers=headers(1),json={'title':'Test','description':'Detail','request_type':'Unknown'}).status_code==422

def test_sla_priority_change_preserves_revision_history(env):
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'Incident','description':'A problem','request_type':'IT Incident','priority':'Normal'}).json();rid=r['id']
    before=env.get(f'/api/v1/requests/{rid}/automation',headers=headers(1)).json()['slas'][0]
    assert env.patch(f'/api/v1/requests/{rid}',headers=headers(5),json={'priority':'Critical'}).status_code==200
    after=env.get(f'/api/v1/requests/{rid}/automation',headers=headers(1)).json()
    assert len(after['slas'])==2 and after['slas'][0]['priority_at_evaluation']=='Critical'
    assert after['slas'][1]['id']==before['id'] and after['slas'][1]['response_due_at']==before['response_due_at']
    assert any(e['kind']=='critical' for e in after['escalations'])

def test_missing_destination_manual_triage_is_idempotent(env):
    r=env.post('/api/v1/requests',headers=headers(1),json={'title':'Project','description':'Coordination','request_type':'Cross-Department Project'}).json();rid=r['id']
    assert r['assigned_department_id'] is None
    for _ in range(2): assert env.post(f'/api/v1/requests/{rid}/routing/reevaluate',headers=headers(5)).json()['routed'] is False
    decisions=env.get(f'/api/v1/requests/{rid}/automation',headers=headers(1)).json()['decisions']
    assert len([d for d in decisions if d['decision_type']=='routing' and d['outcome']=='manual_triage'])==1

def test_monetary_float_is_rejected(env):
    response=env.post('/api/v1/requests',headers=headers(1),json={'title':'Purchase','description':'License','request_type':'Purchase Request','purchase_details':{'total_committed_amount':25.55}})
    assert response.status_code==422

def test_revoked_approver_capability_disables_queue_action(env):
    from app.main import app, db_session
    from app.models import User
    detail={'vendor':'Acme','description':'License','total_committed_amount':'300.00','currency':'USD','business_justification':'Needed','contract_term':'Annual','commitment_confirmed':True}
    req=env.post('/api/v1/requests',headers=headers(1),json={'title':'Purchase','description':'License','request_type':'Purchase Request','purchase_details':detail}).json()
    aid=env.get(f"/api/v1/requests/{req['id']}/automation",headers=headers(1)).json()['approvals'][0]['id']
    assert env.get('/api/v1/approvals',headers=headers(4)).json()[0]['actionable'] is True
    for db in app.dependency_overrides[db_session](): db.get(User,4).role='Employee';db.commit()
    assert env.get('/api/v1/approvals',headers=headers(4)).json()[0]['actionable'] is False
    assert env.post(f'/api/v1/approvals/{aid}/decision',headers=headers(4),json={'decision':'Approved'}).status_code==403
