"""Explicit, synthetic-only evaluation. Never runs as part of normal requests."""
import hashlib
import json
import os
import time
from pathlib import Path
from statistics import mean, median
from . import ai_service
from .ai_schemas import AnalyzeDraft
from .models import AIEvaluationResult, AIEvaluationRun, utcnow

DATASET_VERSION = 'meridian-synthetic-100-v2'
PROMPT_VERSION = hashlib.sha256(ai_service.SYSTEM.encode()).hexdigest()[:12]
CATEGORIES = ('IT Incident', 'Purchase Request', 'Cross-Department Project')

def cases():
    return json.loads((Path(__file__).resolve().parent.parent / 'evaluation' / 'cases-v2.json').read_text(encoding='utf-8'))

def select_cases(limit, strategy='balanced'):
    rows=cases()
    if strategy == 'sequential': return rows[:limit]
    groups = {category: [c for c in rows if c['expected_type'] == category] for category in CATEGORIES}
    # Prioritize review-sensitive examples while interleaving categories.
    for group in groups.values():
        group.sort(key=lambda c: (not c.get('mandatory_review', False), c['id']))
    selected=[]
    while len(selected)<limit and any(groups.values()):
        for category in CATEGORIES:
            if groups[category] and len(selected)<limit: selected.append(groups[category].pop(0))
    return selected

def estimate(limit, input_price, output_price, strategy='balanced'):
    selected=select_cases(limit,strategy)
    max_output=int(os.getenv('OPENAI_MAX_OUTPUT_TOKENS', '2000'))
    return sum(((len((ai_service.SYSTEM + c['description']).encode('utf-8')) + 3000) * input_price + max_output * output_price) / 1_000_000 for c in selected)

def execute(db, actor, limit, budget, input_price, output_price, strategy='balanced'):
    selected = select_cases(limit,strategy)
    model = os.getenv('OPENAI_MODEL', 'gpt-6-luna')
    # Planning estimate, not a provider-enforced spending cap.
    estimated_max = estimate(limit, input_price, output_price, strategy)
    if estimated_max > budget: raise ValueError(f'Estimated maximum ${estimated_max:.4f} exceeds the requested budget. Reduce case count or increase budget.')
    digest=hashlib.sha256(json.dumps(cases(),sort_keys=True).encode()).hexdigest()
    run = AIEvaluationRun(dataset_version=DATASET_VERSION, model_name=model, prompt_version=PROMPT_VERSION, created_by_user_id=actor.id, status='Running', configuration={'case_limit':limit,'selection_strategy':strategy,'case_ids':[c['id'] for c in selected],'budget_usd':budget,'input_usd_per_million':input_price,'output_usd_per_million':output_price,'estimated_max_usd':estimated_max,'dataset_sha256':digest,'timeout_seconds':float(os.getenv('OPENAI_TIMEOUT_SECONDS','30')),'provider_retries':0})
    db.add(run); db.commit(); db.refresh(run)
    run_id = run.id
    db.rollback()  # Do not hold a database transaction during a provider call.
    consecutive_errors=0
    for case in selected:
        started = time.monotonic(); actual = None; error = None; inp = out = identifier = None
        try:
            result = ai_service.analyze(AnalyzeDraft(description=case['description']))
            actual = result.result.model_dump(mode='json'); inp = result.input_tokens; out = result.output_tokens; identifier = result.model_identifier
        except ai_service.AIServiceError as exc:
            error = exc.category
        except Exception:
            error = 'internal_error'
        consecutive_errors = consecutive_errors + 1 if error else 0
        elapsed = round((time.monotonic() - started)*1000)
        expected = {k:v for k,v in case.items() if k != 'description'}
        current=db.query(AIEvaluationRun).filter(AIEvaluationRun.id==run_id).with_for_update().one()
        if current.status != 'Running':
            db.rollback()
            return run_id
        if identifier:
            configuration=dict(current.configuration)
            configuration['model_identifiers']=sorted(set(configuration.get('model_identifiers',[])) | {identifier})
            current.configuration=configuration
        db.add(AIEvaluationResult(run_id=run_id, case_id=case['id'], expected=expected, actual=actual, error_category=error, latency_ms=elapsed, input_tokens=inp, output_tokens=out)); db.commit()
        if consecutive_errors >= 3: break
    run = db.query(AIEvaluationRun).filter(AIEvaluationRun.id==run_id).with_for_update().one()
    if run.status=='Running':
        run.status='Failed' if consecutive_errors >= 3 else 'Completed'; run.completed_at=utcnow(); db.commit()
    return run_id

