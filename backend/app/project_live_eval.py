"""Opt-in billable live AI plan validation for a fictional campaign."""
import argparse
from .models import SessionLocal, Department
from .project_ai import generate
from .project_schemas import PlanDraft
from .projects import validate_plan
from sqlalchemy import select

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live: parser.error('Pass --live to opt in to a billable API call')
    with SessionLocal() as db:
        departments=db.scalars(select(Department)).all();names={d.name:d.id for d in departments}
        plan,model,usage=generate('Coordinate a fictional campaign landing page with Marketing and IT.','Fictional campaign',list(names))
        if any(t.department not in names for t in plan.tasks): raise ValueError('AI proposed an unknown department')
        draft=PlanDraft.model_validate({'objective':plan.objective,'tasks':[{'key':t.key,'title':t.title,'description':t.description,'department_id':names[t.department],'priority':t.priority,'required':t.required,'depends_on':t.depends_on} for t in plan.tasks]})
        validate_plan(db,draft)
        print('Validated acyclic synthetic AI plan; model:',model)
        input_tokens=getattr(usage,'input_tokens',None);output_tokens=getattr(usage,'output_tokens',None)
        print('Input tokens:',input_tokens,'output tokens:',output_tokens)
        if model and model.startswith('gpt-6-luna') and input_tokens is not None and output_tokens is not None:
            print(f'Estimated uncached standard text cost: ${((input_tokens*0.10+output_tokens*0.50)/1000000):.8f}; actual billing may differ.')
        else: print('Cost estimate unavailable for this model; consult billing.')
if __name__=='__main__': main()
