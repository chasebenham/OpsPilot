"""Opt-in, billable evaluation: python -m evaluation.run --live"""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from app.ai_schemas import AnalyzeDraft
from app.ai_service import analyze, AIServiceError

def main():
    load_dotenv()
    parser=argparse.ArgumentParser(description='Run billable live analysis on synthetic cases')
    parser.add_argument('--live', action='store_true', help='Explicitly send the synthetic cases to OpenAI')
    parser.add_argument('--limit', type=int, default=30)
    args=parser.parse_args()
    if not args.live: parser.error('Pass --live to explicitly opt in to billable API calls')
    if not os.getenv('OPENAI_API_KEY'): parser.error('OPENAI_API_KEY is not configured')
    cases=json.loads((Path(__file__).parent/'cases.json').read_text(encoding='utf-8'))[:max(0,args.limit)]
    successes=errors=invalid=classification=priority=route=review_total=review_hit=extract_total=extract_hit=missing_total=missing_hit=inputs=outputs=0
    for case in cases:
        if case['mandatory_review']: review_total+=1
        try:
            response=analyze(AnalyzeDraft(description=case['description']))
            result=response.result; successes+=1
            classification+=result.request_type==case['expected_type']; priority+=result.suggested_priority==case['expected_priority']; route+=result.suggested_department==case['expected_department']
            if case['mandatory_review'] and result.needs_human_review: review_hit+=1
            details=result.extracted_details.model_dump()
            for key, expected in case['expected_extracted'].items():
                extract_total+=1; extract_hit+=expected.lower() in str(details.get(key) or '').lower()
            for keyword in case['missing_keywords']:
                missing_total+=1; missing_hit+=any(keyword.lower() in q.lower() for q in result.missing_information)
            inputs+=response.input_tokens or 0; outputs+=response.output_tokens or 0
        except AIServiceError as exc:
            errors+=1; invalid+=exc.category in ('invalid_output','incomplete')
            print(f"{case['id']}: {exc.category}")
    pct=lambda n,d: round(n/d*100,1) if d else None
    result={'cases':len(cases),'successful':successes,'classification_accuracy_percent':pct(classification,successes),'priority_agreement_percent':pct(priority,successes),'routing_agreement_percent':pct(route,successes),'critical_and_flagged_review_recall_percent':pct(review_hit,review_total),'extraction_field_match_percent':pct(extract_hit,extract_total),'missing_keyword_detection_percent':pct(missing_hit,missing_total),'invalid_output_rate_percent':pct(invalid,len(cases)),'error_rate_percent':pct(errors,len(cases)),'input_tokens':inputs,'output_tokens':outputs,'measured_spend':'not provided by API; consult billing'}
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()

