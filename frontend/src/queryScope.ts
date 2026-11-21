import type { Query } from '@tanstack/react-query';
const scoped = new Set(['dashboard','requests','request','events','departments','ai-analyses','approvals','automation','incident-attention']);
export function isRoleDependentQuery(query: Query) { return typeof query.queryKey[0] === 'string' && scoped.has(query.queryKey[0]); }
