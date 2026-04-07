export interface ProjectSummary {
  id: number;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface OverviewCard {
  label: string;
  value: string;
  tone: string;
}

export interface ProjectOverview {
  project_name: string;
  status: string;
  summary: string;
  chapter_progress: OverviewCard[];
  asset_health: OverviewCard[];
  provider_usage: OverviewCard[];
  initialization_progress: OverviewCard[];
}

export interface ChapterPipelineState {
  id: number;
  stage_key: string;
  status: string;
  detail: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChapterDetail {
  id: number;
  project_id: number;
  chapter_number: number;
  title: string;
  summary: string | null;
  status: string;
  pipeline_states: ChapterPipelineState[];
  created_at: string;
  updated_at: string;
}

export interface CharacterReferenceImage {
  id: number;
  view_type: string;
  asset_path: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CharacterProfile {
  id: number;
  project_id: number;
  name: string;
  appearance: string;
  personality: string;
  lora_path: string | null;
  review_status: string;
  reference_images: CharacterReferenceImage[];
  created_at: string;
  updated_at: string;
}

export interface VoiceProfile {
  id: number;
  project_id: number;
  character_name: string;
  voice_key: string;
  provider_key: string;
  tone_description: string;
  created_at: string;
  updated_at: string;
}

export interface SceneProfile {
  id: number;
  project_id: number;
  name: string;
  baseline_prompt: string;
  continuity_guardrails: string | null;
  review_status: string;
  created_at: string;
  updated_at: string;
}

export interface ArtifactArchive {
  id: number;
  archive_type: string;
  archive_path: string;
  index_key: string;
  status: string;
  remote_url: string | null;
  checksum_sha256: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArtifactRecord {
  id: number;
  project_id: number;
  chapter_id: number | null;
  job_run_id: number;
  step_key: string;
  title: string;
  media_kind: string;
  provider_key: string | null;
  status: string;
  mime_type: string;
  artifact_path: string;
  preview_path: string;
  preview_url: string;
  size_bytes: number | null;
  artifact_metadata: Record<string, unknown>;
  archives: ArtifactArchive[];
  sync_runs: ArtifactSyncRun[];
  created_at: string;
  updated_at: string;
}

export interface StorageTarget {
  archive_type: string;
  mode: string;
  location: string;
  remote_base_url: string | null;
  is_ready: boolean;
  readiness_reason: string;
}

export interface ArtifactSyncRun {
  id: number;
  artifact_id: number;
  archive_type: string;
  status: string;
  summary: string | null;
  error_message: string | null;
  worker_id: string | null;
  attempt_count: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowNode {
  key: string;
  title: string;
  provider_type: string;
  checkpointable: boolean;
}

export interface WorkflowEdge {
  source: string;
  target: string;
}

export interface WorkflowDefinition {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  routing_mode: string;
  spec: {
    nodes: WorkflowNode[];
    edges: WorkflowEdge[];
  };
  created_at: string;
  updated_at: string;
}

export interface ProviderAttempt {
  provider_key: string;
  status: string;
  error_message?: string | null;
}

export interface JobStepOutputSnapshot {
  provider_candidates?: string[];
  resolved_provider_key?: string | null;
  provider_attempts?: ProviderAttempt[];
  mime_type?: string;
  media_kind?: string;
  checksum_sha256?: string;
  playback_hint?: string;
  [key: string]: unknown;
}

export interface JobRunStep {
  id: number;
  sequence_no: number;
  step_key: string;
  step_name: string;
  provider_type: string;
  provider_key: string | null;
  status: string;
  usage_amount: number | null;
  usage_unit: string | null;
  output_snapshot: JobStepOutputSnapshot | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobCheckpoint {
  id: number;
  step_key: string;
  payload: Record<string, unknown>;
  resume_cursor: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobRun {
  id: number;
  project_id: number;
  chapter_id: number | null;
  workflow_id: number | null;
  execution_mode: string;
  routing_mode: string;
  status: string;
  current_step_key: string | null;
  summary: string | null;
  error_message: string | null;
  request_payload: Record<string, unknown>;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  locked_at?: string | null;
  last_heartbeat_at?: string | null;
  worker_id?: string | null;
  attempt_count?: number;
  steps: JobRunStep[];
  checkpoints: JobCheckpoint[];
  created_at: string;
  updated_at: string;
}

export interface ProviderUsageItem {
  provider_key: string;
  provider_type: string;
  routing_mode: string;
  budget_threshold: number;
  consumed: number;
  usage_unit: string;
  alert_status: string;
}

export interface MonitoringAlert {
  id: number;
  alert_key: string;
  scope_type: string;
  scope_key: string;
  severity: string;
  status: string;
  title: string;
  message: string;
  detail: Record<string, unknown>;
  first_triggered_at: string;
  last_triggered_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkerHeartbeat {
  worker_id: string;
  worker_type: string;
  status: string;
  health_status: string;
  last_seen_at: string;
  seconds_since_seen: number;
  last_job_id: number | null;
  detail: Record<string, unknown>;
}

export interface MonitoringSummary {
  active_alerts: number;
  healthy_workers: number;
  stale_workers: number;
  queued_jobs: number;
  running_jobs: number;
  failed_jobs: number;
  resumable_jobs: number;
  completed_jobs: number;
}

export interface MonitoringOverview {
  items: ProviderUsageItem[];
  alerts: MonitoringAlert[];
  workers: WorkerHeartbeat[];
  summary: MonitoringSummary;
}

export interface PreviewItem {
  id: string;
  artifact_id: number;
  job_id: number;
  chapter_id: number | null;
  stage_key: string;
  title: string;
  media_kind: string;
  status: string;
  provider_key: string | null;
  mime_type?: string | null;
  archive_status?: string | null;
  archive_targets?: string[];
  playback_url: string | null;
  playback_hint: string;
  updated_at: string;
}

export interface PreviewList {
  items: PreviewItem[];
}

export interface PromptTemplateSummary {
  id: number;
  project_id: number | null;
  workflow_key: string;
  template_version: string;
  template_body: string;
  feedback_count: number;
  latest_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface PromptFeedback {
  id: number;
  prompt_template_id: number;
  job_run_id: number | null;
  score: number;
  correction_summary: string;
  corrected_prompt: string | null;
  created_at: string;
  updated_at: string;
}

export interface SharedMemory {
  id: number;
  project_id: number | null;
  scope_type: string;
  scope_key: string;
  memory_type: string;
  content: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AuthSession {
  auth_enabled: boolean;
  email: string | null;
  display_name: string | null;
  role: string | null;
}

export interface BootstrapAccount {
  email: string;
  display_name: string;
  role: string;
  status: string;
}

export interface SettingsAuthOverview {
  enabled: boolean;
  bootstrap_accounts: BootstrapAccount[];
}

export interface SettingsRuntimeOverview {
  environment: string;
  default_routing_mode: string;
  archive_targets: string[];
  object_storage_mode: string;
  quark_pan_mode: string;
  aliyundrive_mode: string;
}

export interface ProviderConfigRecord {
  id: number;
  provider_key: string;
  provider_type: string;
  routing_mode: string;
  is_enabled: boolean;
  priority: number;
  budget_threshold: number;
  config: Record<string, unknown>;
}

export interface SettingsOverview {
  auth: SettingsAuthOverview;
  runtime: SettingsRuntimeOverview;
  storage_targets: StorageTarget[];
  providers: ProviderConfigRecord[];
}

export interface AuditLogRecord {
  id: number;
  actor_user_id: number | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  request_method: string;
  request_path: string;
  response_status: number;
  outcome: string;
  detail: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReviewTask {
  id: number;
  project_id: number | null;
  chapter_id: number | null;
  review_stage: string;
  review_type: string;
  status: string;
  assigned_agents: string[];
  checklist: string[];
  findings_summary: string | null;
  result_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProjectSourceMaterial {
  id: number;
  project_id: number;
  source_title: string;
  source_type: string;
  import_status: string;
  chapter_count: number;
  content_preview: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectStorySummary {
  id: number;
  project_id: number;
  status: string;
  summary_body: string;
  highlights: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectScriptDraft {
  id: number;
  project_id: number;
  status: string;
  title: string;
  script_body: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectGenerationAttempt {
  provider_key: string;
  status: string;
  error_message: string | null;
}

export interface ProjectGenerationTrace {
  generation_mode: string;
  routing_mode: string;
  manual_provider: string | null;
  resolved_provider_key: string | null;
  provider_candidates: string[];
  provider_attempts: ProjectGenerationAttempt[];
  usage_amount: number;
  usage_unit: string;
}

export interface ProjectInitialization {
  project_id: number;
  status: string;
  stage_cards: OverviewCard[];
  generation_trace: ProjectGenerationTrace | null;
  source: ProjectSourceMaterial | null;
  summary: ProjectStorySummary | null;
  script: ProjectScriptDraft | null;
  chapters: ChapterDetail[];
  character_drafts: CharacterProfile[];
  scene_drafts: SceneProfile[];
}

export interface WorkspaceData {
  authSession: AuthSession;
  settingsOverview: SettingsOverview;
  auditLogs: AuditLogRecord[];
  overview: ProjectOverview;
  chapters: ChapterDetail[];
  characters: CharacterProfile[];
  scenes: SceneProfile[];
  voices: VoiceProfile[];
  artifacts: ArtifactRecord[];
  storageTargets: StorageTarget[];
  workflows: WorkflowDefinition[];
  jobs: JobRun[];
  monitoring: MonitoringOverview;
  previews: PreviewList;
  projectInitialization: ProjectInitialization;
  promptTemplates: PromptTemplateSummary[];
  promptFeedback: PromptFeedback[];
  sharedMemories: SharedMemory[];
  reviewTasks: ReviewTask[];
}
