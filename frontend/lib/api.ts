import { t, userError } from "@/lib/i18n/th";
import type { Category, CategoryAnalytics, Document, MatrixRow, PipelineConfig, QueryFilters, RunResponse, TestCase, TestCaseInput } from "@/types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export function assetUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
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
  Object.entries(filters ?? {}).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  return params.size ? `?${params}` : "";
}

export const getHealth = () => request<Record<string, unknown>>("/health");
export const getUploadConfig = () => request<{ max_upload_mb: number; pdf_render_dpi: number }>("/upload-config");
export const getDocumentPage = (id: string, page_number: number) => request<Document>(`/documents/${id}?page_number=${page_number}`);
export const getGatewayStatus = () => request<import("@/types").GatewayStatus>("/integrations/model-gateway/status");
export const getAutoROIs = (id: string, auto_roi_mode = "text-line", page_number: number | null = null) => request<import("@/types").AutoROIResponse>(`/documents/${id}/auto-rois`, { method: "POST", body: JSON.stringify({ auto_roi_mode, expand_text_rois: false, page_number }) });
export const getCategories = () => request<Category[]>("/categories");
export const getPipelines = () => request<PipelineConfig[]>("/pipelines");
export const updatePipeline = (id: string, value: Partial<PipelineConfig>) => request<PipelineConfig>(`/pipelines/${id}`, { method: "PUT", body: JSON.stringify(value) });
export const testConnection = (id: string) => request<{ status: string; message: string }>(`/pipelines/${id}/test-connection`, { method: "POST" });
export const uploadDocument = (file: File) => { const form = new FormData(); form.set("file", file); return request<Document>("/documents", { method: "POST", body: form }); };
export const createTestCase = (input: TestCaseInput) => request<TestCase>("/test-cases", { method: "POST", body: JSON.stringify(input) });
export const getTestCase = (id: string) => request<TestCase>(`/test-cases/${id}`);
export const deleteTestCase = (id: string) => request<void>(`/test-cases/${id}`, { method: "DELETE" });

export type AppLog = { id: string; created_at: string; level: string; event_type: string; message: string; page_number: number | null; pipeline_id: string | null; request_id: string | null; gateway_request_id: string | null; metadata: { error_code?: string; duration_ms?: number } };
export const getLogs = (params: URLSearchParams) => request<{ total: number; items: AppLog[] }>(`/logs?${params}`);
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
export const getResults = (id: string) => request<RunResponse>(`/test-cases/${id}/results`);
export const checkField = (caseId: string, runId: string, fieldId: string, ground_truth_raw: string) => request<import("@/types").FieldComparison>(`/test-cases/${caseId}/runs/${runId}/fields/${fieldId}/check`, { method: "POST", body: JSON.stringify({ ground_truth_raw }) });
export const saveFieldGT = (caseId: string, runId: string, fieldId: string, ground_truth_raw: string, confirmed: boolean) => request<import("@/types").OCRField>(`/test-cases/${caseId}/runs/${runId}/fields/${fieldId}/ground-truth`, { method: "PUT", body: JSON.stringify({ ground_truth_raw, confirmed }) });
export const getHistory = (filters?: QueryFilters) => request<TestCase[]>(`/history${query(filters)}`);
export const getMatrix = (filters?: QueryFilters) => request<MatrixRow[]>(`/matrix${query(filters)}`);
export const getCategoryAnalytics = (filters?: QueryFilters) => request<CategoryAnalytics[]>(`/analytics/categories${query(filters)}`);
export type ErrorGroup = { pipeline_id: string; error_type: string; ground_truth_unit: string | null; ocr_unit: string | null; count: number; test_case_count: number; cases: { id: string; document_id: string; filename: string; page_number: number | null; categories: string[] }[] };
export const getErrorAnalysis = (params: URLSearchParams) => request<{ total: number; items: ErrorGroup[] }>(`/analytics/errors?${params}`);
export const recomputeErrors = (id: string) => request<{ recomputed_runs: number }>(`/test-cases/${id}/errors/recompute`, { method: "POST" });
export type DatasetSample = { id: string; document_id: string; filename: string; page_number: number | null; roi: import("@/types").ROI; ground_truth_raw: string; updated_at: string; source_sha256: string | null; categories: string[]; source_available?: boolean };
export const getDatasetSamples = (params: URLSearchParams) => request<{ total: number; items: DatasetSample[] }>(`/dataset/samples?${params}`);
export async function exportDataset(test_case_ids: string[]) {
  const response = await fetch(`${API_BASE_URL}/api/dataset/export`, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ test_case_ids }) });
  if (!response.ok) { const error = await response.json().catch(() => null); throw new Error(typeof error?.detail === "string" ? error.detail : "ส่งออก Dataset ไม่สำเร็จ กรุณาลองใหม่"); }
  return response.blob();
}
export const cropUrl = (id: string, roi: import("@/types").ROI, page_number: number | null = null) => assetUrl(`/api/documents/${id}/crop?${new URLSearchParams(Object.entries({ ...roi, ...(page_number ? { page_number } : {}) }).map(([k, v]) => [k, String(v)]))}`);
export async function loadSample(): Promise<File> {
  const response = await fetch("/sample-document.png");
  if (!response.ok) throw new Error(t("The sample document could not be loaded."));
  return new File([await response.blob()], "sample-document.png", { type: "image/png" });
}
