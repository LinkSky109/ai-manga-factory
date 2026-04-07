import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import type { JobRun, JobRunStep, MonitoringOverview, ProviderAttempt, WorkflowDefinition } from "../../types/api";

interface MonitoringPageProps {
  monitoring: MonitoringOverview;
  jobs: JobRun[];
  workflows: WorkflowDefinition[];
}

interface RoutingEvent {
  id: string;
  jobId: number;
  chapterId: number | null;
  stepKey: string;
  stepName: string;
  finalStatus: string;
  resolvedProviderKey: string | null;
  attempts: ProviderAttempt[];
  candidates: string[];
  updatedAt: string;
  errorMessage: string | null;
}

function toneForStatus(status: string) {
  if (status === "completed" || status === "healthy") {
    return "success";
  }
  if (status === "failed" || status === "danger" || status === "critical" || status === "stopped") {
    return "danger";
  }
  if (status === "running" || status === "queued" || status === "warning") {
    return "warning";
  }
  return "neutral";
}

function normalizeAttempts(step: JobRunStep): ProviderAttempt[] {
  if (step.output_snapshot?.provider_attempts && step.output_snapshot.provider_attempts.length > 0) {
    return step.output_snapshot.provider_attempts;
  }
  if (step.provider_key) {
    return [
      {
        provider_key: step.provider_key,
        status: step.status,
        error_message: step.error_message,
      },
    ];
  }
  return [];
}

function buildRoutingEvents(jobs: JobRun[]): RoutingEvent[] {
  const toTimestamp = (value: string) => {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  };

  return jobs
    .flatMap((job) =>
      job.steps.map((step) => {
        const attempts = normalizeAttempts(step);
        const candidates = step.output_snapshot?.provider_candidates ?? attempts.map((attempt) => attempt.provider_key);
        return {
          id: `${job.id}-${step.id}`,
          jobId: job.id,
          chapterId: job.chapter_id,
          stepKey: step.step_key,
          stepName: step.step_name,
          finalStatus: step.status,
          resolvedProviderKey: step.output_snapshot?.resolved_provider_key ?? step.provider_key,
          attempts,
          candidates,
          updatedAt: step.updated_at || job.updated_at,
          errorMessage: step.error_message,
        };
      }),
    )
    .sort((left, right) => toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt));
}

function renderChapterLabel(chapterId: number | null) {
  if (chapterId === null) {
    return "全局任务";
  }
  return `章节 ${chapterId}`;
}

function renderAttemptStatus(status: string) {
  if (status === "completed") {
    return "hit";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "running") {
    return "running";
  }
  return status;
}

