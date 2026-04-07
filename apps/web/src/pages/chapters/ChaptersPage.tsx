import { useDeferredValue, useState } from "react";

import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import type { ChapterDetail } from "../../types/api";

interface ChaptersPageProps {
  chapters: ChapterDetail[];
}

export function ChaptersPage({ chapters }: ChaptersPageProps) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();
  const visibleChapters = chapters.filter((chapter) => {
    if (!normalizedQuery) {
      return true;
    }
    return `${chapter.chapter_number} ${chapter.title} ${chapter.summary ?? ""}`.toLowerCase().includes(normalizedQuery);
  });

  return (
    <div className="page-stack">
      <SectionCard
        title="章节推进面板"
        eyebrow="Chapter Pipeline"
        actions={
          <input
            className="search-input"
            placeholder="搜索章节、摘要或章节号"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        }
      >
        <div className="chapter-grid">
          {visibleChapters.map((chapter) => (
            <article className="chapter-card" key={chapter.id}>
              <div className="chapter-card-top">
                <div>
                  <span className="chapter-number">Chapter {chapter.chapter_number}</span>
                  <h3>{chapter.title}</h3>
                </div>
                <StatusPill tone={chapter.status === "completed" ? "success" : chapter.status === "failed" ? "danger" : "warning"}>
                  {chapter.status}
                </StatusPill>
              </div>
              <p>{chapter.summary ?? "当前章节暂无摘要。"}</p>
              <div className="pipeline-row">
                {chapter.pipeline_states.map((state) => (
                  <div className="pipeline-chip" key={state.id}>
                    <span>{state.stage_key}</span>
                    <StatusPill tone={state.status === "completed" ? "success" : state.status === "failed" ? "danger" : "neutral"}>
                      {state.status}
                    </StatusPill>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
