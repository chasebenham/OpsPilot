"""Project plan validation and deterministic handoffs; callers lock the parent request."""
from fastapi import HTTPException
from sqlalchemy import select
from .models import Department, User, WorkflowPlan, WorkflowTask, TaskDependency, WorkflowEvent, utcnow
from .project_schemas import PlanDraft

def validate_graph(plan: PlanDraft):
    keys=[task.key for task in plan.tasks]
    if len(keys)!=len(set(keys)): raise HTTPException(422,'Task keys must be unique')
    graph={task.key:task.depends_on for task in plan.tasks}
    for task in plan.tasks:
        if len(task.depends_on)!=len(set(task.depends_on)): raise HTTPException(422,'Duplicate dependency')
        if task.key in task.depends_on: raise HTTPException(422,'A task cannot depend on itself')
        if any(dep not in graph for dep in task.depends_on): raise HTTPException(422,'Dependency references an unknown task')
    visiting=set();done=set()
    def visit(key):
        if key in visiting: raise HTTPException(422,'Circular dependency detected')
        if key in done: return
        visiting.add(key)
        for dep in graph[key]: visit(dep)
        visiting.remove(key);done.add(key)
    for key in graph: visit(key)

def validate_plan(db, plan: PlanDraft):
    validate_graph(plan)
    for task in plan.tasks:
        if not db.get(Department,task.department_id): raise HTTPException(422,f'Unknown department for {task.key}')
        if task.assigned_user_id:
            user=db.get(User,task.assigned_user_id)
            if not user or not user.active or user.department_id!=task.department_id: raise HTTPException(422,f'Assignee for {task.key} must be active in its department')

def log(db, workflow, kind, actor=None, task=None, **details):
    db.add(WorkflowEvent(workflow_id=workflow.id,task_id=task.id if task else None,actor_id=actor.id if actor else None,event_type=kind,structured_details=details))
    workflow.updated_at=utcnow()
def latest_plan(db, workflow_id):
    return db.scalar(select(WorkflowPlan).where(WorkflowPlan.workflow_id==workflow_id).order_by(WorkflowPlan.version.desc()))
def predecessors(db, task):
    return db.scalars(select(WorkflowTask).join(TaskDependency,TaskDependency.predecessor_task_id==WorkflowTask.id).where(TaskDependency.successor_task_id==task.id,TaskDependency.workflow_id==task.workflow_id)).all()
def unlock_dependents(db, workflow, task):
    successors=db.scalars(select(WorkflowTask).join(TaskDependency,TaskDependency.successor_task_id==WorkflowTask.id).where(TaskDependency.predecessor_task_id==task.id,TaskDependency.workflow_id==workflow.id)).all()
    for successor in successors:
        if successor.status=='Blocked' and all(p.status=='Completed' for p in predecessors(db,successor)):
            successor.status='Ready';successor.updated_at=utcnow()
            log(db,workflow,'task_unblocked',task=successor,predecessor=task.title)
def update_blocked_state(db, workflow):
    db.flush()
    tasks=db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id==workflow.id)).all()
    incomplete=any(t.required and t.status!='Completed' for t in tasks)
    actionable=any(t.status in ('Ready','In Progress') for t in tasks)
    workflow.status='Blocked' if incomplete and not actionable else 'Active'
def owner_or_manager(user, request, workflow):
    return user.id==workflow.owner_user_id or user.role=='Operations Admin' or (user.role=='Department Manager' and user.department_id==request.assigned_department_id)
def can_work(user, task):
    return user.role=='Operations Admin' or user.id==task.assigned_user_id or (user.role=='Department Manager' and user.department_id==task.responsible_department_id)
