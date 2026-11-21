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
    return c.put(f'/api/v1/requests/{id}/assignment',headers=headers(5),json={'department_id':1,'user_id':3})
def test_create_validation_and_audit(env):
    r=create(env); assert r['status']=='Submitted' and r['human_readable_id'].startswith('REQ-')
    assert env.post('/api/v1/requests',headers=headers(1),json={'title':'  ','description':'x','request_type':'IT Incident'}).status_code==422
    assert env.post('/api/v1/requests',json={}).status_code==422
    events=env.get(f"/api/v1/requests/{r['id']}/events",headers=headers(1)).json()
    assert events[0]['event_type']=='created'
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
    for status in ('Triaged','In Progress'): assert env.post(f"/api/v1/requests/{r['id']}/transition",headers=headers(3),json={'status':status}).status_code==200
    assert env.post(f"/api/v1/requests/{r['id']}/transition",headers=headers(3),json={'status':'Resolved'}).status_code==409
