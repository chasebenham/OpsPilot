import type { Department, Event, User } from './api';

const labels: Record<string, string> = {
  created: 'Request submitted', status_changed: 'Status changed',
  assigned_department_id_changed: 'Department changed', assigned_user_id_changed: 'Assignee changed',
  title_changed: 'Title updated', description_changed: 'Description updated', priority_changed: 'Priority changed',
  clarification: 'Clarification added', ai_analysis_reviewed: 'AI recommendations reviewed',
  policy_routing: 'Routing decision recorded', policy_sla: 'Response target evaluated',
  policy_approval: 'Purchase approval updated', incident_acknowledged: 'Incident acknowledged',
  incident_escalated: 'Incident escalated', purchase_details_updated: 'Purchase details updated',
};
export function describeActivity(event: Event, users: User[], departments: Department[]) {
  const actor = event.actor_id === null ? 'System' : users.find(user => user.id === event.actor_id)?.name ?? 'Unknown user';
  const resolve = (value: string | null) => {
    if (value === null) return 'Unassigned';
    if (event.event_type === 'assigned_department_id_changed') return departments.find(d => String(d.id) === value)?.name ?? 'Unknown department';
    if (event.event_type === 'assigned_user_id_changed') return users.find(u => String(u.id) === value)?.name ?? 'Unknown user';
    return value;
  };
  let label = labels[event.event_type] ?? 'Request updated';
  let detail: string;
  if (event.event_type === 'created') detail = 'Submitted';
  else if (['policy_routing','policy_sla','policy_approval','incident_acknowledged','incident_escalated','purchase_details_updated'].includes(event.event_type)) detail = event.new_value ?? 'Updated';
  else if (event.event_type === 'description_changed') detail = 'Request description updated';
  else if (event.event_type === 'ai_analysis_reviewed') {
    if (actor !== 'Unknown user') label = `AI recommendations reviewed by ${actor}`;
    detail = event.new_value === 'accepted' ? 'Suggestions reviewed' : event.new_value === 'dismissed' ? 'Suggestions dismissed' : 'Review recorded';
  } else if (event.event_type === 'clarification') detail = event.new_value ?? '';
  else if (event.event_type === 'assigned_user_id_changed') {
    const assignee = resolve(event.new_value);
    label = event.new_value === null ? 'Assignment removed' : assignee === 'Unknown user' ? 'Assignee changed' : `Assigned to ${assignee}`;
    detail = `${resolve(event.previous_value)} → ${assignee}`;
  } else if (event.event_type === 'assigned_department_id_changed') {
    const department = resolve(event.new_value);
    label = event.new_value === null ? 'Department assignment removed' : department === 'Unknown department' ? 'Department changed' : `Department changed to ${department}`;
    detail = `${resolve(event.previous_value)} → ${department}`;
  } else if (event.event_type in labels) detail = `${resolve(event.previous_value)} → ${resolve(event.new_value)}`;
  else detail = 'Request updated';
  return { label, detail, actor };
}
