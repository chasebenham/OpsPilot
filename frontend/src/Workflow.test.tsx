// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {ApprovalActions,PurchaseFields,SLAView,emptyPurchase} from './Workflow';
import type {User} from './api';
const user={id:2,name:'Finance',role:'Finance Approver',department_id:2} as User;
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
function withQuery(node:React.ReactNode){return <QueryClientProvider client={new QueryClient({defaultOptions:{mutations:{retry:false}}})}>{node}</QueryClientProvider>}
describe('workflow controls',()=>{
 it('requires a rejection reason and explicit confirmation before sending',async()=>{
  const u=userEvent.setup();const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({status:'Rejected'})});vi.stubGlobal('fetch',fetchMock);
  render(withQuery(<ApprovalActions id={5} user={user} onDone={()=>{}}/>));
  await u.click(screen.getByRole('button',{name:'Reject'}));expect(fetchMock).not.toHaveBeenCalled();
  const confirm=screen.getByRole('button',{name:'Confirm rejection'}) as HTMLButtonElement;expect(confirm.disabled).toBe(true);
  await u.type(screen.getByLabelText('Rejection reason'),'Missing justification');await u.click(confirm);
  expect(fetchMock).toHaveBeenCalledTimes(1);expect(fetchMock.mock.calls[0][1].body).toContain('Missing justification');
 });
 it('reports errors without hiding the pending decision',async()=>{
  const u=userEvent.setup();vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:403,json:async()=>({detail:'Not permitted'})}));
  render(withQuery(<ApprovalActions id={5} user={user} onDone={()=>{}}/>));await u.click(screen.getByRole('button',{name:'Approve'}));await u.click(screen.getByRole('button',{name:'Confirm approval'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Not permitted');
 });
 it('shows incident target and unacknowledged escalation',()=>{
  render(<SLAView sla={{id:1,revision:1,priority_at_evaluation:'Critical',policy_version:'meridian-2026-01',response_due_at:'2020-01-01T00:00:00Z',first_acknowledged_at:null,breached_at:null,escalation_status:'Escalated'}}/>);
  expect(screen.getByText(/Overdue by/)).toBeTruthy();expect(screen.getByText(/Not acknowledged/)).toBeTruthy();expect(screen.getByText(/Escalated/)).toBeTruthy();
 });
 it('keeps a full-contract commitment explicit',()=>{render(<PurchaseFields value={emptyPurchase} onChange={()=>{}}/>);expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);expect(screen.getByText(/full committed amount/)).toBeTruthy()});
});
 it('shows action controls only for an actionable approval',async()=>{
  const {AutomationPanel}=await import('./Workflow');
  const request={id:12,human_readable_id:'REQ-0012',title:'Purchase',description:'Detail',request_type:'Purchase Request',priority:'Normal',status:'Submitted',requester_id:1,assigned_department_id:2,assigned_user_id:null,created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z',resolved_at:null};
  const approval={id:4,request_id:12,cycle:1,approval_stage:1,required_role_or_capability:'Finance Approver',assigned_approver_id:2,status:'Pending',decision_actor_id:null,decision_reason:null,policy_version:'v1',created_at:'2026-01-01T00:00:00Z',decided_at:null};
  vi.stubGlobal('fetch',vi.fn(async (url:string)=>({ok:true,json:async()=>url.endsWith('/approvals')?[{request,approval,actionable:false,approval_state:'Pending'}]:{purchase:null,approval_state:'Pending',approvals:[approval],slas:[],escalations:[],decisions:[],can_acknowledge:false}})));
  render(withQuery(<AutomationPanel request={request} user={user} users={[user]} departments={[]}/>));
  await screen.findByText(/Purchase approval/);expect(screen.queryByRole('button',{name:'Approve'})).toBeNull();expect(screen.queryByRole('button',{name:'Reject'})).toBeNull();
 });
