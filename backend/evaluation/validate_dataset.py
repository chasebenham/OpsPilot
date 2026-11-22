"""Validate labels independently of the evaluated model; human review remains pending."""
import json
from pathlib import Path
from app.ai_schemas import ExtractedDetails

ROOT = Path(__file__).parent
def validate(cases):
    errors=[]; review=[]; ids=set()
    for case in cases:
        cid=case.get('id','<missing>')
        if cid in ids: errors.append(f'{cid}: duplicate id')
        ids.add(cid)
        if case.get('expected_type') not in ('IT Incident','Purchase Request','Cross-Department Project'): errors.append(f'{cid}: invalid category')
        priorities=case.get('expected_priority'); priorities=priorities if isinstance(priorities,list) else [priorities]
        if not priorities or any(p not in ('Low','Normal','High','Critical') for p in priorities): errors.append(f'{cid}: invalid priority')
        if case.get('expected_department') not in ('IT','Finance','Marketing','Operations','People & HR'): errors.append(f'{cid}: invalid department')
        if not isinstance(case.get('description'),str) or not case['description'].strip(): errors.append(f'{cid}: missing text')
        if not isinstance(case.get('mandatory_review'),bool): errors.append(f'{cid}: invalid review flag')
        if not isinstance(case.get('missing_keywords'),list): errors.append(f'{cid}: invalid missing keywords')
        if set(case.get('expected_extracted',{})) - set(ExtractedDetails.model_fields): errors.append(f'{cid}: invalid extraction fields')
        text=case.get('description','').lower()
        if ('per month' in text or 'monthly' in text) and 'total_committed_amount' in case.get('expected_extracted',{}) and 'total commitment' not in text: errors.append(f'{cid}: monthly amount is not total commitment')
        if case.get('review_status') != 'human_reviewed': review.append({'id':cid,'reason':case.get('adjudication_note','Human label review pending')})
    return {'dataset_version':'meridian-synthetic-100-v2','cases':len(cases),'errors':errors,'human_review_pending':review,'note':'Automated consistency checks are not independent expert review.'}

if __name__ == '__main__':
    result=validate(json.loads((ROOT/'cases-v2.json').read_text(encoding='utf-8')))
    (ROOT/'review-report-v2.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"{result['cases']} cases; {len(result['errors'])} errors; {len(result['human_review_pending'])} awaiting human review")
    if result['errors']: raise SystemExit(1)
