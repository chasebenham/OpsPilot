import { describe, expect, it } from 'vitest';
import { isAnalysisStale, reviewedAnalysisPayload } from './aiReview';
describe('reviewed AI analysis',()=>{
 it('does not attach results after the description changes',()=>{
  expect(isAnalysisStale('CRM unavailable','CRM is restored')).toBe(true);
  expect(reviewedAnalysisPayload(42,true,['priority'])).toEqual({});
 });
 it('records a dismissal with no accepted recommendations',()=>{
  expect(isAnalysisStale('CRM unavailable',' CRM unavailable ')).toBe(false);
  expect(reviewedAnalysisPayload(42,false,[])).toEqual({analysis_id:42,accepted_ai_fields:[]});
 });
});
