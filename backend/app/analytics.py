"""Scoped operational metrics. Periods select request-creation cohorts, not events."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from statistics import mean, median
from zoneinfo import ZoneInfo
import re

from sqlalchemy import func, select
from .models import (Request, RequestEvent, Department, PolicyDecision, Approval,
                     IncidentSLA, Escalation, ProjectWorkflow, WorkflowTask, WorkflowEvent, TaskDependency)

TZ = ZoneInfo('America/Phoenix')
OPEN = ('Submitted', 'Needs Information', 'Triaged', 'In Progress')
MIN_COHORT = 5

def privacy_report(report):
    """Release coarse fixed-cohort totals only; never expose breakdowns or durations.

    The source records can change between calls. Bucketing reduces disclosure but is
    not differential privacy and does not prevent inference from repeated snapshots.
    """
    def bucket(n):
        if n == 0: return '0–4'
        if n < MIN_COHORT: return '0–4'
        low = n // MIN_COHORT * MIN_COHORT
        return f'{low}–{low + MIN_COHORT - 1}'
    release = {
        'requests': ('total', 'open', 'resolved', 'closed'),
        'approvals': ('purchase_requests', 'awaiting', 'authorized', 'rejected'),
        'incidents': ('with_sla', 'acknowledged', 'overdue_unacknowledged', 'breached_recorded', 'escalated_incidents'),
        'workflows': (),
        'routing': (),
    }
    result = {'methodology': report['methodology'], 'filters': report['filters']}
    result['methodology']['privacy'] = 'Fixed cohort only; counts are ranges of five, including zero. Detailed breakdowns and durations are withheld to reduce differencing. Repeated changing snapshots and simulated identities still allow inference.'
    for section, names in release.items():
        result[section] = {name: bucket(report[section][name]) for name in names}
    return result

def boundary(day: date) -> datetime:
    return datetime.combine(day, time.min, TZ).astimezone(timezone.utc)

def durations(rows):
    values = []
    for start, end in rows:
        if start is not None and end is not None:
            seconds = (end.replace(tzinfo=timezone.utc) - start.replace(tzinfo=timezone.utc)).total_seconds()
            if seconds >= 0: values.append(seconds / 3600)
    return {'count': len(values), 'average_hours': round(mean(values), 2) if values else None,
            'median_hours': round(median(values), 2) if values else None}

def summary(db, visibility, start=None, end=None, department_id=None, request_type=None):
    filters = [visibility]
    if start: filters.append(Request.created_at >= boundary(start))
    if end: filters.append(Request.created_at < boundary(end + timedelta(days=1)))
    if department_id: filters.append(Request.assigned_department_id == department_id)
    if request_type: filters.append(Request.request_type == request_type)
    ids = select(Request.id).where(*filters)
    def grouped(column):
        return {str(key or 'Unassigned'): count for key, count in db.execute(select(column, func.count()).where(*filters).group_by(column))}
    statuses = grouped(Request.status)
    total = sum(statuses.values())
    first_resolution = (select(RequestEvent.request_id, func.min(RequestEvent.created_at).label('at'))
        .where(RequestEvent.event_type == 'status_changed', RequestEvent.new_value == 'Resolved', RequestEvent.request_id.in_(ids))
        .group_by(RequestEvent.request_id).subquery())
    resolution = durations(db.execute(select(Request.created_at, first_resolution.c.at).join(first_resolution, Request.id == first_resolution.c.request_id)))
    department = dict(db.execute(select(Department.name, func.count(Request.id)).join(Request, Request.assigned_department_id == Department.id).where(*filters).group_by(Department.name)).all())
    unassigned = db.scalar(select(func.count()).select_from(Request).where(*filters, Request.assigned_department_id.is_(None)))
    if unassigned: department['Unassigned'] = unassigned
    routes = dict(db.execute(select(PolicyDecision.outcome, func.count(func.distinct(PolicyDecision.request_id))).where(PolicyDecision.request_id.in_(ids), PolicyDecision.decision_type == 'routing').group_by(PolicyDecision.outcome)).all())
    versions = dict(db.execute(select(PolicyDecision.policy_version, func.count()).where(PolicyDecision.request_id.in_(ids)).group_by(PolicyDecision.policy_version)).all())
    latest_cycle = select(Approval.request_id, func.max(Approval.cycle).label('cycle')).where(Approval.request_id.in_(ids)).group_by(Approval.request_id).subquery()
    approval_rows = db.execute(select(Approval.request_id, Approval.status, Approval.created_at, Approval.decided_at).join(latest_cycle, (Approval.request_id == latest_cycle.c.request_id) & (Approval.cycle == latest_cycle.c.cycle))).all()
    cycles = {}
    for rid, status, created, decided in approval_rows: cycles.setdefault(rid, []).append((status, created, decided))
    authorized = [rows for rows in cycles.values() if rows and all(row[0] == 'Approved' for row in rows)]
    rejected = sum(any(row[0] == 'Rejected' for row in rows) for rows in cycles.values())
    waiting = sum(any(row[0] == 'Pending' for row in rows) and not any(row[0] == 'Rejected' for row in rows) for rows in cycles.values())
    approval_duration = durations([(min(r[1] for r in rows), max(r[2] for r in rows if r[2])) for rows in authorized if all(r[2] for r in rows)])
    stage_ready = {}
    for request_id, value, at in db.execute(select(RequestEvent.request_id, RequestEvent.new_value, RequestEvent.created_at).where(RequestEvent.request_id.in_(ids),RequestEvent.event_type=='approval_stage_ready')):
        match = re.match(r'Cycle (\d+), stage (\d+):', value or '')
        if match:
            key=(request_id,int(match.group(1)),int(match.group(2)))
            if key not in stage_ready or at < stage_ready[key]: stage_ready[key]=at
    stage_samples = {}
    for row in db.execute(select(Approval.request_id,Approval.cycle,Approval.approval_stage,Approval.required_role_or_capability,Approval.decided_at).where(Approval.request_id.in_(ids),Approval.decided_at.is_not(None))):
        start_at=stage_ready.get((row[0],row[1],row[2]))
        if start_at is not None: stage_samples.setdefault(row[3],[]).append((start_at,row[4]))
    stage_waiting={role:durations(samples) for role,samples in stage_samples.items()}
    latest_sla = select(IncidentSLA.request_id, func.max(IncidentSLA.revision).label('revision')).where(IncidentSLA.request_id.in_(ids)).group_by(IncidentSLA.request_id).subquery()
    slas = db.execute(select(Request.created_at, IncidentSLA.first_acknowledged_at, IncidentSLA.response_due_at, IncidentSLA.breached_at).join(IncidentSLA, IncidentSLA.request_id == Request.id).join(latest_sla, (IncidentSLA.request_id == latest_sla.c.request_id) & (IncidentSLA.revision == latest_sla.c.revision))).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    acknowledged = [r for r in slas if r[1]]
    timely = sum(r[1].replace(tzinfo=None) <= r[2].replace(tzinfo=None) for r in acknowledged)
    overdue = sum(not r[1] and r[2].replace(tzinfo=None) < now for r in slas)
    escalated = db.scalar(select(func.count(func.distinct(Escalation.request_id))).where(Escalation.request_id.in_(ids)))
    escalation_reasons = db.scalar(select(func.count()).select_from(Escalation).where(Escalation.request_id.in_(ids)))
    wf_ids = select(ProjectWorkflow.id).where(ProjectWorkflow.request_id.in_(ids))
    projects = dict(db.execute(select(ProjectWorkflow.status, func.count()).where(ProjectWorkflow.id.in_(wf_ids)).group_by(ProjectWorkflow.status)).all())
    tasks = dict(db.execute(select(WorkflowTask.status, func.count()).where(WorkflowTask.workflow_id.in_(wf_ids)).group_by(WorkflowTask.status)).all())
    task_times = durations(db.execute(select(WorkflowTask.started_at, WorkflowTask.completed_at).where(WorkflowTask.workflow_id.in_(wf_ids), WorkflowTask.status == 'Completed')))
    task_overdue = db.scalar(select(func.count()).select_from(WorkflowTask).where(WorkflowTask.workflow_id.in_(wf_ids), WorkflowTask.status.in_(['Ready','Blocked','In Progress']), WorkflowTask.due_at < datetime.now(timezone.utc)))
    handoffs = db.scalar(select(func.count()).select_from(WorkflowEvent).where(WorkflowEvent.workflow_id.in_(wf_ids), WorkflowEvent.event_type == 'task_unblocked'))
    readiness=(select(WorkflowEvent.task_id,func.min(WorkflowEvent.created_at).label('ready_at')).where(WorkflowEvent.workflow_id.in_(wf_ids),WorkflowEvent.event_type.in_(['task_ready','task_unblocked']),WorkflowEvent.task_id.is_not(None)).group_by(WorkflowEvent.task_id).subquery())
    ready_to_start=durations(db.execute(select(readiness.c.ready_at,WorkflowTask.started_at).join(WorkflowTask,WorkflowTask.id==readiness.c.task_id).where(WorkflowTask.started_at.is_not(None))))
    predecessors=(select(TaskDependency.successor_task_id.label('successor'),func.max(WorkflowTask.completed_at).label('finished_at'),func.count().label('total'),func.count(WorkflowTask.completed_at).label('completed')).join(WorkflowTask,WorkflowTask.id==TaskDependency.predecessor_task_id).where(TaskDependency.workflow_id.in_(wf_ids)).group_by(TaskDependency.successor_task_id).subquery())
    handoff_time=durations(db.execute(select(predecessors.c.finished_at,readiness.c.ready_at).join(readiness,readiness.c.task_id==predecessors.c.successor).where(predecessors.c.total==predecessors.c.completed)))
    local_created = func.timezone('America/Phoenix', Request.created_at) if db.bind.dialect.name == 'postgresql' else Request.created_at
    month = func.to_char(local_created, 'YYYY-MM') if db.bind.dialect.name == 'postgresql' else func.strftime('%Y-%m', local_created)
    volume = [{'month': key, 'count': count} for key,count in db.execute(select(month,func.count()).where(*filters).group_by(month).order_by(month))]
    def by_month(stamp, condition, entity):
        local = func.timezone('America/Phoenix', stamp) if db.bind.dialect.name == 'postgresql' else stamp
        bucket = func.to_char(local, 'YYYY-MM') if db.bind.dialect.name == 'postgresql' else func.strftime('%Y-%m', local)
        return [{'month':key,'count':count} for key,count in db.execute(select(bucket,func.count()).select_from(entity).where(*condition,stamp.is_not(None)).group_by(bucket).order_by(bucket))]
    # Cohort membership follows request creation filters; event months are actual
    # persisted timestamps, not reconstructed or manufactured history.
    acknowledgement_trend=by_month(IncidentSLA.first_acknowledged_at,[IncidentSLA.request_id.in_(ids),IncidentSLA.id.in_(select(IncidentSLA.id).join(latest_sla,(IncidentSLA.request_id==latest_sla.c.request_id)&(IncidentSLA.revision==latest_sla.c.revision)))],IncidentSLA)
    approval_trend=by_month(Approval.decided_at,[Approval.request_id.in_(ids),Approval.status.in_(['Approved','Rejected'])],Approval)
    completion_trend=by_month(ProjectWorkflow.completed_at,[ProjectWorkflow.request_id.in_(ids),ProjectWorkflow.status=='Completed'],ProjectWorkflow)
    return {
      'methodology': {'timezone':'America/Phoenix', 'period':'Inclusive local dates; request creation cohort. State metrics are current, not historical snapshots.', 'source':'Persisted demo-environment records; may include fictional seed and user-entered records, whose provenance is not separately tracked.', 'resolution':'First recorded transition to Resolved; missing event excluded.', 'sla':'Latest SLA revision; compliance denominator is acknowledged incidents only.', 'limitations':'Routing success is not routing correctness. Purchase authorization is not payment. No small-sample trend inference.'},
      'filters': {'start':start.isoformat() if start else None, 'end':end.isoformat() if end else None, 'department_id':department_id, 'request_type':request_type},
      'requests': {'total':total, 'open':sum(statuses.get(s,0) for s in OPEN), 'resolved':statuses.get('Resolved',0), 'closed':statuses.get('Closed',0), 'status':statuses, 'types':grouped(Request.request_type), 'priorities':grouped(Request.priority), 'departments':department, 'resolution':resolution, 'monthly_volume':volume},
      'routing': {'outcomes':routes, 'policy_versions':versions},
      'approvals': {'purchase_requests':grouped(Request.request_type).get('Purchase Request',0), 'awaiting':waiting, 'authorized':len(authorized), 'rejected':rejected, 'cycle_time':approval_duration, 'stage_waiting_time':stage_waiting, 'monthly_stage_decisions':approval_trend},
      'incidents': {'with_sla':len(slas), 'acknowledged':len(acknowledged), 'on_time':timely, 'compliance_rate':round(timely/len(acknowledged),4) if acknowledged else None, 'overdue_unacknowledged':overdue, 'breached_recorded':sum(bool(r[3]) for r in slas), 'escalated_incidents':escalated, 'escalation_records':escalation_reasons, 'acknowledgement_time':durations([(r[0],r[1]) for r in acknowledged]), 'monthly_acknowledgements':acknowledgement_trend},
      'workflows': {'projects':projects, 'tasks':tasks, 'overdue_tasks':task_overdue, 'handoffs':handoffs, 'task_completion_time':task_times, 'ready_to_start_time':ready_to_start, 'handoff_time':handoff_time, 'monthly_completed_projects':completion_trend},
    }

def financial_model(data):
    d = {k: Decimal(str(v)) for k,v in data.items()}
    annual = d['monthly_volume'] * 12
    eligible = annual * d['eligibility_rate']
    hours = eligible * d['automation_rate'] * (d['manual_minutes'] - d['review_minutes']) / 60
    labor = hours * d['hourly_cost']
    recurring = eligible * d['ai_cost'] + 12 * (d['infrastructure_monthly'] + d['maintenance_monthly'])
    benefit = labor - recurring
    first = benefit - d['implementation_cost']
    investment = recurring + d['implementation_cost']
    return {k: str(v.quantize(Decimal('.01'))) if v is not None else None for k,v in {
        'annual_requests':annual, 'eligible_requests':eligible, 'annual_hours_saved':hours, 'annual_labor_savings':labor,
        'annual_recurring_costs':recurring, 'annual_net_benefit':benefit, 'first_year_net_benefit':first,
        'roi_percent': first / investment * 100 if investment > 0 else None,
        'payback_months': d['implementation_cost'] / benefit * 12 if benefit > 0 else None}.items()}
