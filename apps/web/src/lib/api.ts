import type {
  AuditLogRecord,
  ArtifactRecord,
  AuthSession,
  ChapterDetail,
  CharacterProfile,
  JobRun,
  MonitoringOverview,
  PreviewList,
  ProviderConfigRecord,
  ProjectInitialization,
  ProjectOverview,
  ProjectSummary,
  PromptFeedback,
  PromptTemplateSummary,
  ReviewTask,
  SceneProfile,
  SettingsOverview,
  SharedMemory,
  StorageTarget,
  VoiceProfile,
  WorkflowDefinition,
} from "../types/api";

const API_ROOT = (import.meta.env.VITE_API_ROOT ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const API_V1 = `${API_ROOT}/api/v1`;
const API_TOKEN = (import.meta.env.VITE_API_TOKEN ?? "").trim();

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`;
}

async function request<T>(path: string): Promise<T> {
  const headers: HeadersInit = {};
  if (API_TOKEN) {
    headers.Authorization = `Bearer ${API_TOKEN}`;
  }
  const response = await fetch(`${API_V1}${path}`, { headers });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Ignore JSON parsing failures for non-JSON errors.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects(): Promise<ProjectSummary[]> {
    return request<ProjectSummary[]>("/projects");
  },
  getAuthMe(): Promise<AuthSession> {
    return request<AuthSession>("/auth/me");
  },
  getSettingsOverview(): Promise<SettingsOverview> {
    return request<SettingsOverview>("/settings/overview");
  },
  listAuditLogs(): Promise<{ items: AuditLogRecord[] }> {
    return request<{ items: AuditLogRecord[] }>("/audit-logs");
  },
  getProjectOverview(projectId: number): Promise<ProjectOverview> {
    return request<ProjectOverview>(`/projects/${projectId}/overview`);
  },
  listProjectChapters(projectId: number): Promise<ChapterDetail[]> {
    return request<ChapterDetail[]>(`/projects/${projectId}/chapters`);
  },
  listProjectJobs(projectId: number): Promise<JobRun[]> {
    return request<JobRun[]>(`/projects/${projectId}/jobs`);
  },
  listProjectPreviews(projectId: number): Promise<PreviewList> {
    return request<PreviewList>(`/projects/${projectId}/previews`);
  },
  listCharacters(projectId: number): Promise<CharacterProfile[]> {
    return request<CharacterProfile[]>(`/assets/characters?project_id=${projectId}`);
  },
  listScenes(projectId: number): Promise<SceneProfile[]> {
    return request<SceneProfile[]>(`/assets/scenes?project_id=${projectId}`);
  },
  listVoices(projectId: number): Promise<VoiceProfile[]> {
    return request<VoiceProfile[]>(`/assets/voices?project_id=${projectId}`);
  },
  getProjectInitialization(projectId: number): Promise<ProjectInitialization> {
    return request<ProjectInitialization>(`/projects/${projectId}/initialization`);
  },
  listArtifacts(projectId: number): Promise<ArtifactRecord[]> {
    return request<ArtifactRecord[]>(`/assets/artifacts?project_id=${projectId}`);
  },
  listStorageTargets(): Promise<{ items: StorageTarget[] }> {
    return request<{ items: StorageTarget[] }>("/storage/targets");
  },
  listWorkflows(projectId: number): Promise<WorkflowDefinition[]> {
    return request<WorkflowDefinition[]>(`/workflows?project_id=${projectId}`);
  },
  updateWorkflow(
    workflowId: number,
    payload: {
      name: string;
      description: string | null;
      routing_mode: string;
      nodes: WorkflowDefinition["spec"]["nodes"];
      edges: WorkflowDefinition["spec"]["edges"];
    },
  ): Promise<WorkflowDefinition> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    if (API_TOKEN) {
      headers.Authorization = `Bearer ${API_TOKEN}`;
    }
    return fetch(`${API_V1}/workflows/${workflowId}`, {
      method: "PUT",
      headers,
      body: JSON.stringify(payload),
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error(`更新工作流失败: ${response.status}`);
      }
      return (await response.json()) as WorkflowDefinition;
    });
  },
  getMonitoring(): Promise<MonitoringOverview> {
    return request<MonitoringOverview>("/monitoring/overview");
  },
  listPromptTemplates(projectId: number): Promise<PromptTemplateSummary[]> {
    return request<PromptTemplateSummary[]>(`/prompt-evolution/templates?project_id=${projectId}`);
  },
  listPromptFeedback(projectId: number): Promise<PromptFeedback[]> {
    return request<PromptFeedback[]>(`/prompt-evolution/feedback?project_id=${projectId}`);
  },
  listMemories(projectId: number): Promise<SharedMemory[]> {
    return request<SharedMemory[]>(`/memories?project_id=${projectId}`);
  },
  listReviews(projectId: number): Promise<ReviewTask[]> {
    return request<ReviewTask[]>(`/reviews?project_id=${projectId}`);
  },
  updateProviderConfig(
    providerKey: string,
    payload: Partial<Pick<ProviderConfigRecord, "routing_mode" | "is_enabled" | "priority" | "budget_threshold">>,
  ): Promise<ProviderConfigRecord> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    if (API_TOKEN) {
      headers.Authorization = `Bearer ${API_TOKEN}`;
    }
    return fetch(`${API_V1}/settings/providers/${providerKey}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
    }).then(async (response) => {
      if (!response.ok) {
        let detail = `更新 Provider 失败: ${response.status}`;
        try {
          const data = (await response.json()) as { detail?: string };
          if (data.detail) {
            detail = data.detail;
          }
        } catch {
          // Ignore.
        }
        throw new Error(detail);
      }
      return (await response.json()) as ProviderConfigRecord;
    });
  },
};
