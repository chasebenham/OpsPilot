export function isAnalysisStale(source:string, current:string) { return source.trim() !== current.trim(); }
export function reviewedAnalysisPayload(analysisId:number|null,stale:boolean,acceptedFields:string[]) {
 return analysisId!==null&&!stale ? {analysis_id:analysisId,accepted_ai_fields:acceptedFields} : {};
}
