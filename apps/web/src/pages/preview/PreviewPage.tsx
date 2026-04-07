import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import { resolveApiUrl } from "../../lib/api";
import type { ArtifactRecord, PreviewList, StorageTarget } from "../../types/api";

interface PreviewPageProps {
  previews: PreviewList;
  artifacts: ArtifactRecord[];
  storageTargets: StorageTarget[];
}

export function PreviewPage({ previews, artifacts, storageTargets }: PreviewPageProps) {
  return (
    <div className="page-stack">
      <SectionCard title="归档后端" eyebrow="Storage Targets">
        <div className="tag-row">
          {storageTargets.map((target) => (
            <div className="storage-target-pill" key={target.archive_type}>
              <div className="storage-target-pill-head">
                <strong>{target.archive_type}</strong>
                <StatusPill tone={target.is_ready ? "success" : "danger"}>
                  {target.is_ready ? "ready" : "blocked"}
                </StatusPill>
              </div>
              <span>{target.mode}</span>
              <span>{target.readiness_reason}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="即时预览队列" eyebrow="Preview Stream">
        <div className="preview-grid">
          {previews.items.map((item) => {
            const sourceUrl = item.playback_url ? resolveApiUrl(item.playback_url) : null;

            return (
              <article className="preview-card" key={item.id}>
                <div className="preview-media">
                  {sourceUrl ? (
                    item.mime_type?.startsWith("audio/") ? (
                      <audio className="preview-audio" controls preload="metadata" src={sourceUrl}>
                        Your browser does not support the audio element.
                      </audio>
                    ) : item.mime_type?.startsWith("video/") ? (
                      <video className="preview-video" controls preload="metadata" src={sourceUrl}>
                        Your browser does not support the video element.
                      </video>
                    ) : (
                      <iframe className="preview-frame" src={sourceUrl} title={item.title} loading="lazy" />
                    )
                  ) : (
                    <span>{item.media_kind.toUpperCase()}</span>
                  )}
                </div>
                <div className="preview-copy">
                  <div className="asset-card-header">
                    <strong>{item.title}</strong>
                    <StatusPill tone={item.status === "completed" ? "success" : item.status === "failed" ? "danger" : "warning"}>
                      {item.status}
                    </StatusPill>
                  </div>
                  <p>{item.playback_hint}</p>
                  <div className="preview-meta">
                    <span>Job #{item.job_id}</span>
                    <span>{item.stage_key}</span>
                    <span>{item.provider_key ?? "pending"}</span>
                  </div>
                  <div className="preview-actions">
                    <span>
                      Archive: {item.archive_status ?? "pending"}
                      {item.archive_targets?.length ? ` · ${item.archive_targets.join(", ")}` : ""}
                    </span>
                    {sourceUrl ? (
                      <a href={sourceUrl} target="_blank" rel="noreferrer">
                        打开预览
                      </a>
                    ) : null}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard title="归档清单" eyebrow="Artifact Catalog">
        <div className="stack-list">
          {artifacts.slice(0, 8).map((artifact) => {
            const latestSyncRun = artifact.sync_runs[0] ?? null;

            return (
              <article className="archive-row" key={artifact.id}>
                <div className="archive-row-copy">
                  <strong>{artifact.title}</strong>
                  <p>
                    {artifact.media_kind} · {artifact.mime_type} · {artifact.size_bytes ?? 0} bytes
                  </p>
                  {latestSyncRun ? (
                    <div className="archive-sync-meta">
                      <StatusPill
                        tone={
                          latestSyncRun.status === "completed"
                            ? "success"
                            : latestSyncRun.status === "failed"
                              ? "danger"
                              : "warning"
                        }
                      >
                        {latestSyncRun.status}
                      </StatusPill>
                      <span>{latestSyncRun.archive_type}</span>
                      <span>{latestSyncRun.summary ?? "Archive sync update available."}</span>
                    </div>
                  ) : (
                    <div className="archive-sync-meta">
                      <StatusPill tone="neutral">idle</StatusPill>
                      <span>尚未创建归档补同步任务</span>
                    </div>
                  )}
                </div>
                <div className="archive-links">
                  {artifact.archives.map((archive) => (
                    <div className="archive-link-stack" key={`${artifact.id}-${archive.id}`}>
                      <a
                        href={archive.remote_url ?? resolveApiUrl(artifact.preview_url)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {archive.archive_type}
                      </a>
                      {archive.checksum_sha256 ? (
                        <span className="archive-checksum">{archive.checksum_sha256.slice(0, 12)}...</span>
                      ) : null}
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}
