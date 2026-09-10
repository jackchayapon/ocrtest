export type PipelineId = "mint" | "hutch_crop" | "hutch_full";
export type ROI = { x1: number; y1: number; x2: number; y2: number };
export type ViewerBox = { id: string; bbox: [number, number, number, number]; polygon?: [number, number][] | null; text: string; confidence: number | null; color: string; pipelineId: string };
export type Document = { id: string; filename: string; mime_type: string; width: number; height: number; created_at: string; storage_key: string; image_url: string; sha256?: string; document_type: "image" | "pdf"; page_count: number; page_number: number | null; pdf_render_dpi?: number | null };
export type Category = { id: string; code: string; display_name: string };
export type Metrics = { cer: number | null; wer: number | null; exact_match: boolean };
export type OCRBox = { bbox: [number, number, number, number]; polygon?: [number, number][] | null; crop_bbox?: [number, number, number, number] | null; crop_polygon?: [number, number][] | null; text: string; confidence: number | null; det_confidence?: number | null; rec_confidence?: number | null };
export type PipelineRun = {
  id: string; pipeline_id: string; pipeline_name: string; status: "success" | "error";
  raw_text: string | null; final_text: string | null; text: string | null; normalized_text: string | null;
  confidence: number | null; processing_time_ms: number | null; boxes: OCRBox[];
  raw_response: Record<string, unknown> | null; error_message: string | null; created_at: string;
  metrics: Metrics | null; raw_metrics: Metrics | null;
  input_sha256?: string | null; input_width?: number | null; input_height?: number | null; request_id?: string | null; gateway_request_id?: string | null;
  gateway_duration_ms?: number | null; gateway_service?: string | null; gateway_model?: string | null;
  detector_model?: string | null; recognizer_model?: string | null; error_code?: string | null;
  original_width?: number | null; original_height?: number | null; roi?: ROI | null;
  crop_width?: number | null; crop_height?: number | null; crop_sha256?: string | null;
  input_byte_size?: number | null; input_format?: string | null; crop_stage?: string | null;
  model_info?: { detector?: string | null; recognizer?: string | null; service?: string | null; gateway_model?: string | null };
};
export type TestCase = {
  id: string; document_id: string; document: Document; roi: ROI | null;
  page_number: number | null;
  ground_truth_raw: string | null; ground_truth_normalized: string | null;
  status: "draft" | "tested" | "confirmed"; created_at: string; updated_at: string;
  categories: Category[]; runs: PipelineRun[];
};
export type PipelineConfig = {
  id: string; pipeline_id: string; name: string;
  base_url: string | null; endpoint: string | null; http_method: "POST" | "PUT";
  request_format: "multipart" | "json_base64" | "binary" | "custom";
  file_field_name: string | null; enabled: boolean; engine: string | null; include_roi: boolean;
  last_connection_status: string | null; created_at: string; updated_at: string;
  query_params?: Record<string, string>; api_key_configured?: boolean;
};
export type MatrixRow = {
  pipeline_id: string; pipeline_name: string; tests: number; successful_runs: number;
  failed_runs: number; evaluated_runs: number; cer: number | null; wer: number | null;
  exact_match_rate: number | null; avg_time_ms: number | null; avg_confidence: number | null;
  avg_gateway_time_ms?: number | null;
};
export type CategoryAnalytics = { code: string; display_name: string; test_cases: number; pipelines: MatrixRow[] };
export type QueryFilters = { category?: string; pipeline?: string; date_from?: string; date_to?: string; document?: string; limit?: number; offset?: number };
export type TestCaseInput = { document_id: string; roi: ROI | null; ground_truth_raw: string | null; category_codes: string[]; page_number?: number | null };
export type RunResponse = { test_case_id: string; runs: PipelineRun[] };
export type AutoROISuggestion = { id: string; roi: ROI; score: number | null; source: string };
export type AutoROIResponse = { regions: AutoROISuggestion[]; request_id?: string | null };
export type GatewayStatus = { gateway: string; mint: string; hutch_crop: string; hutch_full: string; auto_roi: string; api_key_configured: boolean; message?: string };
