
import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { AdaptationPackResponse, ArtifactInventoryResponse, ArtifactPreview, ArtifactSyncStatusResponse, BatchRetryResponse, BatchSyncStorageResponse, CapabilityDescriptor, CapabilityField, CloudSyncOverviewResponse, CloudSyncTaskListResponse, CloudSyncTaskResponse, JobListResponse, JobResponse, JobSummaryResponse, JobSyncStatusResponse, JobSyncTriggerResponse, LatestPackResult, ProjectResponse, ProviderUsageResponse, StageModelPlanResponse } from "./types";

type JobStatusFilter = "all" | "running" | "completed" | "failed";
type ControlMode = "job" | "pack";
type PageKey = "overview" | "actions" | "jobs" | "artifact" | "models";
type ArtifactKind = "markdown" | "json" | "text" | "image" | "video" | "audio" | "html" | "pdf" | "file";
type ArtifactSource = "job" | "pack";
type JobGroupMode = "none" | "status" | "capability";

interface DashboardState {
  capabilities: CapabilityDescriptor[];
  projects: ProjectResponse[];
  jobs: JobListResponse["items"];
  packs: AdaptationPackResponse[];
  latestResults: Record<string, LatestPackResult>;
  artifactInventory: ArtifactRecord[];
  jobSummary: JobSummaryResponse | null;
  cloudOverview: CloudSyncOverviewResponse | null;
  cloudTasks: CloudSyncTaskResponse[];
  usage: ProviderUsageResponse | null;
  stagePlan: StageModelPlanResponse | null;
}

interface ArtifactSelection {
  url: string;
  label: string;
}

interface ArtifactRecord {
  key: string;
  url: string;
  label: string;
  fileName: string;
  kind: ArtifactKind;
  source: ArtifactSource;
  sourceLabel: string;
  pathHint?: string | null;
  byteSize?: number | null;
  updatedAt?: string | null;
  status?: string | null;
}

const defaultApiBase = window.location.port === "5173" || window.location.port === "4173" ? "http://127.0.0.1:8000" : "";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? defaultApiBase;
const PAGE_QUERY_KEY = "page";
const ARTIFACT_QUERY_KEY = "artifact";
const ARTIFACT_LABEL_QUERY_KEY = "artifactLabel";
const JOB_FILTER_QUERY_KEY = "capability";
const JOB_STATUS_QUERY_KEY = "jobStatus";
const JOB_SEARCH_QUERY_KEY = "jobSearch";
const PACK_SEARCH_QUERY_KEY = "packSearch";
const JOB_STATUS_FILTERS: JobStatusFilter[] = ["all", "running", "completed", "failed"];
const PAGE_ITEMS: PageKey[] = ["overview", "actions", "jobs", "artifact", "models"];
const PAGE_META: Record<PageKey, { label: string; eyebrow: string }> = {
  overview: { label: "总览", eyebrow: "工作区" },
  actions: { label: "操作", eyebrow: "发起" },
  jobs: { label: "任务", eyebrow: "任务台" },
  artifact: { label: "产物", eyebrow: "产物台" },
  models: { label: "模型", eyebrow: "策略" },
};

function resolveUrl(path: string) {
  if (!path) return "#";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

function readParam(key: string) {
  return new URLSearchParams(window.location.search).get(key);
}

function readPage(): PageKey {
  const value = readParam(PAGE_QUERY_KEY);
  return value && value in PAGE_META ? (value as PageKey) : "overview";
}

function readArtifact(): ArtifactSelection | null {
  const url = readParam(ARTIFACT_QUERY_KEY);
  if (!url) return null;
  return { url, label: readParam(ARTIFACT_LABEL_QUERY_KEY) ?? getArtifactName(url) };
}

function runViewTransition(update: () => void) {
  update();
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(resolveUrl(path));
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json() as Promise<T>;
}

async function fetchOptionalJson<T>(path: string, fallback: T): Promise<T> {
  try {
    return await fetchJson<T>(path);
  } catch (error) {
    console.warn(`Optional request failed: ${path}`, error);
    return fallback;
  }
}

async function postJson<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  const response = await fetch(resolveUrl(path), { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const payload = (await response.json().catch(() => ({}))) as T & { detail?: string };
  if (!response.ok) throw new Error(payload.detail || `Request failed: ${path}`);
  return payload;
}

function formatDate(value?: string | number | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN");
}

function statusTone(status?: string | null) {
  if (status === "completed" || status === "PASS") return "ok";
  if (status === "running") return "warn";
  if (status === "failed" || status === "FAIL") return "bad";
  return "neutral";
}

function statusLabel(status?: string | null) {
  return ({ pending: "待执行", planned: "已规划", running: "运行中", completed: "已完成", failed: "失败", PASS: "通过", FAIL: "未通过" } as Record<string, string>)[status ?? ""] ?? (status ?? "未知");
}

function syncStatusTone(status?: string | null) {
  if (status === "uploaded" || status === "synced") return "ok";
  return "neutral";
}

function syncStatusLabel(status?: string | null) {
  return ({ uploaded: "已上传", synced: "已同步", missing: "未同步" } as Record<string, string>)[status ?? ""] ?? "未知";
}

function queueStatusTone(status?: string | null) {
  if (status === "completed") return "ok";
  if (status === "queued" || status === "running") return "warn";
  if (status === "failed") return "bad";
  return "neutral";
}

function queueStatusLabel(status?: string | null) {
  return ({ queued: "排队中", running: "同步中", completed: "已完成", failed: "失败" } as Record<string, string>)[status ?? ""] ?? "未知";
}

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function formatSyncResultSummary(items: Array<{ provider: string; uploaded: number; skipped: number; note?: string | null }>) {
  return items.map((item) => {
    if (item.note && item.uploaded === 0 && item.skipped === 0) {
      return `${item.provider}: ${item.note}`;
    }
    return `${item.provider}: 上传 ${item.uploaded}，复用 ${item.skipped}`;
  }).join("；");
}

function fieldPlaceholder(field: CapabilityField) {
  return field.field_type === "array" ? '[{"chapter":1,"title":"Chapter 1"}]' : field.description;
}

function formatCapabilityValue(field: CapabilityField, value: string) {
  const trimmed = value.trim();
  if (!trimmed && field.required) throw new Error(`请填写 ${field.label}`);
  if (field.field_type === "boolean") return trimmed ? trimmed === "true" : undefined;
  if (field.field_type === "integer") return trimmed ? Number(trimmed) : undefined;
  if (field.field_type === "array") return trimmed ? JSON.parse(trimmed) : undefined;
  return trimmed || undefined;
}

function resolveJobArtifactUrl(jobId: number, pathHint?: string | null) {
  if (!pathHint) return null;
  const normalized = pathHint.replaceAll("\\", "/");
  return resolveUrl(`/artifacts/${normalized.startsWith("job_") ? normalized : `job_${jobId}/${normalized}`}`);
}

function getArtifactName(url: string) {
  const pathname = new URL(resolveUrl(url), window.location.origin).pathname;
  const parts = pathname.split("/").filter(Boolean);
  return decodeURIComponent(parts[parts.length - 1] ?? "artifact");
}

function getRawArtifactUrl(url: string) {
  const target = new URL(resolveUrl(url), window.location.origin);
  target.searchParams.set("raw", "1");
  return target.toString();
}

function getArtifactKind(url: string): ArtifactKind {
  const path = new URL(resolveUrl(url), window.location.origin).pathname.toLowerCase();
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".txt") || path.endsWith(".log") || path.endsWith(".csv")) return "text";
  if (path.endsWith(".png") || path.endsWith(".jpg") || path.endsWith(".jpeg") || path.endsWith(".webp") || path.endsWith(".svg")) return "image";
  if (path.endsWith(".mp4") || path.endsWith(".webm")) return "video";
  if (path.endsWith(".mp3") || path.endsWith(".wav")) return "audio";
  if (path.endsWith(".html") || path.endsWith(".htm")) return "html";
  if (path.endsWith(".pdf")) return "pdf";
  return "file";
}

