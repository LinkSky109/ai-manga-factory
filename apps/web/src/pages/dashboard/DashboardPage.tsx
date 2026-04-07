import { MetricCard } from "../../components/stitch/MetricCard";
import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import type { JobRun, ProjectInitialization, ProjectOverview } from "../../types/api";

interface DashboardPageProps {
  overview: ProjectOverview;
  jobs: JobRun[];
  initialization: ProjectInitialization;
  sampleMode: boolean;
}

export function DashboardPage({ overview, jobs, initialization, sampleMode }: DashboardPageProps) {
  const generationTrace = initialization.generation_trace;

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Project Control Tower</p>
          <h1 data-testid="hero-project-name">{overview.project_name}</h1>
          <p className="lede">{overview.summary}</p>
        </div>
        <div className="hero-meta">
          <div>
            <span className="meta-label">项目状态</span>
            <StatusPill tone={overview.status === "completed" ? "success" : "warning"}>
              {overview.status}
            </StatusPill>
          </div>
          <div>
            <span className="meta-label">当前模式</span>
            <StatusPill tone={sampleMode ? "warning" : "success"}>
              {sampleMode ? "sample" : "live"}
            </StatusPill>
          </div>
        </div>
      </section>

      <div className="metric-grid">
        {overview.chapter_progress.map((item) => (
          <MetricCard key={item.label} label={item.label} value={item.value} tone={item.tone} />
        ))}
      </div>

      <div className="two-column-grid">
        <SectionCard title="资产健康度" eyebrow="Asset Health">
          <div className="stack-list">
            {overview.asset_health.map((item) => (
              <div className="list-row" key={item.label}>
                <span>{item.label}</span>
                <StatusPill tone={item.tone}>{item.value}</StatusPill>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="模型消耗概览" eyebrow="Provider Usage">
          <div className="stack-list">
            {overview.provider_usage.map((item) => (
              <div className="list-row" key={item.label}>
                <span>{item.label}</span>
                <StatusPill tone={item.tone}>{item.value}</StatusPill>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="two-column-grid">
        <SectionCard title="项目初始化" eyebrow="Initialization Pipeline">
          <div className="stack-list">
            {overview.initialization_progress.map((item) => (
              <div className="list-row" key={item.label}>
                <span>{item.label}</span>
                <StatusPill tone={item.tone}>{item.value}</StatusPill>
              </div>
            ))}
            {generationTrace ? (
              <>
                <div className="list-row">
                  <span>生成模式</span>
                  <StatusPill tone={generationTrace.generation_mode === "model" ? "success" : "warning"}>
                    {generationTrace.generation_mode}
                  </StatusPill>
                </div>
                <div className="list-row">
                  <span>命中 Provider</span>
                  <StatusPill tone="neutral">{generationTrace.resolved_provider_key ?? "pending"}</StatusPill>
                </div>
                <p className="muted-copy">
                  {generationTrace.provider_attempts
                    .map((attempt) => `${attempt.provider_key} (${attempt.status})`)
                    .join(" -> ")}
                </p>
              </>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="原文导入与摘要" eyebrow="Story Intake">
          <div className="stack-list">
            <div className="list-row">
              <span>原文标题</span>
              <StatusPill tone={initialization.source ? "success" : "warning"}>
                {initialization.source?.source_title ?? "pending"}
              </StatusPill>
            </div>
            <p className="muted-copy">{initialization.source?.content_preview ?? "当前还没有导入原文。"} </p>
            <p className="muted-copy">{initialization.summary?.summary_body ?? "当前还没有生成项目摘要。"} </p>
          </div>
        </SectionCard>
      </div>

      <div className="two-column-grid">
        <SectionCard title="剧本初稿" eyebrow="Script Draft">
          <div className="stack-list">
            <div className="list-row">
              <span>当前版本</span>
              <StatusPill tone={initialization.script ? "success" : "warning"}>
                {initialization.script?.status ?? "pending"}
              </StatusPill>
            </div>
            <div className="prompt-diff-box">
              <span>{initialization.script?.title ?? "待生成剧本初稿"}</span>
              <p>{initialization.script?.script_body.slice(0, 260) ?? "当前还没有剧本初稿。"} </p>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="初始化资产草稿" eyebrow="Draft Assets">
          <div className="stack-list">
            <div className="list-row">
              <span>角色初稿</span>
              <StatusPill tone={initialization.character_drafts.length > 0 ? "success" : "warning"}>
                {String(initialization.character_drafts.length)}
              </StatusPill>
            </div>
            <div className="list-row">
              <span>场景初稿</span>
              <StatusPill tone={initialization.scene_drafts.length > 0 ? "success" : "warning"}>
                {String(initialization.scene_drafts.length)}
              </StatusPill>
            </div>
            <p className="muted-copy">
              {initialization.character_drafts.slice(0, 3).map((item) => item.name).join(" / ") || "待抽取角色"}
            </p>
            <p className="muted-copy">
              {initialization.scene_drafts.slice(0, 3).map((item) => item.name).join(" / ") || "待抽取场景"}
            </p>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="最近任务" eyebrow="Recent Jobs">
        <div className="stack-list">
          {jobs.slice(0, 4).map((job) => (
            <article className="job-row" key={job.id}>
              <div>
                <strong>Job #{job.id}</strong>
                <p>{job.summary ?? "任务已创建，等待更多摘要。"}</p>
                {(job.worker_id || job.attempt_count) ? (
                  <p className="muted-copy">
                    {job.worker_id ? `worker: ${job.worker_id}` : "worker: pending"}
                    {typeof job.attempt_count === "number" ? ` · attempts: ${job.attempt_count}` : ""}
                  </p>
                ) : null}
              </div>
              <div className="job-row-meta">
                <StatusPill tone={job.status === "completed" ? "success" : job.status === "failed" ? "danger" : "warning"}>
                  {job.status}
                </StatusPill>
                <span>{job.routing_mode}</span>
              </div>
            </article>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
