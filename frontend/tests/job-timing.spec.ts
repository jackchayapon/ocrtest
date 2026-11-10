import {test,expect} from '@playwright/test';
import {jobElapsedSeconds} from '../lib/job-timing';
import type {OCRJob} from '../lib/api';

const stamp='2026-11-08T00:00:00Z';
const job={status:'completed',created_at:stamp,started_at:stamp,finished_at:'2026-11-08T00:01:05Z',updated_at:'2026-11-08T01:00:00Z'} as OCRJob;
for(const status of ['completed','partial_success','failed','cancelled'] as const)test(`terminal ${status} elapsed uses persisted finish and never grows`,()=>{
 expect(jobElapsedSeconds({...job,status},Date.parse('2026-11-09T00:00:00Z'))).toBe(65);
 expect(jobElapsedSeconds({...job,status},Date.parse('2027-01-01T00:00:00Z'))).toBe(65);
});
test('historical finish fallback and malformed timestamps remain honest',()=>{
 expect(jobElapsedSeconds({...job,finished_at:null},0)).toBe(3600);
 expect(jobElapsedSeconds({...job,finished_at:'invalid'},0)).toBeNull();
 expect(jobElapsedSeconds({...job,finished_at:'2026-11-07T00:00:00Z'},0)).toBeNull();
 expect(jobElapsedSeconds({...job,finished_at:null,updated_at:''},Date.now())).toBeNull();
});
test('only active jobs use the live clock',()=>{
 expect(jobElapsedSeconds({...job,status:'running'},Date.parse(stamp)+7000)).toBe(7);
 expect(jobElapsedSeconds({...job,status:'queued',started_at:null},Date.parse(stamp)+9000)).toBe(9);
});
