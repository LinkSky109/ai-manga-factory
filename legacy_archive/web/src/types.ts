export type JobStatus = "pending" | "planned" | "running" | "completed" | "failed";

export interface ProjectResponse {
  id: number;
  name: string;
  description?: string | null;
  created_at: string;
}

export interface ArtifactPreview {
  artifact_type: string;
  label: string;
  path_hint?: string | null;
}

export interface WorkflowStep {
  key: string;
  title: string;
  description: string;
  status: JobStatus;
  details?: string | null;
}

export interface JobResponse {
  id: number;
  project_id: number;
  project_name?: string | null;
  capability_id: string;
  status: JobStatus;
  input: Record<string, unknown>;
  workflow: WorkflowStep[];
  artifacts: ArtifactPreview[];
  summary: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobListResponse {
  items: JobResponse[];
}

export interface JobSummaryBucketResponse {
  key: string;
  label: string;
  count: number;
}

export interface JobSummaryResponse {
  totals: Record<string, number>;
  by_status: JobSummaryBucketResponse[];
  by_capability: JobSummaryBucketResponse[];
}

export interface BatchRetryResponse {
  requested: number;
  created: number;
  items: JobResponse[];
}

export interface BatchSyncStorageResponse {
  job_ids: number[];
  items: JobSyncTriggerItemResponse[];
}

export interface ArtifactInventoryItemResponse {
  key: string;
  url: string;
  label: string;
  file_name: string;
  kind: string;
  source: "job" | "pack";
  source_label: string;
  path_hint?: string | null;
  byte_size?: number | null;
  updated_at?: string | null;
  status?: string | null;
}

export interface ArtifactInventoryResponse {
  items: ArtifactInventoryItemResponse[];
}

export interface ArtifactSyncProviderResponse {
  provider: string;
  display_name: string;
  status: "uploaded" | "synced" | "missing";
  updated_at?: string | null;
  dry_run: boolean;
  remote_path?: string | null;
  remote_dir?: string | null;
  provider_home_url?: string | null;
  file_web_url?: string | null;
  note?: string | null;
  root_folder?: string | null;
}

export interface ArtifactSyncStatusResponse {
  artifact_url: string;
  local_path?: string | null;
  providers: ArtifactSyncProviderResponse[];
}

export interface CloudSyncOverviewProviderResponse {
  provider: string;
  display_name: string;
  updated_at?: string | null;
  dry_run: boolean;
  root_folder?: string | null;
  business_folder?: string | null;
  pack_reports_folder?: string | null;
  uploaded_count: number;
  synced_count: number;
  pending_count: number;
  provider_home_url?: string | null;
  note?: string | null;
}

export interface CloudSyncOverviewResponse {
  runtime_provider: string;
  remote_sync_enabled: boolean;
  remote_sync_provider: string;
  providers: CloudSyncOverviewProviderResponse[];
}

export interface CloudSyncTaskResponse {
  id: string;
  scope: "job" | "batch";
  provider: "quark_pan" | "aliyundrive" | "all";
  job_ids: number[];
  status: "queued" | "running" | "completed" | "failed";
  dry_run: boolean;
  created_at: string;
  updated_at: string;
  note?: string | null;
  items: JobSyncTriggerItemResponse[];
  error?: string | null;
}

export interface CloudSyncTaskListResponse {
  items: CloudSyncTaskResponse[];
}

export interface JobSyncProviderResponse {
  provider: string;
  display_name: string;
  status: "uploaded" | "synced" | "missing";
  updated_at?: string | null;
  matched_files: number;
  remote_dirs: string[];
  provider_home_url?: string | null;
  note?: string | null;
}

export interface JobSyncStatusResponse {
  job_id: number;
  local_roots: string[];
  providers: JobSyncProviderResponse[];
}

export interface JobSyncTriggerItemResponse {
  provider: string;
  dry_run: boolean;
  planned: number;
  pending: number;
  uploaded: number;
  skipped: number;
  updated_at?: string | null;
  note?: string | null;
}

export interface JobSyncTriggerResponse {
  job_id: number;
  items: JobSyncTriggerItemResponse[];
}

export interface CapabilityField {
  key: string;
  label: string;
  required: boolean;
  field_type: "string" | "integer" | "boolean" | "array";
  description: string;
}

export interface CapabilityDescriptor {
  id: string;
  name: string;
  description: string;
  category: string;
  outputs: string[];
  input_fields: CapabilityField[];
}

export interface AdaptationPackResponse {
  pack_name: string;
  source_title: string;
  chapter_range: string;
  chapter_count: number;
  default_project_name: string;
  default_scene_count: number;
}

export interface LatestPackResult {
  pack_name: string;
  job_id: number;
  project_name?: string | null;
  capability_id?: string | null;
  status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  validation_status?: string | null;
  validation_passed?: number | null;
  validation_total?: number | null;
  source: "pointer" | "scan-fallback";
  artifact_summary_url: string;
  artifact_validation_url: string;
  artifact_snapshot_url: string;
  pack_summary_url?: string | null;
  pack_validation_url?: string | null;
  shared_summary_url?: string | null;
  shared_validation_url?: string | null;
}

export interface ProviderUsageResponse {
  provider: string;
  display_name: string;
  updated_at: string;
  period_key: string;
  measurement_note: string;
  capabilities: Array<{
    capability: "text" | "image" | "video";
    active_model?: string | null;
    warning_ratio: number;
    switch_ratio: number;
    models: Array<{
      name: string;
      label: string;
      status: string;
      usage_ratio: number;
      usage_value: number;
      budget_limit?: number | null;
      usage_unit: string;
    }>;
  }>;
}

export interface StageModelPlanResponse {
  updated_at: string;
  strategy: {
    name: string;
    description: string;
  };
  pipeline: Array<{
    stage: string;
    uses_model: boolean;
    current_default?: string | null;
    fallbacks: string[];
    cost_effectiveness: string;
    coding_plan_pro_fit: string;
    notes: string;
  }>;
}

export interface UiPreferencesResponse {
  density_mode: "comfortable" | "balanced" | "compact";
  updated_at?: string | null;
}
