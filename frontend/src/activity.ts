import type { Department, Event, User } from './api';

const labels: Record<string, string> = {
  created: 'Request submitted',
  status_changed: 'Status changed',
  assigned_department_id_changed: 'Department changed',
  assigned_user_id_changed: 'Assignee changed',
  title_changed: 'Title updated',
  description_changed: 'Description updated',
  priority_changed: 'Priority changed',
  clarification: 'Clarification added',
};

export function describeActivity(event: Event, users: User[], departments: Department[]) {
  const resolve = (value: string | null) => {
    if (value === null) return 'Unassigned';
    if (event.event_type === 'assigned_department_id_changed') return departments.find(d => String(d.id) === value)?.name ?? 'Unknown department';
    if (event.event_type === 'assigned_user_id_changed') return users.find(u => String(u.id) === value)?.name ?? 'Unknown user';
    return value;
  };
  let detail: string;
  if (event.event_type === 'created') detail = 'Submitted';
  else if (event.event_type === 'description_changed') detail = 'Request description updated';
  else if (event.event_type === 'clarification') detail = event.new_value ?? '';
  else if (event.event_type in labels) detail = `${resolve(event.previous_value)} → ${resolve(event.new_value)}`;
  else detail = 'Request updated';
  return { label: labels[event.event_type] ?? 'Request updated', detail, actor: event.actor_id === null ? 'System' : users.find(u => u.id === event.actor_id)?.name ?? 'Unknown user' };
}
