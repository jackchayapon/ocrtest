import { ReadCoordinator } from "@/lib/read-coordinator";
import { t, userError } from "@/lib/i18n/th";
import type { Category, CategoryAnalytics, Document, MatrixRow, PipelineConfig, QueryFilters, RunResponse, TestCase, TestCaseInput } from "@/types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export function assetUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
}

export const deletePipeline = (id: string) => request<void>(`/pipelines/${encodeURIComponent(id)}`, {method:"DELETE"});

const reads = new ReadCoordinator();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (typeof window === "undefined") return fetchJSON<T>(path, init);
  const method = (init?.method || "GET").toUpperCase();
  if (method === "GET") {
    return reads.read(path, key => fetchJSON<T>(key, init), !!init?.signal || !!init?.headers);
  }
  const value = await fetchJSON<T>(path, init);
  reads.mutated(path);
  return value;
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch (error) {
    if (init?.signal?.aborted) throw error;
    throw new Error(t("Cannot reach the backend. Check that the API is running and try again."));
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const detail = error?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg ?? t("Invalid input")).join(". ")
      : `Request failed (${response.status}). Please try again.`;
    throw new Error(userError(message, response.status));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function query(filters?: QueryFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters ?? {}).sort(([a], [b]) => a.localeCompare(b)).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  return params.size ? `?${params}` : "";
}

export const getUploadConfig = () => request<{ max_upload_mb: number; pdf_render_dpi: number }>("/upload-config");
export const getDocumentPage = (id: string, page_number?: number) => request<Document>(`/documents/${id}${page_number === undefined ? "" : `?page_number=${page_number}`}`);
export const getGatewayStatus = () => request<import("@/types").GatewayStatus>("/integrations/model-gateway/status");
export const getAutoROIs = (id: string, auto_roi_mode = "text-line", page_number: number | null = null) => request<import("@/types").AutoROIResponse>(`/documents/${id}/auto-rois`, { method: "POST", body: JSON.stringify({ auto_roi_mode, expand_text_rois: false, page_number }) });
export const getCategories = () => request<Category[]>("/categories");
export const getPipelines = () => request<PipelineConfig[]>("/pipelines");
export const getOCRModels = () => request<import("@/types").OCRModel[]>("/pipelines/models");
export const saveOCRModel = (value: Omit<import("@/types").OCRModel, "id">, id?: string) => request<import("@/types").OCRModel>(id ? `/pipelines/models/${id}` : "/pipelines/models", { method: id ? "PUT" : "POST", body: JSON.stringify(value) });
export const saveDynamicPipeline = (value: import("@/types").DynamicPipelineInput, id?: string) => request<PipelineConfig>(id ? `/pipelines/${id}/definition` : "/pipelines", { method: id ? "PUT" : "POST", body: JSON.stringify(value) });
export const updatePipeline = (id: string, value: Partial<PipelineConfig>) => request<PipelineConfig>(`/pipelines/${id}`, { method: "PUT", body: JSON.stringify(value) });
export const testConnection = (id: string) => request<{ status: string; message: string }>(`/pipelines/${id}/test-connection`, { method: "POST" });
export const uploadDocument = (file: File, documentTypeId?: string) => { const form = new FormData(); form.set("file", file); if(documentTypeId)form.set("document_type_id",documentTypeId); return request<Document>("/documents", { method: "POST", body: form }); };
export const createTestCase = (input: TestCaseInput) => request<TestCase>("/test-cases", { method: "POST", body: JSON.stringify(input) });
export const getTestCase = (id: string) => request<TestCase>(`/test-cases/${id}`);
export const deleteTestCase = (id: string) => request<void>(`/test-cases/${id}`, { method: "DELETE" });

