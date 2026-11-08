import type {OCRJob} from './api';

/** Terminal jobs never use the viewing time as their completion time. */
export function jobElapsedSeconds(job: OCRJob | null, now: number): number | null {
  if (!job) return null;
  const start = Date.parse(job.started_at || job.created_at);
  const end = job.status === 'queued' || job.status === 'running'
    ? now : Date.parse(job.finished_at || job.updated_at || '');
  return Number.isFinite(start) && Number.isFinite(end) && end >= start
    ? Math.floor((end - start) / 1000) : null;
}
