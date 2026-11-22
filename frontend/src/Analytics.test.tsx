// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {Analytics} from './Analytics';

afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});
it('loads synthetic metrics and applies request filters',async()=>{
 const fetcher=vi.fn(async(_url:string)=>({ok:true,json:async()=>({methodology:{period:'Creation cohort'},requests:{total:2,open:1},routing:{},approvals:{awaiting:0},incidents:{overdue_unacknowledged:0},workflows:{overdue_tasks:0}})}));
 vi.stubGlobal('fetch',fetcher);
 vi.stubGlobal('URL',{...URL,createObjectURL:vi.fn(()=> 'blob:report'),revokeObjectURL:vi.fn()});
 vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><Analytics user={{id:1,name:'Admin',role:'Operations Admin',department_id:1}} departments={[{id:1,name:'IT'}]}/></QueryClientProvider>);
 expect(await screen.findByText('Requests created')).toBeTruthy();
 await userEvent.selectOptions(screen.getByLabelText('Request type'),'IT Incident');
 expect(fetcher.mock.calls.some((args:any[])=>String(args[0]).includes('request_type=IT'))).toBe(true);
 await userEvent.click(screen.getByRole('button',{name:'Export report'}));
 expect(URL.createObjectURL).toHaveBeenCalled();
});
it('reports an API failure',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:403,json:async()=>({detail:'Not authorized'})})));
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><Analytics user={{id:1,name:'Admin',role:'Operations Admin',department_id:1}} departments={[]}/></QueryClientProvider>);
 expect((await screen.findByRole('alert')).textContent).toContain('Not authorized');
});
it('changes illustrative ROI scenarios and exports the results',async()=>{
 const fetcher=vi.fn(async(url:string,init?:RequestInit)=>({ok:true,json:async()=>url.includes('/analytics/impact')?{results:{annual_hours_saved:'100.00'},assumptions:JSON.parse(String(init?.body)),methodology:'Illustrative formula',source:'Assumed'}:{methodology:{period:'Creation cohort'},requests:{total:2,open:1},routing:{},approvals:{awaiting:0},incidents:{overdue_unacknowledged:0},workflows:{overdue_tasks:0}}}));
 vi.stubGlobal('fetch',fetcher);vi.stubGlobal('URL',{...URL,createObjectURL:vi.fn(()=> 'blob:test'),revokeObjectURL:vi.fn()});
 vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><Analytics user={{id:1,name:'Admin',role:'Operations Admin',department_id:1}} departments={[]}/></QueryClientProvider>);
 await userEvent.click(await screen.findByRole('button',{name:'Business impact'}));
 await screen.findByText('100.00');
 await userEvent.selectOptions(screen.getByLabelText('Scenario preset'),'Conservative');
 expect((screen.getByLabelText('AI eligibility rate (0–1)') as HTMLInputElement).value).toBe('0.4');
 await userEvent.selectOptions(screen.getByLabelText('Scenario preset'),'Optimistic');
 expect((screen.getByLabelText('AI eligibility rate (0–1)') as HTMLInputElement).value).toBe('0.85');
 await userEvent.selectOptions(screen.getByLabelText('Scenario preset'),'Base');
 expect((screen.getByLabelText('AI eligibility rate (0–1)') as HTMLInputElement).value).toBe('0.7');
 await userEvent.click(screen.getByText('Formula and assumptions'));
 await userEvent.click(screen.getByRole('button',{name:'Export scenario'}));
 expect(URL.createObjectURL).toHaveBeenCalled();
 await userEvent.clear(screen.getByLabelText('Monthly requests'));
 expect(screen.getByText('Enter all assumptions to calculate this scenario.')).toBeTruthy();
});
it('keeps the impact calculator available when the synthetic database is unavailable',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.includes('/analytics/impact')?{ok:true,json:async()=>({results:{annual_requests:'7200.00'},methodology:'Formula',source:'Assumed'})}:{ok:false,status:503,json:async()=>({detail:'Synthetic dataset unavailable'})}));
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><Analytics user={{id:1,name:'Admin',role:'Operations Admin',department_id:1}} departments={[]}/></QueryClientProvider>);
 expect(await screen.findByRole('alert')).toBeTruthy();
 await userEvent.click(screen.getByRole('button',{name:'Business impact'}));
 expect(await screen.findByText('7200.00')).toBeTruthy();
});