export function MonitoringPage({ monitoring, jobs, workflows }: MonitoringPageProps) {
  const routingEvents = buildRoutingEvents(jobs);
  const routedSteps = routingEvents.length;
  const directHits = routingEvents.filter(
    (event) => event.attempts.length === 1 && event.attempts[0]?.status === "completed",
  ).length;
  const fallbackHits = routingEvents.filter(
    (event) => event.attempts.length > 1 && event.attempts.some((attempt) => attempt.status === "completed"),
  ).length;
  const terminalFailures = routingEvents.filter(
    (event) => event.finalStatus === "failed" || event.attempts.every((attempt) => attempt.status !== "completed"),
  ).length;
  const fallbackEvents = routingEvents.filter(
    (event) => event.attempts.length > 1 || event.attempts.some((attempt) => attempt.status === "failed"),
  );

  return (
    <div className="page-stack" data-testid="page-monitoring">
      <div className="three-column-grid">
        <SectionCard title="作业状态" eyebrow="Jobs">
          <div className="stack-list">
            <div className="list-row">
              <span>已完成</span>
              <StatusPill tone="success">{String(monitoring.summary.completed_jobs)}</StatusPill>
            </div>
            <div className="list-row">
              <span>运行中</span>
              <StatusPill tone="warning">{String(monitoring.summary.running_jobs)}</StatusPill>
            </div>
            <div className="list-row">
              <span>排队中</span>
              <StatusPill tone="neutral">{String(monitoring.summary.queued_jobs)}</StatusPill>
            </div>
            <div className="list-row">
              <span>失败 / 可恢复</span>
              <StatusPill tone="danger">
                {String(monitoring.summary.failed_jobs + monitoring.summary.resumable_jobs)}
              </StatusPill>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="路由统计" eyebrow="Provider Routing">
          <div className="stack-list">
            <div className="list-row">
              <span>已记录节点</span>
              <StatusPill tone="neutral">{String(routedSteps)}</StatusPill>
            </div>
            <div className="list-row">
              <span>直接命中</span>
              <StatusPill tone="success">{String(directHits)}</StatusPill>
            </div>
            <div className="list-row">
              <span>回退成功</span>
              <StatusPill tone="warning">{String(fallbackHits)}</StatusPill>
            </div>
            <div className="list-row">
              <span>最终失败</span>
              <StatusPill tone="danger">{String(terminalFailures)}</StatusPill>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="告警状态" eyebrow="Alerts">
          <div className="stack-list">
            <div className="list-row">
              <span>活跃告警</span>
              <StatusPill
                tone={monitoring.summary.active_alerts > 0 ? "danger" : "success"}
              >
                {String(monitoring.summary.active_alerts)}
              </StatusPill>
            </div>
            <div data-testid="monitoring-alert-count" hidden>
              {String(monitoring.summary.active_alerts)}
            </div>
            <div className="list-row">
              <span>健康 worker</span>
              <StatusPill tone="success">{String(monitoring.summary.healthy_workers)}</StatusPill>
            </div>
            <div className="list-row">
              <span>陈旧 worker</span>
              <StatusPill tone={monitoring.summary.stale_workers > 0 ? "warning" : "success"}>
                {String(monitoring.summary.stale_workers)}
              </StatusPill>
            </div>
            {monitoring.items.slice(0, 3).map((item) => (
              <div className="list-row" key={item.provider_key}>
                <span>{item.provider_key}</span>
                <StatusPill tone={toneForStatus(item.alert_status)}>
                  {item.alert_status}
                </StatusPill>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="two-column-grid">
        <SectionCard title="活跃告警" eyebrow="Budget & Risk">
          <div className="stack-list">
            {monitoring.alerts.length > 0 ? (
              monitoring.alerts.slice(0, 6).map((alert) => (
                <article className="review-card" key={alert.id}>
                  <div className="asset-card-header">
                    <strong>{alert.scope_key}</strong>
                    <StatusPill tone={toneForStatus(alert.severity)}>{alert.severity}</StatusPill>
                  </div>
                  <p>{alert.title}</p>
                  <p className="muted-copy">{alert.message}</p>
                </article>
              ))
            ) : (
              <p className="muted-copy">当前没有活跃预算告警。</p>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Worker 健康" eyebrow="Queue Health">
          <div className="stack-list">
            {monitoring.workers.length > 0 ? (
              monitoring.workers.map((worker) => (
                <article className="review-card" key={worker.worker_id}>
                  <div className="asset-card-header">
                    <strong>{worker.worker_id}</strong>
                    <StatusPill tone={toneForStatus(worker.health_status)}>{worker.health_status}</StatusPill>
                  </div>
                  <p>{`${worker.worker_type} · ${worker.status}`}</p>
                  <p className="muted-copy">
                    {`last seen ${String(worker.seconds_since_seen)}s ago`}
                    {worker.last_job_id ? ` · job #${String(worker.last_job_id)}` : ""}
                  </p>
                </article>
              ))
            ) : (
              <p className="muted-copy">当前还没有 worker 心跳记录。</p>
            )}
          </div>
        </SectionCard>
      </div>

      <div className="two-column-grid">
        <SectionCard title="最近路由路径" eyebrow="Routing History">
          <div className="routing-event-list">
            {routingEvents.length > 0 ? (
              routingEvents.slice(0, 6).map((event) => (
                <article className="routing-event" key={event.id}>
                  <div className="routing-event-header">
                    <div className="routing-event-title">
                      <strong>{`${renderChapterLabel(event.chapterId)} / ${event.stepName}`}</strong>
                      <p>{`Job #${event.jobId} · 节点 ${event.stepKey}`}</p>
                    </div>
                    <StatusPill tone={toneForStatus(event.finalStatus)}>
                      {event.resolvedProviderKey ?? "unresolved"}
                    </StatusPill>
                  </div>
                  <div className="routing-path">
                    {event.attempts.map((attempt, index) => (
                      <div className="routing-attempt-group" key={`${event.id}-${attempt.provider_key}-${index}`}>
                        <div className="routing-attempt">
                          <code>{attempt.provider_key}</code>
                          <StatusPill tone={toneForStatus(attempt.status)}>
                            {renderAttemptStatus(attempt.status)}
                          </StatusPill>
                        </div>
                        {index < event.attempts.length - 1 ? <span className="routing-arrow">→</span> : null}
                      </div>
                    ))}
                  </div>
                  <div className="routing-event-footer">
                    <span className="muted-copy">{`候选链：${event.candidates.join(" -> ") || "未记录"}`}</span>
                    {event.errorMessage ? <span className="muted-copy">{`错误：${event.errorMessage}`}</span> : null}
                  </div>
                </article>
              ))
            ) : (
              <p className="muted-copy">当前还没有可展示的模型路由记录。</p>
            )}
          </div>
        </SectionCard>

        <SectionCard title="工作流模板" eyebrow="Workflow">
          <div className="stack-list">
            {workflows.map((workflow) => (
              <div className="list-row" key={workflow.id}>
                <span>{workflow.name}</span>
                <StatusPill tone="neutral">{`${workflow.spec.nodes.length} 节点`}</StatusPill>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="回退与失败" eyebrow="Fallback Log">
        <div className="routing-event-list">
          {fallbackEvents.length > 0 ? (
            fallbackEvents.slice(0, 8).map((event) => (
              <article className="routing-event compact" key={`${event.id}-fallback`}>
                <div className="routing-event-header">
                  <div className="routing-event-title">
                    <strong>{`${renderChapterLabel(event.chapterId)} / ${event.stepName}`}</strong>
                    <p>{`最终命中：${event.resolvedProviderKey ?? "未命中"}`}</p>
                  </div>
                  <StatusPill tone={toneForStatus(event.finalStatus)}>{event.finalStatus}</StatusPill>
                </div>
                <div className="routing-failure-list">
                  {event.attempts.map((attempt) => (
                    <div className="list-row" key={`${event.id}-${attempt.provider_key}-${attempt.status}`}>
                      <span>{attempt.provider_key}</span>
                      <span className="routing-inline-meta">
                        <StatusPill tone={toneForStatus(attempt.status)}>{renderAttemptStatus(attempt.status)}</StatusPill>
                        {attempt.error_message ? <span className="muted-copy">{attempt.error_message}</span> : null}
                      </span>
                    </div>
                  ))}
                </div>
              </article>
            ))
          ) : (
            <p className="muted-copy">当前没有需要关注的回退或失败记录。</p>
          )}
        </div>
      </SectionCard>

      <SectionCard title="模型消耗明细" eyebrow="Provider Usage">
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Type</th>
                <th>Mode</th>
                <th>Consumed</th>
                <th>Threshold</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {monitoring.items.map((item) => (
                <tr key={item.provider_key}>
                  <td>{item.provider_key}</td>
                  <td>{item.provider_type}</td>
                  <td>{item.routing_mode}</td>
                  <td>
                    {item.consumed} {item.usage_unit}
                  </td>
                  <td>{item.budget_threshold}</td>
                  <td>
                    <StatusPill tone={toneForStatus(item.alert_status)}>
                      {item.alert_status}
                    </StatusPill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