export type AppLog = { id: string; created_at: string; level: string; event_type: string; message: string; page_number: number | null; pipeline_id: string | null; pipeline_name: string | null; document_name: string | null; document_id: string | null; test_case_id: string | null; test_case_exists: boolean; outcome: string; request_id: string | null; gateway_request_id: string | null; metadata: { error_code?: string; duration_ms?: number; count?: number } };
export const getLogs = (params: URLSearchParams) => request<{ enabled?:boolean; total: number; items: AppLog[] }>(`/logs?${params}`);
export type PageProgress = { event: string; page?: number; pages?: number[]; status?: string; test_case_id?: string; message?: string };
export async function runPages(id: string, pages: number[], pipelines: string[], category_codes: string[], onEvent: (event: PageProgress) => void) {
  const response = await fetch(`${API_BASE_URL}/api/documents/${id}/run-pages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pages, pipelines, category_codes }) });
  if (!response.ok || !response.body) throw new Error("เริ่มประมวลผลไม่ได้ กรุณาตรวจหมายเลขหน้าและการเชื่อมต่อ");
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = "", finished = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n"); buffer = lines.pop() ?? "";
      for (const line of lines) if (line.trim()) { const event = JSON.parse(line) as PageProgress; if (event.event === "batch_finished") finished = true; onEvent(event); }
      if (done) break;
    }
    if (!finished) throw new Error("การเชื่อมต่อขาด กรุณาตรวจประวัติและบันทึกการทำงานก่อนลองใหม่");
  } finally { reader.releaseLock(); }
}
export const updateTestCase = (id: string, input: Partial<TestCaseInput>) => request<TestCase>(`/test-cases/${id}`, { method: "PUT", body: JSON.stringify(input) });
export const saveGroundTruth = (id: string, ground_truth_raw: string, confirmed = false) => request<TestCase>(`/test-cases/${id}/ground-truth`, { method: "PUT", body: JSON.stringify({ ground_truth_raw, confirmed }) });
export const runPipelines = (id: string, pipelines: string[]) => request<RunResponse>(`/test-cases/${id}/run`, { method: "POST", body: JSON.stringify({ pipelines }) });
export const checkField = (caseId: string, runId: string, fieldId: string, ground_truth_raw: string) => request<import("@/types").FieldComparison>(`/test-cases/${caseId}/runs/${runId}/fields/${fieldId}/check`, { method: "POST", body: JSON.stringify({ ground_truth_raw }) });
export const saveFieldGT = (caseId: string, runId: string, fieldId: string, ground_truth_raw: string, confirmed: boolean) => request<import("@/types").OCRField>(`/test-cases/${caseId}/runs/${runId}/fields/${fieldId}/ground-truth`, { method: "PUT", body: JSON.stringify({ ground_truth_raw, confirmed }) });
export const getHistory = (filters?: QueryFilters, signal?: AbortSignal) => request<TestCase[]>(`/history${query(filters)}${query(filters) ? "&" : "?"}view=summary`, { signal });
export const getMatrix = (filters?: QueryFilters, signal?: AbortSignal) => request<MatrixRow[]>(`/matrix${query(filters)}`, { signal });
export const getAnalyticsSummary = (filters?: QueryFilters, signal?: AbortSignal) => request<import("@/types").AnalyticsSummary>(`/analytics/summary${query(filters)}`, { signal });
export const getAnalyticsPipelines = (signal?: AbortSignal) => request<import("@/types").AnalyticsPipeline[]>("/analytics/pipelines", { signal });
export const getAnalysisGroups = (dimension: "document-types" | "categories", filters?: QueryFilters) => request<import("@/types").AnalyticsGroup[]>(`/analytics/${dimension}${query(filters)}`);
export const getCategoryAnalytics = (filters?: QueryFilters) => request<CategoryAnalytics[]>(`/analytics/categories${query(filters)}`);
export type ErrorGroup = { pipeline_id: string; error_type: string; ground_truth_unit: string | null; ocr_unit: string | null; count: number; test_case_count: number; cases: { id: string; document_id: string; filename: string; page_number: number | null; categories: string[] }[] };
export const getErrorAnalysis = (params: URLSearchParams) => request<{ total: number; items: ErrorGroup[] }>(`/analytics/errors?${params}`);
export const recomputeErrors = (id: string) => request<{ recomputed_runs: number }>(`/test-cases/${id}/errors/recompute`, { method: "POST" });
export type DatasetSample = { document_type_id?: string | null; document_type_name?: string | null; id: string; test_case_id?: string; global_field_id?: string | null; field_index?: number | null; document_id: string; filename: string; page_number: number | null; roi: import("@/types").ROI; ground_truth_raw: string; updated_at: string; source_sha256: string | null; categories: string[]; source_available?: boolean };
export const getDatasetSamples = (params: URLSearchParams) => request<{ total: number; items: DatasetSample[] }>(`/dataset/samples?${params}`);
export async function exportDataset(test_case_ids: string[]) {
  const response = await fetch(`${API_BASE_URL}/api/dataset/export`, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ test_case_ids: test_case_ids.filter(id=>!id.startsWith("field:")).map(id=>id.replace(/^case:/,"")), global_field_ids: test_case_ids.filter(id=>id.startsWith("field:")).map(id=>id.slice(6)) }) });
  if (!response.ok) { const error = await response.json().catch(() => null); throw new Error(typeof error?.detail === "string" ? error.detail : "ส่งออก Dataset ไม่สำเร็จ กรุณาลองใหม่"); }
  return response.blob();
}
export const cropUrl = (id: string, roi: import("@/types").ROI, page_number: number | null = null) => assetUrl(`/api/documents/${id}/crop?${new URLSearchParams(Object.entries({ ...roi, ...(page_number ? { page_number } : {}) }).map(([k, v]) => [k, String(v)]))}`);
export async function loadSample(): Promise<File> {
  const response = await fetch("/sample-document.png");
  if (!response.ok) throw new Error(t("The sample document could not be loaded."));
  return new File([await response.blob()], "sample-document.png", { type: "image/png" });
}

export const saveGlobalLayout = (id: string, fields: import("@/types").GlobalField[], confirmed: boolean) => request<TestCase>(`/test-cases/${id}/global-fields`, {method: "PUT", body: JSON.stringify({fields: fields.map(({id,field_index,roi,source})=>({id,field_index,roi,source})),confirmed})});
export const saveGlobalGT = (caseId: string, field: import("@/types").GlobalField) => request<TestCase>(`/test-cases/${caseId}/global-fields/${field.id}/ground-truth`, {method:"PUT",body:JSON.stringify({ground_truth_raw:field.ground_truth_raw ?? ""})});
export const setEvaluationMode = (caseId: string, mode: import("@/types").EvaluationMode) => request<TestCase>(`/test-cases/${caseId}/evaluation-mode`, {method:"PUT",body:JSON.stringify({mode})});
export const evaluateGlobal = (caseId: string, mode: import("@/types").EvaluationMode | "auto", global_field_ids: string[] = [], require_complete_gt = false) => request<TestCase>(`/test-cases/${caseId}/evaluate`, {method:"POST",body:JSON.stringify({mode,global_field_ids,require_complete_gt})});

export const getDocumentTypes = () => request<import("@/types").DocumentType[]>("/document-types");
export const createDocumentType = (name: string) => request<import("@/types").DocumentType>("/document-types", {method:"POST", body:JSON.stringify({name})});
export const archiveDocumentType = (id: string) => request<import("@/types").DocumentType>(`/document-types/${id}`, {method:"DELETE"});
export const excludeDatasetSample = (id: string, kind: "field" | "case") => request<{excluded: boolean}>(`/dataset/items/${id}?kind=${kind}`, {method:"DELETE"});

export const updateDocumentType = (id: string, typeId: string, page?: number | null) => request<Document>(`/documents/${id}/type${page?`?page_number=${page}`:""}`, {method:"PUT",body:JSON.stringify({document_type_id:typeId||null})});

export const getComparison = (filters: import("@/types").QueryFilters, includeArchived=false, signal?: AbortSignal) => request<import("@/types/comparison").Comparison>(`/analytics/comparison?${new URLSearchParams({...Object.fromEntries(Object.entries(filters).filter(([,v])=>v!=null).map(([k,v])=>[k,String(v)])),include_archived:includeArchived?"1":"0"})}`, { signal });


export const bulkDeleteTestCases = (ids:string[]) => request<{requested:number;deleted:number;already_missing:number}>("/test-cases/bulk-delete",{method:"POST",body:JSON.stringify({test_case_ids:ids})});
export const bulkExcludeDataset = (ids:string[]) => request<{requested:number;excluded:number;already_excluded:number;not_found:number}>("/dataset/items/bulk-exclude",{method:"POST",body:JSON.stringify({test_case_ids:ids.filter(id=>!id.startsWith("field:")),global_field_ids:ids.filter(id=>id.startsWith("field:")).map(id=>id.slice(6))})});
