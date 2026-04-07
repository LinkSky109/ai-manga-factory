import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import type { PromptFeedback, PromptTemplateSummary } from "../../types/api";

interface PromptEvolutionPageProps {
  templates: PromptTemplateSummary[];
  feedback: PromptFeedback[];
}

export function PromptEvolutionPage({ templates, feedback }: PromptEvolutionPageProps) {
  return (
    <div className="page-stack">
      <SectionCard title="提示词进化总览" eyebrow="Prompt Evolution">
        <div className="asset-layout">
          <div className="asset-column">
            <h3>模板版本</h3>
            {templates.map((template) => (
              <article className="asset-card" key={template.id}>
                <div className="asset-card-header">
                  <strong>{template.workflow_key}</strong>
                  <StatusPill tone={template.latest_score && template.latest_score >= 4 ? "success" : "warning"}>
                    {template.template_version}
                  </StatusPill>
                </div>
                <p>{template.template_body}</p>
                <div className="asset-meta-row">
                  <span>反馈次数</span>
                  <span>{template.feedback_count}</span>
                </div>
                <div className="asset-meta-row">
                  <span>最近得分</span>
                  <span>{template.latest_score ?? "n/a"}</span>
                </div>
              </article>
            ))}
          </div>

          <div className="asset-column">
            <h3>人工修正记录</h3>
            {feedback.map((item) => (
              <article className="asset-card" key={item.id}>
                <div className="asset-card-header">
                  <strong>Feedback #{item.id}</strong>
                  <StatusPill tone={item.score >= 4 ? "success" : "warning"}>{`${item.score}/5`}</StatusPill>
                </div>
                <p>{item.correction_summary}</p>
                <div className="prompt-diff-box">
                  <span>修正后提示词</span>
                  <p>{item.corrected_prompt ?? "暂无修正文本"}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