def report(run, results):
    total = len(results); success = [r for r in results if r.actual is not None]
    ratio = lambda a,b: round(a/b,4) if b else None
    matrix = {c:{p:0 for p in CATEGORIES} for c in CATEGORIES}
    extraction_hit=extraction_total=missing_hit=missing_total=0
    review_hit=review_total=0; failures=[]
    for r in results:
        exp=r.expected; actual=r.actual or {}
        extraction_total+=len(exp.get('expected_extracted',{}))
        missing_total+=len(exp.get('missing_keywords',[]))
        if exp.get('mandatory_review'):
            review_total+=1; review_hit+=bool(actual.get('needs_human_review'))
        if r.actual:
            matrix[exp['expected_type']][actual['request_type']]+=1
            for key,value in exp.get('expected_extracted',{}).items():
                extraction_hit+=str(value).lower() in str(actual.get('extracted_details',{}).get(key) or '').lower()
            for word in exp.get('missing_keywords',[]):
                missing_hit+=any(word.lower() in q.lower() for q in actual.get('missing_information',[]))
        if r.error_category or actual.get('request_type') != exp['expected_type'] or (actual and actual.get('suggested_priority') not in (exp['expected_priority'] if isinstance(exp['expected_priority'],list) else [exp['expected_priority']])):
            failures.append({'case_id':r.case_id,'expected_type':exp['expected_type'],'actual_type':actual.get('request_type'),'expected_priority':exp['expected_priority'],'actual_priority':actual.get('suggested_priority'),'error_category':r.error_category})
    per_category={}; f1=[]
    for category in CATEGORIES:
        tp=matrix[category][category]; predicted=sum(matrix[e][category] for e in CATEGORIES); expected=sum(r.expected['expected_type']==category for r in results)
        precision=ratio(tp,predicted); recall=ratio(tp,expected)
        f=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else (0 if expected else None)
        if f is not None: f1.append(f)
        per_category[category]={'precision':precision,'recall':recall,'f1':round(f,4) if f is not None else None}
    inputs=sum(r.input_tokens or 0 for r in results); outputs=sum(r.output_tokens or 0 for r in results)
    pricing=run.configuration
    complete_usage=bool(results) and len(success)==len(results) and all(r.input_tokens is not None and r.output_tokens is not None for r in success)
    return {'id':run.id,'dataset_version':run.dataset_version,'model_name':run.model_name,'prompt_version':run.prompt_version,'status':run.status,'started_at':run.started_at,'completed_at':run.completed_at,'configuration':pricing,'cases_attempted':total,'successful':len(success),'failed':total-len(success),'classification_accuracy':ratio(sum(matrix[c][c] for c in CATEGORIES),total),'classification_accuracy_successful_only':ratio(sum(matrix[c][c] for c in CATEGORIES),len(success)),'priority_agreement':ratio(sum(r.actual['suggested_priority'] in (r.expected['expected_priority'] if isinstance(r.expected['expected_priority'],list) else [r.expected['expected_priority']]) for r in success),total),'department_accuracy':ratio(sum(r.actual['suggested_department']==r.expected['expected_department'] for r in success),total),'mandatory_review_recall':ratio(review_hit,review_total),'extraction_match':ratio(extraction_hit,extraction_total),'missing_keyword_recall':ratio(missing_hit,missing_total),'provider_failure_rate':ratio(sum(bool(r.error_category and r.error_category not in ('invalid_output','incomplete')) for r in results),total),'schema_failure_rate':ratio(sum(r.error_category in ('invalid_output','incomplete') for r in results),total),'macro_f1':round(mean(f1),4) if f1 else None,'per_category':per_category,'confusion_matrix':matrix,'failures':failures,'input_tokens':inputs,'output_tokens':outputs,'estimated_cost_usd':round((inputs*pricing['input_usd_per_million']+outputs*pricing['output_usd_per_million'])/1_000_000,6) if complete_usage else None,'average_latency_ms':round(mean(r.latency_ms for r in results),1) if results else None,'median_latency_ms':median(r.latency_ms for r in results) if results else None,'limitations':'Synthetic exploratory labels, not independently validated. Failures count against classification, extraction, missing keyword and review recall. Missing-keyword precision is not measurable with this dataset. Missing usage makes cost unavailable. Estimate is not actual billed spend.'}
