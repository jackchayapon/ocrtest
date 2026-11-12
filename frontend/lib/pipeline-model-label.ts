import type {OCRModel, PipelineConfig} from "@/types";

export const versionLabel = (version: string, kind: OCRModel["kind"], source: OCRModel["source"]) => {
  if(source === "official") return kind === "det" && version === "6" ? "PP-OCRv6_medium_det" : kind === "rec" && version === "5" ? "th_PP-OCRv5_mobile_rec" : `PPOCR${version}_${kind}`;
  return version === "5" && kind === "det" ? "PPOCR5_server_det" : `PPOCR${version}_${kind}`;
};

// Read-only display metadata. Routing remains owned by the backend configuration.
export function pipelineModelDisplay(pipeline: PipelineConfig, kind: "det" | "rec") {
  if (pipeline.execution_mode === "external_api") return {name: pipeline.external_provider?.provider_name || "External OCR API", version: null, weight: null, summary: pipeline.external_provider?.provider_name || "External OCR API"};
  const model = kind === "det" ? pipeline.det_model : pipeline.rec_model;
  if (model) return {name: model.name, version: model.version, weight: model.weight, summary: `${model.name} / ${model.weight}`};
  const opts = pipeline.integrated_options;
  if (pipeline.execution_mode === "integrated") {
    if (pipeline.source === "official") {
      if (opts?.paddle_model_defaults !== false) return {name: "ตามค่า env ของ Gateway", version: null, weight: null, summary: "ตามค่า env ของ Gateway"};
      const version = opts[`${kind}_version`] ?? null;
      const weight = opts[`${kind}_weight`] ?? null;
      const name = versionLabel(version || "—", kind, "official");
      return {name, version, weight, summary: `${name} / ${weight ?? "—"}`};
    }
    const version = opts?.version ?? null;
    const weight = opts?.[`${kind}_weight`] ?? null;
    return {name: `V${version || "—"}`, version, weight, summary: `V${version || "—"} / ${weight || "—"}`};
  }
  return {name: "ไม่ได้เลือกโมเดล", version: null, weight: null, summary: "ไม่ได้เลือกโมเดล"};
}
