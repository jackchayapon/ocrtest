import {API_BASE_URL, APIError, invalidatePipelineCatalog} from "./api";
import type {ExternalOCRProvider, PipelineConfig} from "@/types";

export type ManagedProviderInput = {
  name: string; endpoint: string; readiness_url: string | null;
  request_format: "multipart" | "json_base64"; image_field: string;
  response_adapter: "openthai_v1" | "text_json"; text_path: string; confidence_path: string | null;
  auth_mode: "none" | "bearer" | "x_api_key" | "custom_header";
  auth_header: string; enabled: boolean;
  credential_action: "keep" | "replace" | "remove"; api_key?: string;
};

export async function providerRequest<T>(path: string, data?: unknown, method?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api${path}`, {
    method: method || (data === undefined ? "GET" : "POST"),
    headers: {"Content-Type": "application/json"},
    ...(data === undefined ? {} : {body: JSON.stringify(data)}), cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new APIError(typeof payload?.detail === "string" ? payload.detail : "ไม่สามารถบันทึกการตั้งค่า Provider ได้", response.status);
  }
  if ((method || (data === undefined ? "GET" : "POST")) !== "GET") invalidatePipelineCatalog();
  return response.status === 204 ? undefined as T : response.json();
}

export const managedProviders = () => providerRequest<ExternalOCRProvider[]>("/external-providers");
export const saveManagedProvider = (data: ManagedProviderInput, id?: string) =>
  providerRequest<ExternalOCRProvider>(`/external-providers${id ? `/${encodeURIComponent(id)}` : ""}`, data, id ? "PUT" : "POST");
export const saveManagedPipeline = (data: {
  pipeline_id?: string; provider_id?: string; pipeline_name: string; pipeline_enabled: boolean; provider: ManagedProviderInput;
}) => providerRequest<PipelineConfig>("/external-pipelines", data);
