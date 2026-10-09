import Link from "next/link";
import type { TestCase } from "@/types";

export const stages = ["upload", "layout", "pipelines", "ground-truth"] as const;
export type WorkflowStage = typeof stages[number];
export const stageTitles = ["Upload Document", "Global Layout", "Confirm Layout & Select Pipelines", "Ground Truth & Evaluation"];
export function workflowUrl(id: string, stage: WorkflowStage) { return `/workflow/${id}/${stage}`; }
export function resumeStage(c: TestCase): WorkflowStage {
  return c.runs.length ? "ground-truth" : c.layout_confirmed_at ? "pipelines" : "layout";
}
export default function WorkflowSteps({stage, saved, uploadUrl="/", busy=false}:{stage:WorkflowStage;saved?:TestCase|null;uploadUrl?:string;busy?:boolean}) {
  const reached = saved ? stages.indexOf(resumeStage(saved)) : 0;
  return <nav aria-label="ขั้นตอนทดสอบ" className="flex flex-wrap gap-2">{stages.map((s,i) => {
    const label = `${i+1}. ${["Upload","Global Layout","Pipelines","Ground Truth & Evaluation"][i]}`;
    const accessible = !busy && (i===0 || (saved && i<=reached));
    return accessible ? <Link key={s} href={i===0?uploadUrl:workflowUrl(saved!.id,s)+(stage==="pipelines"&&s==="ground-truth"?"?edit=1":"")} aria-current={stage===s?"step":undefined} className={`button ${stage===s?"primary":"secondary"}`}>{label}{i<reached?" ✓":""}</Link> : <span key={s} aria-disabled="true" className="button secondary opacity-50">{label}</span>;
  })}</nav>;
}
