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
    assert c.put(f'/api/v1/requests/{rid}/assignment', headers=h(4), json={'department_id': 1, 'user_id': 3}).status_code == 200
    assert c.post(f'/api/v1/requests/{rid}/transition', headers=h(3), json={'status': 'Resolved'}).status_code == 409
    for status in ('Triaged', 'In Progress', 'Resolved'):
        assert c.post(f'/api/v1/requests/{rid}/transition', headers=h(3), json={'status': status}).status_code == 200
    details = c.get(f'/api/v1/requests/{rid}', headers=h(1)).json()
    assert details['status'] == 'Resolved' and details['resolved_at'] is not None
    events = c.get(f'/api/v1/requests/{rid}/events', headers=h(1)).json()
    assert {e['event_type'] for e in events} >= {'created', 'assigned_department_id_changed', 'assigned_user_id_changed', 'status_changed'}
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
