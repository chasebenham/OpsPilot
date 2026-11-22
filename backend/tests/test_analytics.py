from datetime import date
from decimal import Decimal
from app.analytics import boundary, financial_model
from test_api import env, headers, create, mock_analysis

def test_period_boundaries_and_roi():
    assert boundary(date(2026, 1, 1)).hour == 7
    inputs = dict(monthly_volume=100, eligibility_rate='.5', automation_rate='.5', manual_minutes=20, review_minutes=8, hourly_cost=60, ai_cost='0.1', infrastructure_monthly=10, maintenance_monthly=10, implementation_cost=100)
    output = financial_model(inputs)
    assert Decimal(output['annual_hours_saved']) == 60
    assert Decimal(output['annual_labor_savings']) == 3600
    assert Decimal(output['annual_recurring_costs']) == 300
    assert Decimal(output['first_year_net_benefit']) == 3200
    inputs['review_minutes'] = 30
    assert financial_model(inputs)['payback_months'] is None
    inputs.update(monthly_volume=0,implementation_cost=0,infrastructure_monthly=0,maintenance_monthly=0)
    result=financial_model(inputs)
    assert result['roi_percent'] is None and result['payback_months'] is None

def test_synthetic_analytics_isolated_and_scoped(env, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models import Base, Department, Request, User
    from app import synthetic_dataset
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine); Session=sessionmaker(bind=engine,expire_on_commit=False)
    with Session() as demo:
        demo.add_all([Department(id=1,name='IT'),Department(id=2,name='Finance')]);demo.flush()
        demo.add(User(id=1,name='Synthetic',email='synthetic@example.test',department_id=1,role='Employee',active=True));demo.flush()
        demo.add(Request(title='Synthetic only',description='Synthetic',request_type='IT Incident',priority='High',status='Submitted',requester_id=1,assigned_department_id=1));demo.commit()
    monkeypatch.setattr(synthetic_dataset,'open_dataset',lambda:Session())
    create(env,'Real user content')
    response=env.get('/api/v1/analytics/synthetic',headers=headers(5))
    assert response.status_code==200, response.text
    assert response.json()['requests']['total']==1
    assert response.json()['requests']['types']=={'IT Incident':1}
    assert env.get('/api/v1/analytics/synthetic?request_type=Purchase%20Request',headers=headers(5)).json()['requests']['total']==0
    assert env.get('/api/v1/analytics/synthetic?start=2999-01-01',headers=headers(5)).json()['requests']['total']==0
    assert env.get('/api/v1/analytics/synthetic?department_id=2',headers=headers(4)).status_code==403
    assert env.get('/api/v1/analytics/synthetic',headers=headers(1)).status_code==403
    engine.dispose()

def test_synthetic_database_must_be_separate_and_local(monkeypatch):
    import pytest
    from app import synthetic_dataset
    monkeypatch.setattr(synthetic_dataset,'DATABASE_URL','postgresql+psycopg://opspilot:opspilot@localhost/opspilot_synthetic')
    with pytest.raises(ValueError): synthetic_dataset.validate_url('postgresql+psycopg://opspilot:opspilot@localhost/opspilot_synthetic')
    with pytest.raises(ValueError): synthetic_dataset.validate_url('postgresql+psycopg://opspilot:opspilot@remote.example/other_synthetic')
    with pytest.raises(ValueError): synthetic_dataset.validate_url('postgresql+psycopg://opspilot:opspilot@localhost/opspilot')
    synthetic_dataset.validate_url('postgresql+psycopg://opspilot:opspilot@localhost/other_synthetic')

def test_scoped_analytics_and_filters(env):
    create(env)
    assert env.get('/api/v1/analytics/overview',headers=headers(1)).status_code == 403
    response=env.get('/api/v1/analytics/overview',headers=headers(5))
    assert response.status_code == 200, response.text
    report=response.json()
    assert report['requests']['total'] == '0–4'
    assert report['requests']['open'] == '0–4'
    assert 'resolution' not in report['requests']
    assert env.get('/api/v1/analytics/overview?request_type=Purchase%20Request',headers=headers(5)).status_code == 403
    assert env.get('/api/v1/analytics/overview?start=2999-01-01',headers=headers(5)).status_code == 403
    assert env.get('/api/v1/analytics/overview?department_id=1',headers=headers(5)).status_code == 403
    assert env.get('/api/v1/analytics/overview?start=2026-02-01&end=2026-01-01',headers=headers(5)).status_code == 422

def test_evaluation_requires_admin_and_records_provider_failures(env, monkeypatch):
    from app import ai_service
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    calls=[]
    def fake(draft):
        calls.append(draft)
        if len(calls)==2: raise ai_service.AIServiceError('timeout','timeout')
        return mock_analysis()
    monkeypatch.setattr(ai_service,'analyze',fake)
    body={'case_limit':2,'budget_usd':10,'input_usd_per_million':1,'output_usd_per_million':5}
    assert env.post('/api/v1/analytics/evaluations',headers=headers(4),json=body).status_code==403
    response=env.post('/api/v1/analytics/evaluations',headers=headers(5),json=body)
    assert response.status_code==201, response.text
    result=response.json()
    assert result['successful']==1 and result['failed']==1
    assert result['provider_failure_rate']==0.5
    assert result['input_tokens']==100
    assert len(env.get('/api/v1/analytics/evaluations',headers=headers(5)).json())==1

def test_dataset_consistency_and_separate_review():
    from evaluation.validate_dataset import validate
    from app.evaluation_lab import cases
    report=validate(cases())
    assert report['cases']==100
    assert not report['errors']
    assert len(report['human_review_pending'])==100
    from app.evaluation_lab import select_cases
    assert {c['expected_type'] for c in select_cases(3)} == {'IT Incident','Purchase Request','Cross-Department Project'}
    assert select_cases(3,'sequential')[0]['id']=='case-01'

def test_concurrent_evaluation_is_rejected(env, monkeypatch):
    from app.models import AIEvaluationRun
    from app.main import db_session
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    with next(env.app.dependency_overrides[db_session]()) as db:
        db.add(AIEvaluationRun(dataset_version='test',model_name='test',prompt_version='test',created_by_user_id=5,status='Running',configuration={}))
        db.commit()
    body={'case_limit':1,'budget_usd':10,'input_usd_per_million':1,'output_usd_per_million':5}
    assert env.post('/api/v1/analytics/evaluations',headers=headers(5),json=body).status_code == 409
