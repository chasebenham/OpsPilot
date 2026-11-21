import { describe, expect, it } from 'vitest';
import { canManage, transitions } from './api';
import type { RequestItem, User } from './api';
const request = {assigned_department_id:1,assigned_user_id:3} as RequestItem;
describe('request controls',()=>{
  it('shows management controls only to an admin, the department manager or assigned agent',()=>{
    expect(canManage({id:1,role:'Employee',department_id:1} as User,request)).toBe(false);
    expect(canManage({id:3,role:'Department Agent',department_id:1} as User,request)).toBe(true);
    expect(canManage({id:4,role:'Department Manager',department_id:2} as User,request)).toBe(false);
    expect(canManage({id:5,role:'Operations Admin',department_id:2} as User,request)).toBe(true);
  });
  it('does not offer transitions from terminal states',()=>{
    expect(transitions.Closed).toEqual([]); expect(transitions.Cancelled).toEqual([]);
  });
});
