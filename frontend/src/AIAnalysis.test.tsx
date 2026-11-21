// @vitest-environment jsdom
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnalysisHistory, AnalysisPanel } from './AIAnalysis';
import type { AIAnalysis } from './AIAnalysis';
import { applySuggestions, reviewedAnalysisPayload } from './aiReview';
import type { RequestValues, ReviewField } from './aiReview';

afterEach(cleanup);
const analysis: AIAnalysis = {
 id:1, request_id:7, initiated_by_user_id:1, model_name:'example-model', model_identifier:'example-v1',
 structured_result:{request_type:'IT Incident',suggested_priority:'High',suggested_department:'IT',summary:'CRM is unavailable',business_impact:'Sales cannot access CRM',extracted_details:{affected_system:'CRM'},missing_information:['When did the outage start?'],explanation:'An outage was reported.',needs_human_review:true},
 validation_flags:['Human review needed'],accepted_fields:['priority'],submitted_changes:{request_type:{suggested:'IT Incident',submitted:'IT Incident'},priority:{suggested:'High',submitted:'Normal'},department:{suggested:'IT',submitted:null}},review_decision:'accepted',created_at:'2026-01-01T12:00:00Z',reviewed_at:'2026-01-01T12:10:00Z',
};
function Harness({stale=false}:{stale?:boolean}) {
 const [values,setValues]=useState<RequestValues>({request_type:'Purchase Request',priority:'Normal'});
 const [selected,setSelected]=useState<ReviewField[]>([]);
 const apply=(fields:ReviewField[])=>{const next=applySuggestions(values,selected,analysis.structured_result,fields);setValues(next.values);setSelected(next.accepted)};
 return <><label>Editable priority<select value={values.priority} onChange={e=>setValues({...values,priority:e.target.value})}><option>Normal</option><option>High</option><option>Low</option></select></label><output data-testid="payload">{JSON.stringify(reviewedAnalysisPayload(analysis.id,stale,selected))}</output><AnalysisPanel analysis={analysis} values={values} selected={selected} onApply={apply} stale={stale}/></>;
}

describe('AI recommendation review',()=>{
 it('applies one recommendation, preserves other values, and records only the applied field',async()=>{
  const user=userEvent.setup();render(<Harness/>);
  await user.click(screen.getByRole('button',{name:'Apply priority suggestion: High'}));
  expect((screen.getByLabelText('Editable priority') as HTMLSelectElement).value).toBe('High');
  expect(screen.getByTestId('payload').textContent).toContain('"accepted_ai_fields":["priority"]');
  expect(screen.getByText('Applied')).toBeTruthy();
  expect(screen.getByRole('button',{name:'Apply request type suggestion: IT Incident'})).toBeTruthy();
  expect(screen.getByText('Recommendation only')).toBeTruthy();
  expect(screen.queryByRole('button',{name:/apply.*department/i})).toBeNull();
 });
 it('applies all applicable suggestions without recording the informational department',async()=>{
  const user=userEvent.setup();render(<Harness/>);await user.click(screen.getByRole('button',{name:'Apply all suggestions'}));
  expect(screen.getByTestId('payload').textContent).toContain('"accepted_ai_fields":["request_type","priority"]');
  expect(screen.getAllByText('Applied')).toHaveLength(2);
  expect(screen.getByText('Recommendation only')).toBeTruthy();
 });
 it('marks an applied field modified after a manual edit and allows reapplying it',async()=>{
  const user=userEvent.setup();render(<Harness/>);await user.click(screen.getByRole('button',{name:'Apply priority suggestion: High'}));
  await user.selectOptions(screen.getByLabelText('Editable priority'),'Low');
  expect(screen.getByText('Modified')).toBeTruthy();
  expect(screen.getByTestId('payload').textContent).toContain('"accepted_ai_fields":["priority"]');
  await user.click(screen.getByRole('button',{name:'Apply priority suggestion: High'}));
  expect(screen.getByText('Applied')).toBeTruthy();
 });
 it('marks matching values without falsely accepting them',()=>{
  render(<AnalysisPanel analysis={analysis} values={{request_type:'IT Incident',priority:'High'}} selected={[]} onApply={vi.fn()}/>);
  expect(screen.getAllByText('Matched')).toHaveLength(2);
  expect((screen.getByRole('button',{name:'Apply all suggestions'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('applies only conflicting fields when one recommendation already matches',async()=>{
  const user=userEvent.setup();const apply=vi.fn();
  render(<AnalysisPanel analysis={analysis} values={{request_type:'IT Incident',priority:'Normal'}} selected={[]} onApply={apply}/>);
  await user.click(screen.getByRole('button',{name:'Apply all suggestions'}));
  expect(apply).toHaveBeenCalledWith(['priority']);
 });
 it('disables stale applications and omits the stale analysis from submission',()=>{
  render(<Harness stale/>);expect(screen.getByRole('alert').textContent).toContain('description changed');
  expect((screen.getByRole('button',{name:'Apply all suggestions'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByTestId('payload').textContent).toBe('{}');
 });
 it('supports expandable detailed analysis and review history using keyboard controls',async()=>{
  const user=userEvent.setup();render(<AnalysisHistory analyses={[analysis]} loading={false} error={null} values={{request_type:'IT Incident',priority:'High',department:'Unassigned'}} users={[{id:1,name:'Alex',role:'Employee',department_id:1}]}/>);
  expect(screen.getByText('Current assignment: Unassigned')).toBeTruthy();
  expect(screen.getByText('Current request: High')).toBeTruthy();
  expect(screen.getByText('Submitted at review: Normal')).toBeTruthy();
  expect(screen.getByText('Human review needed')).toBeTruthy();
  expect(screen.getByText('Review: Modified')).toBeTruthy();
  const details=screen.getByText('View detailed analysis').closest('details')!;
  expect(details.open).toBe(false);screen.getByText('View detailed analysis').focus();await user.keyboard('{Enter}');expect(details.open).toBe(true);
  expect(within(details).getByText('CRM')).toBeTruthy();await user.keyboard('{Enter}');expect(details.open).toBe(false);
  const review=screen.getByText('Review details').closest('details')!;
  expect(review.open).toBe(false);await user.click(screen.getByText('Review details'));expect(review.open).toBe(true);
  expect(within(review).getByText(/Priority: suggested High; submitted Normal; review Modified/)).toBeTruthy();
  expect(within(review).getByText(/Department: suggested IT; submitted assignment not recorded/)).toBeTruthy();
 });
 it('renders loading, error, and empty history states',()=>{
  const props={values:{request_type:'IT Incident',priority:'High',department:'Unassigned'},users:[]};
  const view=render(<AnalysisHistory {...props} loading error={null}/>);expect(screen.getByRole('status').textContent).toContain('Loading');
  view.rerender(<AnalysisHistory {...props} loading={false} error={new Error('Network unavailable')}/>);expect(screen.getByRole('alert').textContent).toContain('Network unavailable');
  view.rerender(<AnalysisHistory {...props} loading={false} error={null} analyses={[]}/>);expect(screen.getByText('No reviewed AI analysis for this request.')).toBeTruthy();
 });
});
