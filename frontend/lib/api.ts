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
export const updateTestCase = (id: string, input: Partial<TestCaseInput>) => request<TestCase>(`/test-cases/${id}`, { method: "PUT", body: JSON.stringify(input) });
export const saveGroundTruth = (id: string, ground_truth_raw: string, confirmed = false) => request<TestCase>(`/test-cases/${id}/ground-truth`, { method: "PUT", body: JSON.stringify({ ground_truth_raw, confirmed }) });
export const runPipelines = (id: string, pipelines: string[]) => request<RunResponse>(`/test-cases/${id}/run`, { method: "POST", body: JSON.stringify({ pipelines }) });
export const getResults = (id: string) => request<RunResponse>(`/test-cases/${id}/results`);
export const getHistory = (filters?: QueryFilters) => request<TestCase[]>(`/history${query(filters)}`);
export const getMatrix = (filters?: QueryFilters) => request<MatrixRow[]>(`/matrix${query(filters)}`);
export const getCategoryAnalytics = (filters?: QueryFilters) => request<CategoryAnalytics[]>(`/analytics/categories${query(filters)}`);
export const cropUrl = (id: string, roi: import("@/types").ROI, page_number: number | null = null) => assetUrl(`/api/documents/${id}/crop?${new URLSearchParams(Object.entries({ ...roi, ...(page_number ? { page_number } : {}) }).map(([k, v]) => [k, String(v)]))}`);
export async function loadSample(): Promise<File> {
  const response = await fetch("/sample-document.png");
  if (!response.ok) throw new Error(t("The sample document could not be loaded."));
  return new File([await response.blob()], "sample-document.png", { type: "image/png" });
}
