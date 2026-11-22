"""Add only separately named fictional project demonstrations."""
from datetime import timedelta
from sqlalchemy import select
from .models import Department, User, Request, RequestEvent, ProjectWorkflow, WorkflowPlan, WorkflowTask, TaskDependency, utcnow
from . import workflows as routing, projects

def seed_projects(db):
    departments={d.name:d for d in db.scalars(select(Department)).all()}
    owner=db.scalar(select(User).where(User.email=='employee.3@meridian.example'))
    if not owner or any(x not in departments for x in ('IT','Finance','Marketing','Operations','People & HR')): return
    cases=[
      ('Marketing campaign launch','Active',[('brief','Marketing brief and copy','Marketing',[]),('design','Creative design','Marketing',['brief']),('compliance','Compliance review','Finance',['brief']),('landing','Landing page development','IT',['brief']),('qa','Quality assurance','Operations',['design','compliance','landing']),('launch','Launch authorization','Marketing',['qa'])]),
      ('Employee onboarding rollout','Pending Review',[('policy','Policy review','People & HR',[]),('accounts','Account provisioning','IT',['policy']),('equipment','Equipment coordination','Operations',['policy']),('onboard','Onboarding completion','People & HR',['accounts','equipment'])]),
      ('Internal process improvement','Completed',[('map','Process mapping','Operations',[]),('finance','Financial review','Finance',['map']),('implement','Implementation','IT',['map']),('signoff','Final operational sign-off','Operations',['finance','implement'])]),
      ('Future coordination draft','Draft',[('scope','Define scope','Operations',[])]),
    ]
    for title,state,definitions in cases:
        title='[Meridian project demo] '+title
        if db.scalar(select(Request.id).where(Request.title==title,Request.requester_id==owner.id)): continue
        now=utcnow();req=Request(title=title,description='Fictional cross-department coordination example.',request_type='Cross-Department Project',priority='Normal',status='Submitted',requester_id=owner.id)
        db.add(req);db.flush();req.human_readable_id=f'REQ-{req.id:04d}';db.add(RequestEvent(request_id=req.id,actor_id=owner.id,event_type='created',new_value='Submitted'));routing.route(db,req)
        workflow=ProjectWorkflow(request_id=req.id,owner_user_id=owner.id,status=state,activated_at=now if state in ('Active','Completed') else None,completed_at=now if state=='Completed' else None)
        db.add(workflow);db.flush()
        payload={'objective':'Coordinate the fictional '+title.split('] ',1)[1]+'.','tasks':[],'risks':[],'missing_information':[],'explanation':'Fictional manual demonstration plan.','target_completion_date':None}
        for key,task,dept,deps in definitions:
            assignee=db.scalar(select(User).where(User.department_id==departments[dept].id,User.role=='Department Agent',User.active.is_(True)).order_by(User.id))
            payload['tasks'].append({'key':key,'title':task,'description':task+' for the fictional project.','department_id':departments[dept].id,'assigned_user_id':assignee.id if assignee else None,'priority':'Normal','required':True,'due_at':(now-timedelta(days=1)).isoformat() if state=='Active' and key=='design' else None,'depends_on':deps})
        plan=WorkflowPlan(workflow_id=workflow.id,version=1,source='manual',status='Approved' if state in ('Active','Completed') else state,proposed_by_user_id=owner.id,approved_by_user_id=owner.id if state in ('Active','Completed') else None,approved_at=now if state in ('Active','Completed') else None,plan_data=payload)
        db.add(plan);db.flush();projects.log(db,workflow,'plan_saved',owner,version=1)
        if state in ('Active','Completed'):
            req.status='Resolved' if state=='Completed' else 'In Progress';req.resolved_at=now if state=='Completed' else None
            db.add(RequestEvent(request_id=req.id,actor_id=owner.id,event_type='status_changed',previous_value='Submitted',new_value=req.status))
            tasks={}
            for item in payload['tasks']:
                done=state=='Completed' or (state=='Active' and item['key']=='brief')
                task=WorkflowTask(workflow_id=workflow.id,plan_id=plan.id,stable_task_key=item['key'],title=item['title'],description=item['description'],responsible_department_id=item['department_id'],assigned_user_id=item['assigned_user_id'],status='Completed' if done else ('Ready' if item['depends_on']==['brief'] else 'Blocked'),priority='Normal',required=True,due_at=now-timedelta(days=1) if state=='Active' and item['key']=='design' else None,completed_at=now if done else None,started_at=now if done else None)
                db.add(task);db.flush();tasks[item['key']]=task
            for item in payload['tasks']:
                for dep in item['depends_on']: db.add(TaskDependency(workflow_id=workflow.id,predecessor_task_id=tasks[dep].id,successor_task_id=tasks[item['key']].id))
            projects.log(db,workflow,'workflow_activated',owner,version=1)
            if state=='Active':
                projects.log(db,workflow,'task_completed',owner,tasks['brief'],note='Fictional completed brief')
                for key in ('design','compliance','landing'): projects.log(db,workflow,'task_unblocked',task=tasks[key],predecessor=tasks['brief'].title)
            else:
                for task in tasks.values(): projects.log(db,workflow,'task_completed',owner,task,note='Fictional completed task')
                projects.log(db,workflow,'workflow_completed',owner)
    db.commit()
