// Optional tab-local navigation hints. PostgreSQL/API remain the source of job truth.
const knownJobs = new Map<string, string>();
const openedJobs = new Set<string>();
const key = (caseId: string) => `ocrlab-job:${caseId}`;

export function rememberJob(caseId: string, jobId: string) {
  knownJobs.set(caseId, jobId);
  try { localStorage.setItem(key(caseId), jobId); } catch { /* Optional hint. */ }
}

export function acknowledgeJob(caseId: string) {
  let jobId = knownJobs.get(caseId);
  try { jobId ??= localStorage.getItem(key(caseId)) ?? undefined; } catch { /* Optional hint. */ }
  if (!jobId) return;
  openedJobs.add(`${caseId}:${jobId}`);
  try { sessionStorage.setItem(`${key(caseId)}:opened`, jobId); } catch { /* In-tab hint remains available. */ }
}

export function jobWasOpened(caseId: string, jobId: string) {
  if (openedJobs.has(`${caseId}:${jobId}`)) return true;
  try { return sessionStorage.getItem(`${key(caseId)}:opened`) === jobId; } catch { return false; }
}