function formatBytes(value?: number | null) {
  if (!value || value < 0) return "暂无";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function getPackStartChapter(pack: AdaptationPackResponse) {
  const match = pack.chapter_range.match(/(\d+)/);
  return match ? Number(match[1]) : 1;
}

function buildMinimalVideoSmokeProjectName(pack: AdaptationPackResponse) {
  return `real-media-smoke-${pack.pack_name}-${Date.now()}`;
}

function getJobContext(job: JobResponse) {
  const project = String(job.project_name ?? "");
  if (job.capability_id === "manga") return [project, String(job.input.source_title ?? ""), String(job.input.chapter_range ?? ""), String(job.input.adaptation_pack ?? "")].filter(Boolean).join(" / ") || "漫画任务";
  if (job.capability_id === "finance") return [project, String(job.input.target ?? ""), String(job.input.time_range ?? "")].filter(Boolean).join(" / ") || "财经任务";
  return [project, job.capability_id].filter(Boolean).join(" / ") || "通用任务";
}

function getJobSearchText(job: JobResponse) {
  return [job.project_name ?? "", job.capability_id, job.summary, getJobContext(job), String(job.input.source_title ?? ""), String(job.input.chapter_range ?? ""), String(job.input.adaptation_pack ?? ""), String(job.input.target ?? ""), String(job.input.time_range ?? "")].join(" ").toLowerCase();
}

function getPackSearchText(pack: AdaptationPackResponse, latest?: LatestPackResult | null) {
  return [
    pack.pack_name,
    pack.source_title,
    pack.chapter_range,
    String(pack.chapter_count),
    pack.default_project_name,
    String(pack.default_scene_count),
    latest?.status ?? "",
    latest?.validation_status ?? "",
    String(latest?.job_id ?? ""),
    latest?.project_name ?? "",
  ].join(" ").toLowerCase();
}

function findJobArtifact(job: JobResponse, keywords: string[]) {
  const normalizedKeywords = keywords.map((keyword) => keyword.toLowerCase());
  return job.artifacts.find((artifact) => {
    const haystack = [artifact.label, artifact.path_hint ?? "", artifact.artifact_type].join(" ").toLowerCase();
    return normalizedKeywords.some((keyword) => haystack.includes(keyword));
  }) ?? null;
}

type ResolvedArtifactLink = { label: string; url: string };

function resolveJobArtifactLink(job: JobResponse, artifact: ArtifactPreview | null): ResolvedArtifactLink | null {
  if (!artifact?.path_hint) return null;
  const url = resolveJobArtifactUrl(job.id, artifact.path_hint);
  return url ? { label: artifact.label, url } : null;
}

function getJobValidationArtifact(job: JobResponse) {
  return resolveJobArtifactLink(job, findJobArtifact(job, ["validation", "validation report", "校验", "验证", "qa"]));
}

function getJobErrorArtifact(job: JobResponse) {
  return resolveJobArtifactLink(job, findJobArtifact(job, ["error", "failed", "failure", "错误", "失败"]));
}

function getJobActiveStep(job: JobResponse) {
  return job.workflow.find((step) => step.status === "running") ?? job.workflow.find((step) => step.status === "failed") ?? [...job.workflow].reverse().find((step) => step.status === "completed") ?? null;
}

function getPrioritizedArtifacts(job: JobResponse) {
  return job.artifacts.filter((artifact) => artifact.path_hint).map((artifact) => ({ label: artifact.label, url: resolveJobArtifactUrl(job.id, artifact.path_hint) })).filter((item): item is { label: string; url: string } => Boolean(item.url)).slice(0, 8);
}

function MarkdownView({ content }: { content: string }) {
  return <div className="doc-content">{content.replaceAll("\r", "").split("\n").map((line, index) => !line.trim() ? <div key={index} className="doc-space" /> : line.startsWith("# ") ? <h1 key={index} className="doc-heading level-1">{line.slice(2)}</h1> : line.startsWith("## ") ? <h2 key={index} className="doc-heading level-2">{line.slice(3)}</h2> : line.startsWith("- ") ? <div key={index} className="doc-item">{line.slice(2)}</div> : <p key={index} className="doc-paragraph">{line}</p>)}</div>;
}

function ArtifactSyncPanel({ selection }: { selection: ArtifactSelection | null }) {
  const [syncStatus, setSyncStatus] = useState<ArtifactSyncStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!selection) {
      setSyncStatus(null);
      setLoadError(null);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setLoadError(null);
    fetchJson<ArtifactSyncStatusResponse>(`/artifact-sync-status?artifact=${encodeURIComponent(selection.url)}`)
      .then((payload) => {
        if (!active) return;
        setSyncStatus(payload);
        setLoading(false);
      })
      .catch((error) => {
        if (!active) return;
        setLoadError(error instanceof Error ? error.message : "同步状态加载失败");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selection]);

  useEffect(() => {
    if (!copyMessage) return;
    const timer = window.setTimeout(() => setCopyMessage(null), 2400);
    return () => window.clearTimeout(timer);
  }, [copyMessage]);

  const handleCopy = async (value: string, label: string) => {
    try {
      await copyText(value);
      setCopyMessage(`${label}已复制`);
    } catch (error) {
      setCopyMessage(error instanceof Error ? error.message : "复制失败");
    }
  };

  if (!selection) {
    return (
      <section className="panel-card artifact-sync-shell">
        <div className="section-head">
          <div>
            <p className="section-tag">网盘同步</p>
            <h2>同步状态</h2>
          </div>
        </div>
        <div className="artifact-empty">
          <strong>选择一个产物</strong>
          <p>这里会展示夸克网盘、阿里云盘的同步结果和远程路径。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel-card artifact-sync-shell">
      <div className="section-head">
        <div>
          <p className="section-tag">网盘同步</p>
          <h2>同步状态</h2>
        </div>
        {copyMessage ? <span className="status-pill ok">{copyMessage}</span> : null}
      </div>
      {syncStatus?.local_path ? (
        <div className="detail-overview sync-local-overview">
          <div className="detail-kv wide">
            <span>本地文件</span>
            <strong className="detail-path">{syncStatus.local_path}</strong>
          </div>
        </div>
      ) : null}
      {loading ? <div className="notice">正在读取网盘同步状态...</div> : null}
      {loadError ? <div className="notice error">{loadError}</div> : null}
      {!loading && !loadError ? (
        <div className="sync-provider-stack">
          {(syncStatus?.providers ?? []).map((provider) => (
            <article key={provider.provider} className="sync-provider-card">
              <div className="section-head">
                <div>
                  <strong>{provider.display_name}</strong>
                  <p className="sync-note">{provider.note ?? "暂无说明"}</p>
                </div>
                <span className={`status-pill ${syncStatusTone(provider.status)}`}>{syncStatusLabel(provider.status)}</span>
              </div>
              <div className="detail-overview sync-grid">
                <div className="detail-kv">
                  <span>最近同步</span>
                  <strong>{formatDate(provider.updated_at)}</strong>
                </div>
                <div className="detail-kv">
                  <span>根目录</span>
                  <strong>{provider.root_folder ?? "暂无"}</strong>
                </div>
                <div className="detail-kv wide">
                  <span>网盘目录</span>
                  <strong className="detail-path">{provider.remote_dir ?? "最近一次同步还未包含该产物"}</strong>
                </div>
                <div className="detail-kv wide">
                  <span>同步路径</span>
                  <strong className="detail-path">{provider.remote_path ?? "暂无"}</strong>
                </div>
              </div>
              <div className="sync-actions">
                {provider.provider_home_url ? (
                  <a className="secondary-button" href={provider.provider_home_url} target="_blank" rel="noreferrer">
                    打开网盘
                  </a>
                ) : null}
                {provider.file_web_url ? (
                  <a className="secondary-button" href={provider.file_web_url} target="_blank" rel="noreferrer">
                    打开云端文件
                  </a>
                ) : null}
                {provider.remote_dir ? (
                  <button type="button" className="mini-button" onClick={() => handleCopy(provider.remote_dir ?? "", `${provider.display_name}目录`)}>
                    复制目录
                  </button>
                ) : null}
                {provider.remote_path ? (
                  <button type="button" className="mini-button" onClick={() => handleCopy(provider.remote_path ?? "", `${provider.display_name}路径`)}>
                    复制路径
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function CloudSyncQueuePanel({ tasks, onRetry }: { tasks: CloudSyncTaskResponse[]; onRetry: (taskId: string) => void; }) {
  return (
    <section className="panel-card cloud-queue-shell">
      <div className="section-head">
        <div>
          <p className="section-tag">同步队列</p>
          <h2>后台交付队列</h2>
        </div>
        <span>{tasks.length} 项</span>
      </div>
      <div className="cloud-queue-list">
        {tasks.length > 0 ? tasks.map((task) => (
          <article key={task.id} className="cloud-task-card">
            <div className="cloud-provider-head">
              <div>
                <strong>{task.scope === "batch" ? "批量交付" : `任务 #${task.job_ids[0] ?? "-"}`}</strong>
                <p>{task.note ?? "暂无说明"}</p>
              </div>
              <span className={`status-pill ${queueStatusTone(task.status)}`}>{queueStatusLabel(task.status)}</span>
            </div>
            <div className="task-row-meta">
              <span>{task.provider}</span>
              <span>{task.job_ids.length} 个任务</span>
              <span>{formatDate(task.updated_at)}</span>
            </div>
            {task.error ? <p className="sync-note">{task.error}</p> : null}
            <div className="sync-actions">
              {task.status === "failed" ? <button type="button" className="primary-button" onClick={() => onRetry(task.id)}>重试</button> : null}
            </div>
          </article>
        )) : <div className="artifact-empty compact-empty"><strong>暂无后台交付任务</strong><p>发起一次同步后，这里会显示排队、执行和完成状态。</p></div>}
      </div>
    </section>
  );
}

function CloudSyncOverviewPanel({ overview }: { overview: CloudSyncOverviewResponse | null; }) {
  const providers = overview?.providers ?? [];

  return (
    <section className="panel-card cloud-overview-shell">
      <div className="section-head">
        <div>
          <p className="section-tag">云端交付</p>
          <h2>网盘同步概览</h2>
        </div>
        <span>{providers.length > 0 ? `${providers.length} 个 provider` : "暂无"}</span>
      </div>
      <div className="cloud-runtime-meta">
        <div className="detail-kv">
          <span>运行目录</span>
          <strong>{overview?.runtime_provider ?? "暂无"}</strong>
        </div>
        <div className="detail-kv">
          <span>自动同步</span>
          <strong>{overview?.remote_sync_enabled ? "已开启" : "手动同步"}</strong>
        </div>
      </div>
      <div className="cloud-provider-grid">
        {providers.length > 0 ? providers.map((provider) => (
          <article key={provider.provider} className="cloud-provider-card">
            <div className="cloud-provider-head">
              <div>
                <strong>{provider.display_name}</strong>
                <p>{provider.note ?? "暂无说明"}</p>
              </div>
              <span className={`status-pill ${provider.uploaded_count > 0 || provider.synced_count > 0 ? "ok" : "neutral"}`}>
                {provider.uploaded_count > 0 || provider.synced_count > 0 ? "在线" : "待同步"}
              </span>
            </div>
            <div className="cloud-provider-metrics">
              <div><span>上传</span><strong>{provider.uploaded_count}</strong></div>
              <div><span>复用</span><strong>{provider.synced_count}</strong></div>
              <div><span>待处理</span><strong>{provider.pending_count}</strong></div>
            </div>
            <div className="cloud-provider-copy">
              <span>目录基线</span>
              <strong className="detail-path">{provider.root_folder ? `${provider.root_folder}/${provider.business_folder ?? ""}` : "暂无"}</strong>
            </div>
            <div className="sync-actions">
              {provider.provider_home_url ? <a className="secondary-button" href={provider.provider_home_url} target="_blank" rel="noreferrer">打开网盘</a> : null}
            </div>
            <div className="cloud-provider-foot">
              <span>{formatDate(provider.updated_at)}</span>
            </div>
          </article>
        )) : <div className="artifact-empty compact-empty"><strong>暂无云端同步数据</strong><p>先执行一次同步，概览会自动显示最近结果。</p></div>}
      </div>
    </section>
  );
}

function ArtifactViewer({ selection }: { selection: ArtifactSelection | null }) {
  const [textContent, setTextContent] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const kind = selection ? getArtifactKind(selection.url) : "file";
  const rawUrl = selection ? getRawArtifactUrl(selection.url) : "";

  useEffect(() => {
    if (!selection || !["markdown", "json", "text"].includes(kind)) return;
    let active = true;
    setLoading(true);
    setLoadError(null);
    fetch(rawUrl)
      .then((response) => response.ok ? response.text() : Promise.reject(new Error("产物读取失败")))
      .then((text) => {
        if (!active) return;
        if (kind === "json") {
          try { setTextContent(JSON.stringify(JSON.parse(text), null, 2)); } catch { setTextContent(text); }
        } else {
          setTextContent(text);
        }
        setLoading(false);
      })
      .catch((error) => {
        if (!active) return;
        setLoadError(error instanceof Error ? error.message : "产物读取失败");
        setLoading(false);
      });
    return () => { active = false; };
  }, [selection, kind, rawUrl]);

  if (!selection) {
    return <section className="panel-card artifact-viewer-shell"><div className="section-head"><div><p className="section-tag">产物预览</p><h2>预览工作区</h2></div></div><div className="artifact-empty"><strong>还没有选中产物</strong><p>从列表选择一个文件开始预览。</p></div></section>;
  }

  return (
    <section className="panel-card artifact-viewer-shell">
      <div className="section-head artifact-header"><div><p className="section-tag">产物预览</p><h2>{selection.label}</h2></div><a className="secondary-button inline-link-button" href={rawUrl} target="_blank" rel="noreferrer">打开原文件</a></div>
      <div className="artifact-meta"><span>{kind}</span></div>
      {loading ? <div className="notice">正在加载产物内容...</div> : null}
      {loadError ? <div className="notice error">{loadError}</div> : null}
      {!loading && !loadError && kind === "markdown" ? <MarkdownView content={textContent} /> : null}
      {!loading && !loadError && (kind === "json" || kind === "text") ? <pre className="artifact-code">{textContent}</pre> : null}
      {!loading && !loadError && kind === "image" ? <img className="artifact-media image" src={rawUrl} alt={selection.label} /> : null}
      {!loading && !loadError && kind === "video" ? <video className="artifact-media" src={rawUrl} controls playsInline /> : null}
      {!loading && !loadError && kind === "audio" ? <audio className="artifact-media audio" src={rawUrl} controls /> : null}
      {!loading && !loadError && (kind === "html" || kind === "pdf") ? <iframe className="artifact-frame" title={selection.label} src={rawUrl} /> : null}
      {!loading && !loadError && kind === "file" ? <div className="artifact-empty"><strong>当前类型暂不内嵌预览</strong><p>请从原文件入口打开。</p></div> : null}
    </section>
  );
}

function TaskDetail({ job, onOpenArtifact, onRetry, retrying, onSynced }: { job: JobResponse | null; onOpenArtifact: (url: string, label?: string) => void; onRetry: (jobId: number) => void; retrying: boolean; onSynced: () => Promise<void>; }) {
  const [syncStatus, setSyncStatus] = useState<JobSyncStatusResponse | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncingProvider, setSyncingProvider] = useState<string | null>(null);
  const [syncActionMessage, setSyncActionMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!job) {
      setSyncStatus(null);
      setSyncLoading(false);
      setSyncError(null);
      return;
    }

    let active = true;
    setSyncLoading(true);
    setSyncError(null);
    fetchJson<JobSyncStatusResponse>(`/jobs/${job.id}/sync-status`)
      .then((payload) => {
        if (!active) return;
        setSyncStatus(payload);
        setSyncLoading(false);
      })
      .catch((error) => {
        if (!active) return;
        setSyncError(error instanceof Error ? error.message : "任务同步状态读取失败");
        setSyncLoading(false);
      });
    return () => {
      active = false;
    };
  }, [job]);

  const triggerSync = async (provider: "quark_pan" | "aliyundrive" | "all", dryRun = false) => {
    if (!job) return;
    try {
      setSyncingProvider(provider);
      setSyncActionMessage(dryRun ? "正在生成同步计划..." : "正在执行网盘同步...");
      const result = await postJson<JobSyncTriggerResponse>(`/jobs/${job.id}/sync-storage`, { provider, dry_run: dryRun });
      const labels = result.items.map((item) => `${item.provider}: 上传 ${item.uploaded}，复用 ${item.skipped}`).join("；");
      setSyncActionMessage(dryRun ? `同步计划已生成。${labels}` : `同步完成。${labels}`);
      const refreshed = await fetchJson<JobSyncStatusResponse>(`/jobs/${job.id}/sync-status`);
      setSyncStatus(refreshed);
      await onSynced();
    } catch (error) {
      setSyncActionMessage(error instanceof Error ? error.message : "网盘同步失败");
    } finally {
      setSyncingProvider(null);
    }
  };

  if (!job) {
    return <section className="panel-card task-detail-shell"><div className="section-head"><div><p className="section-tag">任务检查</p><h2>任务详情</h2></div></div><div className="artifact-empty"><strong>从左侧选择一个任务</strong><p>这里会显示步骤、输入、错误和关联产物。</p></div></section>;
  }

  const artifacts = getPrioritizedArtifacts(job);
  const activeStep = getJobActiveStep(job);
  const hasInput = Object.keys(job.input).length > 0;
  const inputKeys = Object.keys(job.input);
  const summaryText = job.summary || "暂无摘要";
  const validationArtifact = getJobValidationArtifact(job);
  const errorArtifact = getJobErrorArtifact(job);

  return (
    <section className="panel-card task-detail-shell">
      <div className="section-head"><div><p className="section-tag">任务检查</p><h2>{job.capability_id} #{job.id}</h2></div><span className={`status-pill ${statusTone(job.status)}`}>{statusLabel(job.status)}</span></div>
      <div className="detail-overview">
        <div className="detail-kv"><span>项目</span><strong>{job.project_name ?? "暂无"}</strong></div>
        <div className="detail-kv"><span>最近更新</span><strong>{formatDate(job.updated_at)}</strong></div>
        <div className="detail-kv wide"><span>上下文</span><strong>{getJobContext(job)}</strong></div>
      </div>
      {job.status === "failed" ? (
        <div className="failure-actions">
          {validationArtifact ? <button type="button" className="secondary-button" onClick={() => onOpenArtifact(validationArtifact.url, validationArtifact.label)}>查看校验</button> : null}
          {errorArtifact ? <button type="button" className="secondary-button" onClick={() => onOpenArtifact(errorArtifact.url, errorArtifact.label)}>错误产物</button> : null}
          <button className="primary-button" type="button" onClick={() => onRetry(job.id)} disabled={retrying}>{retrying ? "正在重跑..." : "重跑失败任务"}</button>
        </div>
      ) : null}
      <div className="detail-stack">
        <details className="detail-disclosure" open>
          <summary className="detail-disclosure-head">
            <div><strong>摘要</strong><span>{activeStep ? activeStep.title : "概览"}</span></div>
          </summary>
          <div className="detail-panel detail-panel-body"><p>{summaryText}</p></div>
        </details>
        <details className="detail-disclosure" open={job.status === "running" || job.status === "failed"}>
          <summary className="detail-disclosure-head">
            <div><strong>工作流步骤</strong><span>{job.workflow.length} 步</span></div>
          </summary>
          <div className="detail-panel detail-panel-body"><div className="step-stack">{job.workflow.map((step) => <div key={step.key} className={`step-item ${step.status}`}><div className="step-bullet" /><div><strong>{step.title}</strong><span>{statusLabel(step.status)}</span>{step.details ? <p>{step.details}</p> : <p>{step.description}</p>}</div></div>)}</div></div>
        </details>
        {hasInput ? <details className="detail-disclosure"><summary className="detail-disclosure-head"><div><strong>输入参数</strong><span>{inputKeys.length} 项</span></div></summary><div className="detail-panel detail-panel-body"><pre className="artifact-code detail-code">{JSON.stringify(job.input, null, 2)}</pre></div></details> : null}
        {job.error ? <details id={`job-error-${job.id}`} className="detail-disclosure error-disclosure" open><summary className="detail-disclosure-head"><div><strong>错误信息</strong><span>需要处理</span></div></summary><div className="detail-panel detail-panel-body error-panel"><p>{job.error}</p></div></details> : null}
        <details className="detail-disclosure" open>
          <summary className="detail-disclosure-head">
            <div><strong>云端交付</strong><span>{syncStatus?.providers?.filter((provider) => provider.status !== "missing")?.length ?? 0} 个 provider 已记录</span></div>
          </summary>
          <div className="detail-panel detail-panel-body">
            {syncLoading ? <p>正在读取云端同步状态...</p> : null}
            {syncError ? <p>{syncError}</p> : null}
            {syncActionMessage ? <p>{syncActionMessage}</p> : null}
            {!syncLoading && !syncError ? (
              <div className="sync-provider-stack compact-sync-stack">
                {(syncStatus?.providers ?? []).map((provider) => (
                  <article key={provider.provider} className="sync-provider-card compact">
                    <div className="section-head">
                      <div>
                        <strong>{provider.display_name}</strong>
                        <p className="sync-note">{provider.note ?? "暂无说明"}</p>
                      </div>
                      <span className={`status-pill ${syncStatusTone(provider.status)}`}>{syncStatusLabel(provider.status)}</span>
                    </div>
                    <div className="detail-overview sync-grid">
                      <div className="detail-kv">
                        <span>命中文件</span>
                        <strong>{provider.matched_files}</strong>
                      </div>
                      <div className="detail-kv">
                        <span>最近同步</span>
                        <strong>{formatDate(provider.updated_at)}</strong>
                      </div>
                      <div className="detail-kv wide">
                        <span>远程目录</span>
                        <strong className="detail-path">{provider.remote_dirs[0] ?? "暂无"}</strong>
                      </div>
                    </div>
                    <div className="sync-actions">
                      {provider.provider_home_url ? <a className="secondary-button" href={provider.provider_home_url} target="_blank" rel="noreferrer">打开网盘</a> : null}
                      <button type="button" className="mini-button" disabled={syncingProvider !== null} onClick={() => triggerSync(provider.provider as "quark_pan" | "aliyundrive")}>
                        {syncingProvider === provider.provider ? "同步中..." : `同步到 ${provider.display_name}`}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
            <div className="sync-actions">
              <button type="button" className="secondary-button" disabled={syncingProvider !== null} onClick={() => triggerSync("all", true)}>
                {syncingProvider === "all" ? "计划中..." : "生成同步计划"}
              </button>
              <button type="button" className="primary-button" disabled={syncingProvider !== null || job.status === "running"} onClick={() => triggerSync("all")}>
                {syncingProvider === "all" ? "同步中..." : "同步到全部网盘"}
              </button>
            </div>
          </div>
        </details>
        <details className="detail-disclosure" open={artifacts.length > 0 && artifacts.length <= 3}>
          <summary className="detail-disclosure-head">
            <div><strong>关联产物</strong><span>{artifacts.length} 项</span></div>
          </summary>
          <div className="detail-panel detail-panel-body"><div className="job-artifacts">{artifacts.length > 0 ? artifacts.map((artifact) => <button key={`${job.id}-${artifact.url}`} type="button" className="artifact-link" onClick={() => onOpenArtifact(artifact.url, artifact.label)}>{artifact.label}</button>) : <p>暂无可打开的产物。</p>}</div></div>
        </details>
      </div>
      {job.status !== "running" ? <button className="primary-button" onClick={() => onRetry(job.id)} disabled={retrying}>{retrying ? "正在重跑..." : "重跑该任务"}</button> : null}
    </section>
  );
}

export default function App() {
  const [state, setState] = useState<DashboardState>({ capabilities: [], projects: [], jobs: [], packs: [], latestResults: {}, artifactInventory: [], jobSummary: null, cloudOverview: null, cloudTasks: [], usage: null, stagePlan: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<PageKey>(() => readPage());
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactSelection | null>(() => readArtifact());
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [pendingErrorFocusJobId, setPendingErrorFocusJobId] = useState<number | null>(null);
  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([]);
  const [jobGroupMode, setJobGroupMode] = useState<JobGroupMode>("status");
  const [visibleJobCount, setVisibleJobCount] = useState(40);
  const [visibleArtifactCount, setVisibleArtifactCount] = useState(60);
  const [artifactSourceFilter, setArtifactSourceFilter] = useState<"all" | ArtifactSource>("all");
  const [artifactKindFilter, setArtifactKindFilter] = useState<"all" | ArtifactKind>("all");
  const [artifactSearch, setArtifactSearch] = useState("");
  const [controlMode, setControlMode] = useState<ControlMode>("job");
  const [selectedCapabilityId, setSelectedCapabilityId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [capabilityInputs, setCapabilityInputs] = useState<Record<string, string>>({});
  const [createJobMessage, setCreateJobMessage] = useState<string | null>(null);
  const [creatingJob, setCreatingJob] = useState(false);
  const [selectedPackName, setSelectedPackName] = useState("");
  const [packProjectName, setPackProjectName] = useState("");
  const [packSceneCount, setPackSceneCount] = useState("20");
  const [packTargetDuration, setPackTargetDuration] = useState("");
  const [packBatchSize, setPackBatchSize] = useState("5");
  const [packChapterStart, setPackChapterStart] = useState("");
  const [packChapterEnd, setPackChapterEnd] = useState("");
  const [packMessage, setPackMessage] = useState<string | null>(null);
  const [runningPack, setRunningPack] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<number | null>(null);
  const [batchRetrying, setBatchRetrying] = useState(false);
  const [batchSyncing, setBatchSyncing] = useState(false);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const [cloudActionMessage, setCloudActionMessage] = useState<string | null>(null);
  const [packSyncingPackName, setPackSyncingPackName] = useState<string | null>(null);
  const [jobCapabilityFilter, setJobCapabilityFilter] = useState<"all" | string>(() => readParam(JOB_FILTER_QUERY_KEY) ?? "all");
  const [jobStatusFilter, setJobStatusFilter] = useState<JobStatusFilter>(() => (readParam(JOB_STATUS_QUERY_KEY) as JobStatusFilter) || "all");
  const [jobSearch, setJobSearch] = useState<string>(() => readParam(JOB_SEARCH_QUERY_KEY) ?? "");
  const [packSearch, setPackSearch] = useState<string>(() => readParam(PACK_SEARCH_QUERY_KEY) ?? "");
  const deferredJobSearch = useDeferredValue(jobSearch.trim().toLowerCase());
  const deferredArtifactSearch = useDeferredValue(artifactSearch.trim().toLowerCase());
  const deferredPackSearch = useDeferredValue(packSearch.trim().toLowerCase());
  const loadSequenceRef = useRef(0);
  const focusJobErrorDetail = (jobId: number) => {
    runViewTransition(() => {
      setPage("jobs");
      setSelectedJobId(jobId);
      setPendingErrorFocusJobId(jobId);
    });
  };

  async function loadDashboard() {
    const loadSequence = ++loadSequenceRef.current;
    const [capabilities, projects, jobs, packs] = await Promise.all([
      fetchJson<{ items: CapabilityDescriptor[] }>("/capabilities"),
      fetchJson<ProjectResponse[]>("/projects"),
      fetchJson<JobListResponse>("/jobs"),
      fetchJson<AdaptationPackResponse[]>("/adaptation-packs"),
    ]);
    if (loadSequence !== loadSequenceRef.current) return;
    startTransition(() => {
      setState((current) => ({
        ...current,
        capabilities: capabilities.items,
        projects,
        jobs: jobs.items,
        packs,
      }));
      setLoading(false);
      setError(null);
    });
    const [usage, stagePlan, artifactInventory, jobSummary, cloudOverview, cloudTasks, latestEntries] = await Promise.all([
      fetchOptionalJson<ProviderUsageResponse | null>("/provider-usage", null),
      fetchOptionalJson<StageModelPlanResponse | null>("/model-stage-plan", null),
      fetchOptionalJson<ArtifactInventoryResponse>("/artifacts-index", { items: [] }),
      fetchOptionalJson<JobSummaryResponse | null>("/jobs/summary", null),
      fetchOptionalJson<CloudSyncOverviewResponse | null>("/cloud-sync-overview", null),
      fetchOptionalJson<CloudSyncTaskListResponse>("/cloud-sync-tasks", { items: [] }),
      Promise.all(packs.map(async (pack) => {
        try { return [pack.pack_name, await fetchJson<LatestPackResult>(`/adaptation-packs/${encodeURIComponent(pack.pack_name)}/latest-result`)] as const; } catch { return [pack.pack_name, null] as const; }
      })),
    ]);
    if (loadSequence !== loadSequenceRef.current) return;
    startTransition(() => {
      setState((current) => ({
        ...current,
        latestResults: Object.fromEntries(latestEntries.filter((entry): entry is [string, LatestPackResult] => entry[1] !== null)),
        artifactInventory: artifactInventory.items.map((item) => ({
          key: item.key,
          url: item.url,
          label: item.label,
          fileName: item.file_name,
          kind: item.kind as ArtifactKind,
          source: item.source,
          sourceLabel: item.source_label,
          pathHint: item.path_hint,
          byteSize: item.byte_size,
          updatedAt: item.updated_at,
          status: item.status,
        })),
        jobSummary,
        cloudOverview,
        cloudTasks: cloudTasks.items,
        usage,
        stagePlan,
      }));
    });
  }

  useEffect(() => {
    let active = true;
    const runLoad = async () => {
      try { await loadDashboard(); } catch (loadError) { if (!active) return; setLoading(false); setError(loadError instanceof Error ? loadError.message : "控制台加载失败"); }
    };
    runLoad();
    const timer = window.setInterval(runLoad, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (!selectedCapabilityId && state.capabilities.length > 0) { setSelectedCapabilityId(state.capabilities[0].id); setProjectName(`${state.capabilities[0].id}-项目`); }
    if (!selectedPackName && state.packs.length > 0) { setSelectedPackName(state.packs[0].pack_name); setPackProjectName(state.packs[0].default_project_name); setPackSceneCount(String(state.packs[0].default_scene_count)); }
    if (!selectedJobId && state.jobs.length > 0) setSelectedJobId(state.jobs[0].id);
  }, [selectedCapabilityId, selectedJobId, selectedPackName, state.capabilities, state.jobs, state.packs]);

  useEffect(() => {
    setSelectedJobIds((current) => current.filter((id) => state.jobs.some((job) => job.id === id)));
  }, [state.jobs]);

  useEffect(() => {
    setVisibleJobCount(40);
  }, [jobCapabilityFilter, jobStatusFilter, deferredJobSearch, jobGroupMode]);

  useEffect(() => {
    setVisibleArtifactCount(60);
  }, [artifactSourceFilter, artifactKindFilter, deferredArtifactSearch]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (page === "overview") url.searchParams.delete(PAGE_QUERY_KEY); else url.searchParams.set(PAGE_QUERY_KEY, page);
    if (selectedArtifact && page === "artifact") { url.searchParams.set(ARTIFACT_QUERY_KEY, selectedArtifact.url); url.searchParams.set(ARTIFACT_LABEL_QUERY_KEY, selectedArtifact.label); } else { url.searchParams.delete(ARTIFACT_QUERY_KEY); url.searchParams.delete(ARTIFACT_LABEL_QUERY_KEY); }
    if (jobCapabilityFilter === "all") url.searchParams.delete(JOB_FILTER_QUERY_KEY); else url.searchParams.set(JOB_FILTER_QUERY_KEY, jobCapabilityFilter);
    if (jobStatusFilter === "all") url.searchParams.delete(JOB_STATUS_QUERY_KEY); else url.searchParams.set(JOB_STATUS_QUERY_KEY, jobStatusFilter);
    if (!jobSearch.trim()) url.searchParams.delete(JOB_SEARCH_QUERY_KEY); else url.searchParams.set(JOB_SEARCH_QUERY_KEY, jobSearch.trim());
    if (!packSearch.trim()) url.searchParams.delete(PACK_SEARCH_QUERY_KEY); else url.searchParams.set(PACK_SEARCH_QUERY_KEY, packSearch.trim());
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }, [page, selectedArtifact, jobCapabilityFilter, jobSearch, jobStatusFilter, packSearch]);

  const selectedCapability = state.capabilities.find((capability) => capability.id === selectedCapabilityId) ?? null;
  const selectedPack = state.packs.find((pack) => pack.pack_name === selectedPackName) ?? null;
  const minimalSmokeChapter = selectedPack ? getPackStartChapter(selectedPack) : null;
  const filteredJobs = useMemo(() => [...(jobCapabilityFilter === "all" ? state.jobs : state.jobs.filter((job) => job.capability_id === jobCapabilityFilter))].filter((job) => jobStatusFilter === "all" || job.status === jobStatusFilter).filter((job) => !deferredJobSearch || getJobSearchText(job).includes(deferredJobSearch)).sort((a, b) => (b.status === "running" ? 1 : 0) - (a.status === "running" ? 1 : 0) || Date.parse(b.updated_at) - Date.parse(a.updated_at)), [deferredJobSearch, jobCapabilityFilter, jobStatusFilter, state.jobs]);
  const selectedJob = filteredJobs.find((job) => job.id === selectedJobId) ?? filteredJobs[0] ?? null;
  useEffect(() => {
    if (page !== "jobs" || pendingErrorFocusJobId === null || selectedJob?.id !== pendingErrorFocusJobId) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`job-error-${pendingErrorFocusJobId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setPendingErrorFocusJobId(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [page, pendingErrorFocusJobId, selectedJob]);
  const featuredJobs = filteredJobs.slice(0, 3);
  const runningJobs = state.jobs.filter((job) => job.status === "running").length;
  const taskSummary = { total: state.jobSummary?.totals.total ?? state.jobs.length, running: state.jobSummary?.totals.running ?? runningJobs, failed: state.jobSummary?.totals.failed ?? state.jobs.filter((job) => job.status === "failed").length, completed: state.jobSummary?.totals.completed ?? state.jobs.filter((job) => job.status === "completed").length };
  const syncedProviderCount = state.cloudOverview?.providers.filter((provider) => provider.uploaded_count > 0 || provider.synced_count > 0).length ?? 0;
  const uploadedArtifactCount = state.cloudOverview?.providers.reduce((sum, provider) => sum + provider.uploaded_count, 0) ?? 0;
  const artifactRecords = state.artifactInventory;
  const artifactKinds = useMemo(() => [...new Set(artifactRecords.map((artifact) => artifact.kind))], [artifactRecords]);
  const filteredArtifacts = artifactRecords.filter((artifact) => (artifactSourceFilter === "all" || artifact.source === artifactSourceFilter) && (artifactKindFilter === "all" || artifact.kind === artifactKindFilter) && (!deferredArtifactSearch || `${artifact.label} ${artifact.sourceLabel} ${artifact.kind}`.toLowerCase().includes(deferredArtifactSearch)));
  const filteredPacks = useMemo(() => state.packs.filter((pack) => !deferredPackSearch || getPackSearchText(pack, state.latestResults[pack.pack_name]).includes(deferredPackSearch)), [deferredPackSearch, state.latestResults, state.packs]);
  const pageMeta = PAGE_META[page];
  const selectedRetryableJobIds = selectedJobIds.filter((id) => filteredJobs.some((job) => job.id === id && job.status !== "running"));
  const visibleJobs = filteredJobs.slice(0, visibleJobCount);
  const visibleArtifacts = filteredArtifacts.slice(0, visibleArtifactCount);
  const groupedJobs = useMemo(() => {
    if (jobGroupMode === "none") return [{ key: "all", label: "全部任务", items: visibleJobs }];
    const map = new Map<string, JobResponse[]>();
    visibleJobs.forEach((job) => {
      const key = jobGroupMode === "status" ? job.status : job.capability_id;
      const label = jobGroupMode === "status" ? statusLabel(job.status) : job.capability_id;
      const current = map.get(`${key}::${label}`) ?? [];
      current.push(job);
      map.set(`${key}::${label}`, current);
    });
    return [...map.entries()].map(([compoundKey, items]) => {
      const [, label] = compoundKey.split("::");
      return { key: compoundKey, label, items };
    });
  }, [jobGroupMode, visibleJobs]);

  const openArtifact = (url: string, label?: string) => {
    runViewTransition(() => {
      setSelectedArtifact({ url, label: label ?? getArtifactName(url) });
      setPage("artifact");
    });
  };
  const navigatePage = (nextPage: PageKey) => {
    runViewTransition(() => {
      setPage(nextPage);
      if (nextPage !== "artifact") setSelectedArtifact(null);
    });
  };
  const submitMinimalVideoSmokeTest = async () => {
    if (!selectedPack) return;
    const smokeChapter = getPackStartChapter(selectedPack);
    const smokeProjectName = buildMinimalVideoSmokeProjectName(selectedPack);
    try {
      setRunningPack(true);
      setControlMode("pack");
      setPackProjectName(smokeProjectName);
      setPackSceneCount("2");
      setPackTargetDuration("60");
      setPackChapterStart(String(smokeChapter));
      setPackChapterEnd(String(smokeChapter));
      setPackMessage("正在提交 60s 有效视频最小测试...");
      await postJson(`/adaptation-packs/${encodeURIComponent(selectedPack.pack_name)}/jobs`, {
        project_name: smokeProjectName,
        scene_count: 2,
        target_duration_seconds: 60,
        use_real_images: true,
        chapter_start: smokeChapter,
        chapter_end: smokeChapter,
      });
      setPackMessage(`已创建 60s 有效视频最小测试任务：${smokeProjectName}`);
      await loadDashboard();
      navigatePage("jobs");
    } catch (runError) {
      setPackMessage(runError instanceof Error ? runError.message : "60s 有效视频最小测试提交失败");
    } finally {
      setRunningPack(false);
    }
  };
  const submitCreateJob = async () => {
    if (!selectedCapability) return;
    try {
      setCreatingJob(true);
      setCreateJobMessage("正在提交任务...");
      const input: Record<string, unknown> = {};
      for (const field of selectedCapability.input_fields) {
        const parsed = formatCapabilityValue(field, capabilityInputs[field.key] ?? "");
        if (parsed !== undefined) input[field.key] = parsed;
      }
      await postJson("/jobs", { capability_id: selectedCapability.id, project_name: projectName.trim() || `${selectedCapability.id}-项目`, input });
      setCreateJobMessage("任务已创建并进入执行队列。");
      await loadDashboard();
      navigatePage("jobs");
    } catch (submitError) {
      setCreateJobMessage(submitError instanceof Error ? submitError.message : "任务创建失败");
    } finally {
      setCreatingJob(false);
    }
  };

  const submitRunPack = async (useRealImages: boolean, batched: boolean) => {
    if (!selectedPack) return;
    try {
      setRunningPack(true);
      setPackMessage("正在提交适配包任务...");
      const path = batched ? `/adaptation-packs/${encodeURIComponent(selectedPack.pack_name)}/batches` : `/adaptation-packs/${encodeURIComponent(selectedPack.pack_name)}/jobs`;
      const targetDuration = packTargetDuration.trim() ? Number(packTargetDuration) : undefined;
      const payload = batched
        ? {
            project_name: packProjectName.trim() || selectedPack.default_project_name,
            batch_size: Number(packBatchSize || 5),
            scene_count: Number(packSceneCount || selectedPack.default_scene_count),
            target_duration_seconds: targetDuration,
            use_real_images: useRealImages,
          }
        : {
            project_name: packProjectName.trim() || selectedPack.default_project_name,
            scene_count: Number(packSceneCount || selectedPack.default_scene_count),
            target_duration_seconds: targetDuration,
            use_real_images: useRealImages,
            chapter_start: packChapterStart.trim() ? Number(packChapterStart) : undefined,
            chapter_end: packChapterEnd.trim() ? Number(packChapterEnd) : undefined,
          };
      await postJson(path, payload);
      setPackMessage("适配包任务已创建。");
      await loadDashboard();
      navigatePage("jobs");
    } catch (runError) {
      setPackMessage(runError instanceof Error ? runError.message : "适配包执行失败");
    } finally {
      setRunningPack(false);
    }
  };

  const submitRetryJob = async (jobId: number) => {
    try {
      setRetryingJobId(jobId);
      setRetryMessage(`正在重跑任务 #${jobId}...`);
      await postJson(`/jobs/${jobId}/retry`, {});
      setRetryMessage(`任务 #${jobId} 已重新进入队列。`);
      await loadDashboard();
    } catch (retryError) {
      setRetryMessage(retryError instanceof Error ? retryError.message : "重跑失败");
    } finally {
      setRetryingJobId(null);
    }
  };
  const submitBatchRetry = async () => {
    if (selectedRetryableJobIds.length === 0) return;
    try {
      setBatchRetrying(true);
      setRetryMessage(`正在批量重跑 ${selectedRetryableJobIds.length} 个任务...`);
      const result = await postJson<BatchRetryResponse>("/jobs/batch-retry", { job_ids: selectedRetryableJobIds });
      setRetryMessage(`批量重跑完成，已创建 ${result.created} 个新任务。`);
      setSelectedJobIds([]);
      await loadDashboard();
    } catch (retryError) {
      setRetryMessage(retryError instanceof Error ? retryError.message : "批量重跑失败");
    } finally {
      setBatchRetrying(false);
    }
  };

  const submitBatchSync = async (dryRun = false) => {
    if (selectedJobIds.length === 0) return;
    try {
      setBatchSyncing(true);
      setCloudActionMessage(dryRun ? `正在为 ${selectedJobIds.length} 个任务生成同步计划...` : `正在同步 ${selectedJobIds.length} 个任务到网盘...`);
      const result = await postJson<BatchSyncStorageResponse>("/jobs/batch-sync-storage", { job_ids: selectedJobIds, provider: "all", dry_run: dryRun });
      const labels = formatSyncResultSummary(result.items);
      setCloudActionMessage(dryRun ? `批量同步计划已生成。${labels}` : `批量同步已开始。${labels}`);
      await loadDashboard();
    } catch (syncError) {
      setCloudActionMessage(syncError instanceof Error ? syncError.message : "批量网盘同步失败");
    } finally {
      setBatchSyncing(false);
    }
  };

  const submitPackSync = async (packName: string, jobId: number, dryRun = false) => {
    try {
      setPackSyncingPackName(packName);
      setCloudActionMessage(dryRun ? `正在为 ${packName} 生成云端同步计划...` : `正在同步 ${packName} 的最近结果到网盘...`);
      const result = await postJson<JobSyncTriggerResponse>(`/jobs/${jobId}/sync-storage`, { provider: "all", dry_run: dryRun });
      const labels = formatSyncResultSummary(result.items);
      setCloudActionMessage(dryRun ? `${packName} 同步计划已生成。${labels}` : `${packName} 同步已开始。${labels}`);
      await loadDashboard();
    } catch (syncError) {
      setCloudActionMessage(syncError instanceof Error ? syncError.message : "适配包结果同步失败");
    } finally {
      setPackSyncingPackName(null);
    }
  };

  const retryCloudTask = async (taskId: string) => {
    try {
      setCloudActionMessage("正在重试后台同步任务...");
      await postJson(`/cloud-sync-tasks/${taskId}/retry`, {});
      setCloudActionMessage("后台同步任务已重新入队。");
      await loadDashboard();
    } catch (error) {
      setCloudActionMessage(error instanceof Error ? error.message : "同步任务重试失败");
    }
  };

  const latestResultsPanel = (
    <section className="panel-card">
      <div className="section-head"><div><p className="section-tag">最近结果</p><h2>适配包结果</h2></div></div>
      <label className="field inline-field pack-search-field">
        <span>搜索</span>
        <input value={packSearch} onChange={(event) => setPackSearch(event.target.value)} placeholder="包名 / 源标题 / 章节 / 结果状态" />
      </label>
      <div className="pack-stack">
        {filteredPacks.length > 0 ? filteredPacks.map((pack) => {
          const latest = state.latestResults[pack.pack_name];
          return (
            <article key={pack.pack_name} className="pack-card modern-pack-card">
              <div className="pack-cover"><span>{pack.source_title.slice(0, 2)}</span></div>
              <div className="pack-copy">
                <strong>{pack.source_title}</strong>
                <p>{pack.pack_name} / {pack.chapter_range}</p>
                {latest ? (
                  <>
                    <div className="result-meta-row">
                      <span className={`status-pill ${statusTone(latest.validation_status)}`}>{statusLabel(latest.validation_status)}</span>
                      <span className="result-timestamp">{formatDate(latest.updated_at)}</span>
                    </div>
                    <div className="link-list compact">
                      <button type="button" className="artifact-link" onClick={() => openArtifact(latest.artifact_summary_url, "结果摘要")}>摘要</button>
                      <button type="button" className="artifact-link" onClick={() => openArtifact(latest.artifact_validation_url, "校验报告")}>校验</button>
                      <button type="button" className="artifact-link" onClick={() => openArtifact(latest.artifact_snapshot_url, "运行快照")}>快照</button>
                    </div>
                    <div className="link-list compact">
                      <button type="button" className="mini-button" disabled={packSyncingPackName !== null} onClick={() => { void submitPackSync(pack.pack_name, latest.job_id, true); }}>{packSyncingPackName === pack.pack_name ? "计划中..." : "同步计划"}</button>
                      <button type="button" className="secondary-button" disabled={packSyncingPackName !== null} onClick={() => { void submitPackSync(pack.pack_name, latest.job_id, false); }}>{packSyncingPackName === pack.pack_name ? "同步中..." : "同步云端"}</button>
                    </div>
                  </>
                ) : <p>暂时还没有最近一次运行结果。</p>}
              </div>
            </article>
          );
        }) : <article className="empty-state-card"><strong>暂无匹配的适配包</strong><p className="job-summary">换个包名、源标题或章节关键字再试。</p></article>}
      </div>
    </section>
  );

  return (
    <div className="dashboard-shell">
      <aside className="dashboard-sidebar">
        <div className="sidebar-brand"><div className="brand-mark">AMF</div><div className="brand-copy"><p className="eyebrow">AI Manga Factory</p><strong>业务工作台</strong><span>任务与产物统一在同一个操作框架里</span></div></div>
        <nav className="side-nav">{PAGE_ITEMS.map((item) => <button key={item} type="button" className={`side-nav-item ${page === item ? "active" : ""}`} onClick={() => navigatePage(item)}><span className="side-nav-dot" /><span>{PAGE_META[item].label}</span></button>)}</nav>
        <section className="sidebar-card"><p className="section-tag">概览</p><div className="sidebar-metric"><span>项目</span><strong>{state.projects.length}</strong></div><div className="sidebar-metric"><span>任务</span><strong>{state.jobs.length}</strong></div><div className="sidebar-metric"><span>适配包</span><strong>{state.packs.length}</strong></div><div className="sidebar-metric"><span>运行中</span><strong>{runningJobs}</strong></div><div className="sidebar-metric"><span>云端 provider</span><strong>{syncedProviderCount}</strong></div><div className="sidebar-metric"><span>云端文件</span><strong>{uploadedArtifactCount}</strong></div></section>
        <a className="legacy-link" href={resolveUrl("/legacy")} target="_blank" rel="noreferrer">打开旧版控制台</a>
      </aside>

      <main className="dashboard-main">
        <section className="page-title-card"><div><p className="section-tag">{pageMeta.eyebrow}</p><h2>{pageMeta.label}</h2></div></section>
        {error ? <section className="notice error">{error}</section> : null}
        {loading ? <section className="notice">正在加载控制台数据...</section> : null}
        {cloudActionMessage ? <section className="notice">{cloudActionMessage}</section> : null}

        {page === "overview" ? <>
          <section className="hero-card overview-stage">
            <div className="overview-stage-copy">
              <p className="eyebrow">总览</p>
              <h1>从任务到云端交付，在一个工作面里完成。</h1>
              <p className="hero-text">这里先给你当前运行态、最近交付和云端同步结果，再决定是发起新任务、处理失败项，还是直接核对产物。</p>
              <div className="overview-stage-actions">
                {([
                  { key: "actions" as const, title: "发起任务", meta: `${state.capabilities.length} 个能力` },
                  { key: "jobs" as const, title: "处理任务", meta: `${taskSummary.running} 个运行中` },
                  { key: "artifact" as const, title: "检查产物", meta: `${artifactRecords.length} 个产物` },
                ]).map((item) => (
                  <button key={item.key} type="button" className="overview-shortcut compact hero-shortcut" onClick={() => navigatePage(item.key)}>
                    <strong>{item.title}</strong>
                    <span>{item.meta}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className="overview-shortcut compact hero-shortcut smoke-shortcut"
                  onClick={() => {
                    setControlMode("pack");
                    navigatePage("actions");
                  }}
                >
                  <strong>60s 测试</strong>
                  <span>内容优先有效视频</span>
                </button>
              </div>
            </div>
            <div className="overview-stage-metrics">
              <div className="overview-stat compact spotlight"><span>运行中任务</span><strong>{taskSummary.running}</strong></div>
              <div className="overview-stat compact"><span>任务总数</span><strong>{taskSummary.total}</strong></div>
              <div className="overview-stat compact"><span>已完成</span><strong>{taskSummary.completed}</strong></div>
              <div className="overview-stat compact"><span>云端 provider</span><strong>{syncedProviderCount}</strong></div>
              <div className="overview-stat compact"><span>云端文件</span><strong>{uploadedArtifactCount}</strong></div>
              <div className="overview-stat compact"><span>产物数量</span><strong>{artifactRecords.length}</strong></div>
            </div>
          </section>

          <section className="overview-main-grid">
            <div className="main-column">
              <section className="panel-card overview-recent">
                <div className="section-head"><div><p className="section-tag">最近任务</p><h2>最近任务</h2></div><button className="mini-button" type="button" onClick={() => navigatePage("jobs")}>查看全部</button></div>
                <div className="overview-recent-list">{featuredJobs.length > 0 ? featuredJobs.map((job) => <button key={job.id} type="button" className="overview-recent-item rich" onClick={() => { runViewTransition(() => { setSelectedJobId(job.id); setPage("jobs"); setSelectedArtifact(null); }); }}><div className="overview-recent-head"><strong>{job.capability_id} #{job.id}</strong><span className={`status-pill ${statusTone(job.status)}`}>{statusLabel(job.status)}</span></div><p className="overview-recent-summary">{job.summary || "暂无摘要"}</p><div className="overview-recent-meta"><span>{getJobContext(job)}</span><span>{formatDate(job.updated_at)}</span></div></button>) : <article className="empty-state-card"><strong>还没有最近任务</strong><p className="job-summary">先去创建任务或运行适配包。</p></article>}</div>
              </section>
              {latestResultsPanel}
            </div>
            <div className="side-column">
              <CloudSyncOverviewPanel overview={state.cloudOverview} />
              <CloudSyncQueuePanel tasks={state.cloudTasks} onRetry={(taskId) => { void retryCloudTask(taskId); }} />
            </div>
          </section>
        </> : null}

        {page === "actions" ? (
          <section className="page-grid with-sidebar">
            <div className="control-column">
              <section className="control-card">
                <div className="segmented">
                  <button className={controlMode === "job" ? "active" : ""} onClick={() => setControlMode("job")} type="button">创建任务</button>
                  <button className={controlMode === "pack" ? "active" : ""} onClick={() => setControlMode("pack")} type="button">运行适配包</button>
                </div>
                {controlMode === "job" ? (
                  <>
                    <div className="section-head">
                      <div>
                        <p className="section-tag">任务创建</p>
                        <h2>创建通用任务</h2>
                      </div>
                      <span>{selectedCapability?.name ?? "暂无"}</span>
                    </div>
                    <label className="field">
                      <span>能力</span>
                      <select value={selectedCapabilityId} onChange={(event) => setSelectedCapabilityId(event.target.value)}>
                        {state.capabilities.map((capability) => <option key={capability.id} value={capability.id}>{capability.name}</option>)}
                      </select>
                    </label>
                    <label className="field">
                      <span>项目名</span>
                      <input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="漫画项目" />
                    </label>
                    <div className="field-grid">
                      {selectedCapability?.input_fields.map((field) => (
                        <label key={field.key} className="field">
                          <span>{field.label}{field.required ? " *" : ""}</span>
                          {field.field_type === "boolean" ? (
                            <select value={capabilityInputs[field.key] ?? ""} onChange={(event) => setCapabilityInputs((current) => ({ ...current, [field.key]: event.target.value }))}>
                              <option value="">请选择</option>
                              <option value="true">是</option>
                              <option value="false">否</option>
                            </select>
                          ) : field.field_type === "array" ? (
                            <textarea value={capabilityInputs[field.key] ?? ""} onChange={(event) => setCapabilityInputs((current) => ({ ...current, [field.key]: event.target.value }))} placeholder={fieldPlaceholder(field)} />
                          ) : (
                            <input type={field.field_type === "integer" ? "number" : "text"} value={capabilityInputs[field.key] ?? ""} onChange={(event) => setCapabilityInputs((current) => ({ ...current, [field.key]: event.target.value }))} placeholder={fieldPlaceholder(field)} />
                          )}
                        </label>
                      ))}
                    </div>
                    <button className="primary-button" onClick={submitCreateJob} disabled={creatingJob}>{creatingJob ? "提交中..." : "创建并执行任务"}</button>
                    {createJobMessage ? <p className="inline-message">{createJobMessage}</p> : null}
                  </>
                ) : (
                  <>
                    <div className="section-head">
                      <div>
                        <p className="section-tag">适配包</p>
                        <h2>运行适配包</h2>
                      </div>
                      <span>{selectedPack?.pack_name ?? "暂无"}</span>
                    </div>
                    <section className="smoke-test-card">
                      <div className="section-head">
                        <div>
                          <p className="section-tag">最小测试</p>
                          <h3>60s 有效视频</h3>
                        </div>
                        <span className="status-pill warn">真图</span>
                      </div>
                      <p className="smoke-test-copy">
                        按内容完整性优先触发最小 smoke test。默认取当前适配包首章、2 个分镜、60 秒目标上限，不为了凑时长补重复镜头。
                      </p>
                      <div className="smoke-test-meta">
                        <span>当前适配包：{selectedPack?.pack_name ?? "暂无"}</span>
                        <span>测试章节：{minimalSmokeChapter ? `${minimalSmokeChapter}-${minimalSmokeChapter}` : "待选择"}</span>
                        <span>项目名：自动生成</span>
                      </div>
                      <button className="primary-button" type="button" onClick={() => { void submitMinimalVideoSmokeTest(); }} disabled={runningPack || !selectedPack}>
                        {runningPack ? "提交中..." : "运行 60s 有效视频最小测试"}
                      </button>
                    </section>
                    <label className="field">
                      <span>适配包</span>
                      <select value={selectedPackName} onChange={(event) => setSelectedPackName(event.target.value)}>
                        {state.packs.map((pack) => <option key={pack.pack_name} value={pack.pack_name}>{pack.source_title} ({pack.chapter_range})</option>)}
                      </select>
                    </label>
                    <label className="field">
                      <span>项目名</span>
                      <input value={packProjectName} onChange={(event) => setPackProjectName(event.target.value)} placeholder="适配项目" />
                    </label>
                    <div className="field-grid two-up">
                      <label className="field">
                        <span>分镜图数量</span>
                        <input type="number" value={packSceneCount} onChange={(event) => setPackSceneCount(event.target.value)} min={2} max={60} />
                      </label>
                      <label className="field">
                        <span>每批章节数</span>
                        <input type="number" value={packBatchSize} onChange={(event) => setPackBatchSize(event.target.value)} min={1} max={20} />
                      </label>
                    </div>
                    <div className="field-grid two-up">
                      <label className="field">
                        <span>目标时长（秒）</span>
                        <input type="number" value={packTargetDuration} onChange={(event) => setPackTargetDuration(event.target.value)} min={20} max={180} placeholder="可留空，按内容" />
                      </label>
                      <label className="field">
                        <span>开始章节</span>
                        <input type="number" value={packChapterStart} onChange={(event) => setPackChapterStart(event.target.value)} min={1} />
                      </label>
                    </div>
                    <div className="field-grid two-up">
                      <label className="field">
                        <span>结束章节</span>
                        <input type="number" value={packChapterEnd} onChange={(event) => setPackChapterEnd(event.target.value)} min={1} />
                      </label>
                      <div />
                    </div>
                    <div className="button-grid">
                      <button className="primary-button" onClick={() => submitRunPack(false, false)} disabled={runningPack}>整包占位图</button>
                      <button className="secondary-button" onClick={() => submitRunPack(true, false)} disabled={runningPack}>整包真图</button>
                      <button className="secondary-button" onClick={() => submitRunPack(false, true)} disabled={runningPack}>分批占位图</button>
                      <button className="secondary-button" onClick={() => submitRunPack(true, true)} disabled={runningPack}>分批真图</button>
                    </div>
                    {packMessage ? <p className="inline-message">{packMessage}</p> : null}
                  </>
                )}
              </section>
            </div>
            <div className="side-column">
              <CloudSyncOverviewPanel overview={state.cloudOverview} />
              <CloudSyncQueuePanel tasks={state.cloudTasks} onRetry={(taskId) => { void retryCloudTask(taskId); }} />
              {latestResultsPanel}
            </div>
          </section>
        ) : null}
        {page === "jobs" ? (
          <section className="page-grid task-page-grid">
            <div className="control-column">
              <section className="control-card sticky-card compact-filters">
                <div className="section-head">
                  <div>
                    <p className="section-tag">任务筛选</p>
                    <h2>任务工作台</h2>
                  </div>
                  <button className="mini-button" onClick={() => { setJobCapabilityFilter("all"); setJobStatusFilter("all"); setJobSearch(""); setSelectedJobIds([]); }} type="button">重置</button>
                </div>
                <div className="filter-toolbar">
                  <div className="metric-row compact">
                    <div className="metric-tile compact"><span>总数</span><strong>{taskSummary.total}</strong></div>
                    <div className="metric-tile compact"><span>运行中</span><strong>{taskSummary.running}</strong></div>
                    <div className="metric-tile compact"><span>失败</span><strong>{taskSummary.failed}</strong></div>
                  </div>
                  <label className="field inline-field">
                    <span>搜索</span>
                    <input type="text" value={jobSearch} onChange={(event) => setJobSearch(event.target.value)} placeholder="项目 / 来源 / 目标 / 适配包" />
                  </label>
                </div>
                <div className="compact-filter-grid">
                  <div className="filter-block">
                    <span className="section-tag">能力</span>
                    <div className="chip-block">
                      {["all", ...(state.jobSummary?.by_capability.map((item) => item.key) ?? [...new Set(state.jobs.map((job) => job.capability_id))])].map((option) => <button key={option} className={`chip ${jobCapabilityFilter === option ? "active" : ""}`} onClick={() => setJobCapabilityFilter(option)} type="button">{option}</button>)}
                    </div>
                  </div>
                  <div className="filter-block">
                    <span className="section-tag">状态</span>
                    <div className="chip-block">
                      {JOB_STATUS_FILTERS.map((option) => <button key={option} className={`chip ${jobStatusFilter === option ? "active" : ""}`} onClick={() => setJobStatusFilter(option)} type="button">{option}</button>)}
                    </div>
                  </div>
                  <div className="filter-block">
                    <span className="section-tag">分组</span>
                    <div className="chip-block">
                      {[{ key: "status", label: "按状态" }, { key: "capability", label: "按能力" }, { key: "none", label: "不分组" }].map((option) => <button key={option.key} className={`chip ${jobGroupMode === option.key ? "active" : ""}`} onClick={() => setJobGroupMode(option.key as JobGroupMode)} type="button">{option.label}</button>)}
                    </div>
                  </div>
                </div>
                {retryMessage ? <p className="inline-message">{retryMessage}</p> : null}
              </section>
            </div>
            <div className="main-column">
              <section className="panel-card">
                <div className="section-head"><div><p className="section-tag">任务列表</p><h2>任务列表</h2></div><span>显示 {filteredJobs.length} 条</span></div>
                {selectedJobIds.length > 0 ? <div className="batch-action-bar"><span>已选 {selectedJobIds.length} 项，可重跑 {selectedRetryableJobIds.length} 项</span><div className="link-list compact"><button className="secondary-button" type="button" onClick={() => { void submitBatchSync(true); }} disabled={batchSyncing}> {batchSyncing ? "计划中..." : "交付计划"} </button><button className="primary-button" type="button" onClick={() => { void submitBatchSync(false); }} disabled={batchSyncing}> {batchSyncing ? "同步中..." : "批量交付"} </button><button className="primary-button" type="button" onClick={() => { void submitBatchRetry(); }} disabled={batchRetrying || selectedRetryableJobIds.length === 0}>{batchRetrying ? "批量重跑中..." : "批量重跑"}</button></div></div> : null}
                <div className="task-list">{filteredJobs.length > 0 ? groupedJobs.map((group) => <section key={group.key} className="task-group"><div className="task-group-head"><strong>{group.label}</strong><span>{group.items.length} 项</span></div>{group.items.map((job) => { const activeStep = getJobActiveStep(job); const artifacts = getPrioritizedArtifacts(job); const validationArtifact = getJobValidationArtifact(job); const errorArtifact = getJobErrorArtifact(job); const isSelected = selectedJob?.id === job.id; const isChecked = selectedJobIds.includes(job.id); const actionPopoverId = `task-actions-${job.id}`; return <div key={job.id} className={`task-row ${isSelected ? "active" : ""}`}><div className="task-row-main selectable"><label className="task-check"><input type="checkbox" checked={isChecked} onChange={(event) => setSelectedJobIds((current) => event.target.checked ? [...new Set([...current, job.id])] : current.filter((id) => id !== job.id))} /><span /></label><div className="task-row-body"><button type="button" className="task-row-button" onClick={() => runViewTransition(() => setSelectedJobId(job.id))}><div className="task-row-head"><div><strong>{job.capability_id} #{job.id}</strong><p>{getJobContext(job)}</p></div><span className={`status-pill ${statusTone(job.status)}`}>{statusLabel(job.status)}</span></div><p className="task-row-summary">{job.summary || "暂无摘要"}</p><div className="task-row-meta"><span>{activeStep ? activeStep.title : "无步骤"}</span><span>{artifacts.length} 产物</span><span>{formatDate(job.updated_at)}</span></div></button><div className="task-row-tools"><button className="mini-button" type="button" popoverTarget={actionPopoverId}>更多</button><div id={actionPopoverId} popover="auto" className="task-action-popover"><div className="popover-head"><strong>任务 #{job.id}</strong><span>{job.capability_id}</span></div><div className="popover-option-list"><button type="button" className="popover-option" onClick={() => runViewTransition(() => setSelectedJobId(job.id))}><strong>查看详情</strong><span>在右侧检查步骤、错误和输入参数。</span></button>{job.status === "failed" && validationArtifact ? <button type="button" className="popover-option" onClick={() => openArtifact(validationArtifact.url, validationArtifact.label)}><strong>查看校验</strong><span>{validationArtifact.label}</span></button> : null}{job.status === "failed" ? <button type="button" className="popover-option" onClick={() => focusJobErrorDetail(job.id)}><strong>错误详情</strong><span>直接打开右侧错误说明。</span></button> : null}{artifacts[0] && job.status !== "failed" ? <button type="button" className="popover-option" onClick={() => openArtifact(artifacts[0].url, artifacts[0].label)}><strong>打开首个产物</strong><span>{artifacts[0].label}</span></button> : null}{job.status !== "running" ? <button type="button" className="popover-option" onClick={() => { void submitRetryJob(job.id); }}><strong>{job.status === "failed" ? "重跑失败任务" : "重跑任务"}</strong><span>按原输入重新创建一个新任务。</span></button> : null}{job.status === "failed" && errorArtifact ? <button type="button" className="popover-option" onClick={() => openArtifact(errorArtifact.url, errorArtifact.label)}><strong>错误产物</strong><span>{errorArtifact.label}</span></button> : null}</div></div></div></div></div></div>; })}</section>) : <article className="empty-state-card"><strong>暂无符合条件的任务</strong><p className="job-summary">换个筛选条件，或先去创建任务。</p></article>}</div>
                {filteredJobs.length > visibleJobCount ? <button className="secondary-button load-more-button" type="button" onClick={() => setVisibleJobCount((current) => current + 40)}>加载更多任务</button> : null}
              </section>
            </div>
            <div className="side-column"><TaskDetail job={selectedJob} onOpenArtifact={openArtifact} onRetry={submitRetryJob} retrying={retryingJobId === selectedJob?.id} onSynced={loadDashboard} /></div>
          </section>
        ) : null}

        {page === "artifact" ? (
          <section className="page-grid artifact-page-grid">
            <div className="control-column">
              <section className="control-card sticky-card compact-filters">
                <div className="section-head">
                  <div>
                    <p className="section-tag">产物筛选</p>
                    <h2>产物工作区</h2>
                  </div>
                  <button className="mini-button" type="button" onClick={() => { setArtifactSourceFilter("all"); setArtifactKindFilter("all"); setArtifactSearch(""); }}>重置</button>
                </div>
                <div className="filter-toolbar">
                  <div className="metric-row compact">
                    <div className="metric-tile compact"><span>总数</span><strong>{artifactRecords.length}</strong></div>
                    <div className="metric-tile compact"><span>任务产物</span><strong>{artifactRecords.filter((item) => item.source === "job").length}</strong></div>
                    <div className="metric-tile compact"><span>结果产物</span><strong>{artifactRecords.filter((item) => item.source === "pack").length}</strong></div>
                  </div>
                  <label className="field inline-field">
                    <span>搜索</span>
                    <input value={artifactSearch} onChange={(event) => setArtifactSearch(event.target.value)} placeholder="名称 / 来源 / 类型" />
                  </label>
                </div>
                <div className="compact-filter-grid">
                  <div className="filter-block">
                    <span className="section-tag">来源</span>
                    <div className="chip-block">
                      {(["all", "job", "pack"] as const).map((option) => <button key={option} className={`chip ${artifactSourceFilter === option ? "active" : ""}`} type="button" onClick={() => setArtifactSourceFilter(option)}>{option === "all" ? "全部" : option === "job" ? "任务" : "结果"}</button>)}
                    </div>
                  </div>
                  <div className="filter-block">
                    <span className="section-tag">类型</span>
                    <div className="chip-block">
                      <button className={`chip ${artifactKindFilter === "all" ? "active" : ""}`} type="button" onClick={() => setArtifactKindFilter("all")}>全部</button>
                      {artifactKinds.map((kind) => <button key={kind} className={`chip ${artifactKindFilter === kind ? "active" : ""}`} type="button" onClick={() => setArtifactKindFilter(kind)}>{kind}</button>)}
                    </div>
                  </div>
                </div>
              </section>
            </div>
            <div className="main-column">
              <section className="panel-card">
                <div className="section-head"><div><p className="section-tag">产物清单</p><h2>产物清单</h2></div><span>{filteredArtifacts.length} 项</span></div>
                <div className="artifact-list">{filteredArtifacts.length > 0 ? visibleArtifacts.map((artifact) => <button key={artifact.key} type="button" className={`artifact-row ${selectedArtifact?.url === artifact.url ? "active" : ""}`} onClick={() => openArtifact(artifact.url, artifact.label)}><div className="artifact-row-main"><div className="artifact-row-head"><strong>{artifact.label}</strong><span className={`status-pill ${statusTone(artifact.status)}`}>{statusLabel(artifact.status)}</span></div><div className="artifact-row-meta"><span>{artifact.sourceLabel}</span><span>{artifact.kind}</span><span>{formatDate(artifact.updatedAt)}</span><span>{formatBytes(artifact.byteSize)}</span></div><div className="artifact-row-submeta"><span>{artifact.fileName}</span></div></div></button>) : <article className="empty-state-card"><strong>暂无符合条件的产物</strong><p className="job-summary">换个筛选条件，或从任务页打开产物。</p></article>}</div>
                {filteredArtifacts.length > visibleArtifactCount ? <button className="secondary-button load-more-button" type="button" onClick={() => setVisibleArtifactCount((current) => current + 60)}>加载更多产物</button> : null}
              </section>
            </div>
            <div className="side-column"><section className="panel-card artifact-meta-panel">{selectedArtifact ? (() => { const artifact = artifactRecords.find((item) => item.url === selectedArtifact.url); return artifact ? <div className="detail-stack"><div className="section-head"><div><p className="section-tag">产物信息</p><h2>{artifact.label}</h2></div><span className={`status-pill ${statusTone(artifact.status)}`}>{statusLabel(artifact.status)}</span></div><div className="detail-overview"><div className="detail-kv wide"><span>文件名</span><strong>{artifact.fileName}</strong></div><div className="detail-kv"><span>来源</span><strong>{artifact.sourceLabel}</strong></div><div className="detail-kv"><span>类型</span><strong>{artifact.kind}</strong></div><div className="detail-kv"><span>大小</span><strong>{formatBytes(artifact.byteSize)}</strong></div></div>{artifact.pathHint ? <details className="detail-disclosure compact-disclosure"><summary className="detail-disclosure-head"><div><strong>路径</strong><span>展开查看</span></div></summary><div className="detail-panel detail-panel-body"><p className="detail-path">{artifact.pathHint}</p></div></details> : null}</div> : null; })() : <div className="artifact-empty"><strong>选择一个产物</strong><p>这里会展示文件名、大小和来源上下文。</p></div>}</section><ArtifactSyncPanel selection={selectedArtifact} /><ArtifactViewer selection={selectedArtifact} /></div>
          </section>
        ) : null}

        {page === "models" ? (
          <section className="page-grid models-page-grid">
            <div className="main-column">
              <section className="panel-card">
                <div className="section-head">
                  <div>
                    <p className="section-tag">模型用量</p>
                    <h2>模型使用概览</h2>
                  </div>
                  <span>{state.usage?.period_key ?? "暂无"}</span>
                </div>
                <div className="provider-grid">
                  {state.usage?.capabilities?.length ? (
                    state.usage.capabilities.map((capability) => (
                      <article key={capability.capability} className="provider-card">
                        <div className="section-head">
                          <strong>{capability.capability}</strong>
                          <span>{capability.active_model ?? "暂无"}</span>
                        </div>
                        <p>预警 {Math.round(capability.warning_ratio * 100)}% / 切换 {Math.round(capability.switch_ratio * 100)}%</p>
                        <div className="provider-models">
                          {capability.models.slice(0, 4).map((model) => (
                            <div key={model.name} className="provider-row">
                              <span>{model.label}</span>
                              <strong>{model.usage_value}{model.usage_unit}</strong>
                            </div>
                          ))}
                        </div>
                      </article>
                    ))
                  ) : (
                    <p className="inline-message">暂无模型使用数据</p>
                  )}
                </div>
              </section>
            </div>
            <div className="side-column">
              <section className="panel-card">
                <div className="section-head">
                  <div>
                    <p className="section-tag">阶段策略</p>
                    <h2>阶段模型策略</h2>
                  </div>
                  <span>{formatDate(state.stagePlan?.updated_at)}</span>
                </div>
                <div className="stage-stack">
                  {state.stagePlan?.pipeline?.length ? (
                    state.stagePlan.pipeline.map((stage) => (
                      <article key={stage.stage} className="stage-card">
                        <div className="section-head">
                          <strong>{stage.stage}</strong>
                          <span>{stage.current_default ?? "未配置"}</span>
                        </div>
                        <p>{stage.notes}</p>
                      </article>
                    ))
                  ) : (
                    <p className="inline-message">暂无阶段策略数据</p>
                  )}
                </div>
              </section>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}
