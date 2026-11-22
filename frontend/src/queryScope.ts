import type { Query } from '@tanstack/react-query';
const scoped = new Set(['analytics','impact','analytics-evaluations','evaluation-estimate','dashboard','requests','request','events','departments','ai-analyses','approvals','automation','incident-attention','projects','project','my-workflow-tasks']);
export function isRoleDependentQuery(query: Query) { return typeof query.queryKey[0] === 'string' && scoped.has(query.queryKey[0]); }
