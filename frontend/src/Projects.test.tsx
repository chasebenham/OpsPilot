// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {ProjectDetail,ProjectLink,Projects} from './Projects';
import type {User,Department,RequestItem} from './api';
const user:User={id:1,name:'Alex',role:'Employee',department_id:1};
const departments:Department[]=[{id:1,name:'IT'},{id:2,name:'Marketing'}];
const request:RequestItem={id:1,human_readable_id:'REQ-0001',title:'Campaign',description:'Coordinate a campaign',request_type:'Cross-Department Project',priority:'Normal',status:'Submitted',requester_id:1,assigned_department_id:2,assigned_user_id:null,created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z',resolved_at:null};
const draft={objective:'Launch',tasks:[{key:'brief',title:'Brief',description:'Write brief',department_id:2,assigned_user_id:null,priority:'Normal',required:true,due_at:null,depends_on:[]}],risks:[],missing_information:[],explanation:'',target_completion_date:null};
const project={workflow:{id:4,request_id:1,owner_user_id:1,status:'Draft',target_completion_date:null},request,plan:{id:3,version:1,source:'manual',status:'Draft',plan_data:draft},tasks:[],dependencies:[],events:[],can_manage:true,task_actions:{},stale:false};
function wrap(node:React.ReactNode,path='/workflows/4'){return <QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><MemoryRouter initialEntries={[path]}><Routes><Route path="/workflows/:id" element={node}/><Route path="/" element={node}/></Routes></MemoryRouter></QueryClientProvider>}
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe('project workflows',()=>{
 it('lists persisted projects and filters their status',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>String(url).includes('/workflow-tasks/mine')?[]:[project]})));const u=userEvent.setup();render(wrap(<Projects user={user} users={[user]} departments={departments}/>,'/'));
  expect(await screen.findByText('Campaign')).toBeTruthy();await u.selectOptions(screen.getByLabelText('Filter workflow status'),'Completed');expect(screen.getByText('No workflows match your filters.')).toBeTruthy();
 });
 it('edits and submits a draft plan without automatically activating it',async()=>{
  const f=vi.fn(async (_url:string,init?:RequestInit)=>({ok:true,json:async()=>init?.method?{version:2}:project}));vi.stubGlobal('fetch',f);const u=userEvent.setup();render(wrap(<ProjectDetail user={user} users={[user]} departments={departments}/>));
  const title=await screen.findByDisplayValue('Brief');await u.clear(title);await u.type(title,'Campaign brief');
  expect((screen.getByRole('button',{name:'Submit for review'}) as HTMLButtonElement).disabled).toBe(true);
  await u.click(screen.getByRole('button',{name:'Save plan'}));
  expect(f.mock.calls.some(([url,init])=>String(url).endsWith('/plan')&&init?.method==='PUT'&&String(init.body).includes('Campaign brief'))).toBe(true);
  expect(f.mock.calls.some(([url])=>String(url).endsWith('/activate'))).toBe(false);
 });
 it('shows dependencies and hides actions from users without task permission',async()=>{
  const active={...project,workflow:{...project.workflow,status:'Active'},can_manage:false,tasks:[{id:5,stable_task_key:'brief',title:'Brief',description:'Write',responsible_department_id:2,assigned_user_id:null,status:'In Progress',priority:'Normal',required:true,due_at:null},{id:6,stable_task_key:'launch',title:'Launch task',description:'Launch',responsible_department_id:1,assigned_user_id:null,status:'Blocked',priority:'Normal',required:true,due_at:null}],dependencies:[{id:1,predecessor_task_id:5,successor_task_id:6}],task_actions:{'5':false,'6':false}};
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>active})));const u=userEvent.setup();render(wrap(<ProjectDetail user={user} users={[user]} departments={departments}/>));
  expect(await screen.findByText('Launch task')).toBeTruthy();await u.click(within(screen.getByText('Launch task').closest('article')!).getByText('Task details'));expect(screen.getByText(/Waiting for: Brief/)).toBeTruthy();expect(screen.queryByRole('button',{name:'Start task'})).toBeNull();expect(screen.getByText(/Brief → Launch task/)).toBeTruthy();
 });
 it('provides request-detail integration for an existing project',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>[project]})));render(wrap(<ProjectLink request={request} user={user} users={[user]}/>,'/'));
  expect(await screen.findByRole('link',{name:'Open project workspace'})).toBeTruthy();
 });
 it('requires a fresh reviewed AI draft before activation',async()=>{
  const ai={...project,workflow:{...project.workflow,status:'Pending Review'},plan:{...project.plan,source:'AI-assisted',status:'Pending Review'},stale:true};
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>ai})));render(wrap(<ProjectDetail user={user} users={[user]} departments={departments}/>));
  expect((await screen.findByRole('alert')).textContent).toContain('description changed');
  expect((screen.getByRole('button',{name:'Approve & activate'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('shows API errors',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503,json:async()=>({detail:'Unavailable'})})));render(wrap(<Projects user={user} users={[user]} departments={departments}/>,'/'));expect((await screen.findAllByRole('alert'))[0].textContent).toContain('Unavailable');
 });
 it('shows assigned work without exposing a restricted parent project',async()=>{
  const task={id:9,workflow_id:88,title:'Prepare copy',description:'Write copy',department_id:1,assigned_user_id:1,status:'Ready',priority:'Normal',due_at:null,unmet_prerequisites:0,can_work:true};
  const fetcher=vi.fn(async(url:string,init?:RequestInit)=>({ok:true,json:async()=>init?.method?{status:'In Progress'}:String(url).includes('/workflow-tasks/mine')?[task]:[]}));vi.stubGlobal('fetch',fetcher);
  const u=userEvent.setup();render(wrap(<Projects user={user} users={[user]} departments={departments}/>,'/'));
  expect(await screen.findByRole('heading',{name:'My Tasks'})).toBeTruthy();expect(await screen.findByRole('heading',{name:'Projects'})).toBeTruthy();
  expect(await screen.findByText('Prepare copy')).toBeTruthy();expect(screen.getByText(/no full projects are available/i)).toBeTruthy();
  expect(screen.queryByText('Campaign')).toBeNull();expect(screen.getByText(/Department: IT/)).toBeTruthy();
  await u.click(screen.getByRole('button',{name:'Start task: Prepare copy'}));
  expect(fetcher.mock.calls.some(([url,init])=>String(url).includes('/workflows/88/tasks/9/transition')&&String(init?.body).includes('In Progress'))).toBe(true);
 });
});
