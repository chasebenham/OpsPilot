import { describe, expect, it } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { describeActivity } from './activity';
import { isRoleDependentQuery } from './queryScope';
import type { Event, User, Department } from './api';
const base:Event={id:1,request_id:7,actor_id:1,event_type:'assigned_user_id_changed',previous_value:null,new_value:'3',created_at:'2026-01-01T00:00:00Z'};
const users=[{id:1,name:'Admin',role:'Operations Admin',department_id:1},{id:3,name:'IT Agent',role:'Department Agent',department_id:1}] as User[];
const departments=[{id:1,name:'IT'}] as Department[];
describe('activity descriptions',()=>{
 it('resolves user and department IDs to readable names',()=>{
  expect(describeActivity(base,users,departments)).toEqual({label:'Assignee changed',detail:'Unassigned → IT Agent',actor:'Admin'});
  expect(describeActivity({...base,event_type:'assigned_department_id_changed',new_value:'1'},users,departments).detail).toBe('Unassigned → IT');
 });
 it('never displays unknown IDs or treats an unknown actor as the system',()=>{
  const result=describeActivity({...base,actor_id:99,new_value:'987'},users,departments);
  expect(result.detail).toBe('Unassigned → Unknown user'); expect(result.actor).toBe('Unknown user');
 });
 it('formats status and clarification actions',()=>{
  expect(describeActivity({...base,event_type:'status_changed',previous_value:'Submitted',new_value:'Triaged'},users,departments).detail).toBe('Submitted → Triaged');
  expect(describeActivity({...base,event_type:'clarification',new_value:'More information'},users,departments).detail).toBe('More information');
 });
});
it('resets cached role-dependent queries for all users while retaining the demo directory',async()=>{
 const client=new QueryClient();
 client.setQueryData(['dashboard',1],{total:5}); client.setQueryData(['requests',2],{total:2}); client.setQueryData(['users'],users);
 await client.resetQueries({predicate:isRoleDependentQuery});
 expect(client.getQueryData(['dashboard',1])).toBeUndefined(); expect(client.getQueryData(['requests',2])).toBeUndefined(); expect(client.getQueryData(['users'])).toEqual(users);
});
