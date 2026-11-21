export type User={id:number;name:string;role:string;department_id:number};
export type Department={id:number;name:string};
export type RequestItem={id:number;human_readable_id:string;title:string;description:string;request_type:string;priority:string;status:string;requester_id:number;assigned_department_id:number|null;assigned_user_id:number|null;created_at:string;updated_at:string;resolved_at:string|null};
export type Event={id:number;request_id:number;actor_id:number|null;event_type:string;previous_value:string|null;new_value:string|null;created_at:string;request_reference?:string};
export type Page={items:RequestItem[];total:number;page:number;page_size:number};
export type Dashboard={total:number;open:number;attention:number;resolved:number;distribution:Record<string,number>;recent_activity:Event[];automation?:Record<string,number>};
export const types=['IT Incident','Purchase Request','Cross-Department Project'];
export const priorities=['Low','Normal','High','Critical'];
export const statuses=['Submitted','Needs Information','Triaged','In Progress','Resolved','Closed','Cancelled'];
export const transitions:Record<string,string[]>={'Submitted':['Needs Information','Triaged','Cancelled'],'Needs Information':['Submitted','Triaged','Cancelled'],'Triaged':['Needs Information','In Progress','Cancelled'],'In Progress':['Needs Information','Resolved','Cancelled'],'Resolved':['In Progress','Closed'],'Closed':[],'Cancelled':[]};
export async function api<T>(path:string,user:number|null,init?:RequestInit):Promise<T>{
 const headers:Record<string,string>={'Content-Type':'application/json'}; if(user) headers['X-Demo-User-Id']=String(user);
 let response:Response;
 try { response=await fetch('/api/v1'+path,{...init,headers:{...headers,...init?.headers}}); }
 catch { throw new Error('Cannot reach the API. Check that the frontend and backend servers are running, then retry.'); }
 if(!response.ok){
  let message=response.status>=500?'The API or its database is unavailable. Check that the backend and PostgreSQL are running, then run migrations and seed the database.':`Request failed (HTTP ${response.status}).`;
  try{const body=await response.json();if(typeof body.detail==='string')message=body.detail;else if(body.detail)message=JSON.stringify(body.detail)}catch{/* Keep the actionable fallback for empty proxy errors. */}
  throw new Error(message);
 }
 return response.json();
}
export const date=(s:string)=>new Date(s).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'});
export const canManage=(u:User,r:RequestItem)=>u.role==='Operations Admin'||(u.role==='Department Manager'&&u.department_id===r.assigned_department_id)||(u.role==='Department Agent'&&u.id===r.assigned_user_id);
