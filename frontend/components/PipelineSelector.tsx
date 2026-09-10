import { messages, pipelineDescription, pipelineLabel, t } from "@/lib/i18n/th";
import type { PipelineConfig } from "@/types";

export const PIPELINE_COLORS: Record<string, string> = { mint: "#8b73d8", hutch_crop: "#4fa78f", hutch_full: "#db9b58" };
export default function PipelineSelector({ pipelines, selected, onChange, disabled }: { pipelines: PipelineConfig[]; selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  return <div className="pipeline-options">{pipelines.map(pipeline => <label className={`pipeline-option ${selected.includes(pipeline.pipeline_id) ? "chosen" : ""}`} key={pipeline.pipeline_id}><input type="checkbox" title={pipelineDescription[pipeline.pipeline_id]} aria-label={messages.selectPipeline(pipelineLabel(pipeline.pipeline_id, pipeline.name))} checked={selected.includes(pipeline.pipeline_id)} disabled={disabled || !pipeline.enabled} onChange={() => onChange(selected.includes(pipeline.pipeline_id) ? selected.filter(id => id !== pipeline.pipeline_id) : [...selected, pipeline.pipeline_id])} /><span className="pipeline-dot" style={{ background: PIPELINE_COLORS[pipeline.pipeline_id] }} />{pipelineLabel(pipeline.pipeline_id, pipeline.name)}{!pipeline.enabled && t(" (off)")}</label>)}</div>;
}
