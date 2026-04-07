import { startTransition, useEffect, useState } from "react";

import { SectionCard } from "../components/stitch/SectionCard";
import { StatusPill } from "../components/stitch/StatusPill";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { type AppView, useHashRoute } from "../hooks/useHashRoute";
import { api } from "../lib/api";
import { AssetsPage } from "../pages/assets/AssetsPage";
import { WorkflowEditorPage } from "../pages/workflow-editor/WorkflowEditorPage";
import { DashboardPage } from "../pages/dashboard/DashboardPage";
import { MonitoringPage } from "../pages/monitoring/MonitoringPage";
import { PreviewPage } from "../pages/preview/PreviewPage";
import { PromptEvolutionPage } from "../pages/prompt-evolution/PromptEvolutionPage";
import { SettingsPage } from "../pages/settings/SettingsPage";
import { ChaptersPage } from "../pages/chapters/ChaptersPage";
import { sampleProjects } from "../features/project-overview/sampleData";
import { useProjectWorkspace } from "../features/project-overview/useProjectWorkspace";

const NAV_ITEMS: Array<{ key: AppView; label: string; caption: string }> = [
  { key: "overview", label: "项目总览", caption: "Control Tower" },
  { key: "chapters", label: "章节推进", caption: "Chapter Pipeline" },
  { key: "assets", label: "资产库", caption: "Asset Consistency" },
  { key: "workflow", label: "流程编排", caption: "Workflow Editor" },
  { key: "evolution", label: "提示词进化", caption: "Prompt Evolution" },
  { key: "monitoring", label: "监控台", caption: "Provider Usage" },
  { key: "preview", label: "预览流", caption: "Preview Queue" },
  { key: "settings", label: "设置中心", caption: "Security & Config" },
];

export function App() {
  const { view, navigate } = useHashRoute();
  const projects = useAsyncResource(() => api.listProjects(), []);
  const hasLiveProjects = Boolean(projects.data && projects.data.length > 0);
  const availableProjects = hasLiveProjects ? projects.data ?? [] : sampleProjects;
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);

  useEffect(() => {
    if (selectedProjectId !== null) {
      return;
    }
    if (availableProjects.length > 0) {
      setSelectedProjectId(availableProjects[0].id);
    }
  }, [availableProjects, selectedProjectId]);

  const workspace = useProjectWorkspace(selectedProjectId);

  const renderView = () => {
    switch (view) {
      case "chapters":
        return <ChaptersPage chapters={workspace.data.chapters} />;
      case "assets":
        return (
          <AssetsPage
            characters={workspace.data.characters}
            scenes={workspace.data.scenes}
            voices={workspace.data.voices}
          />
        );
      case "workflow":
        return (
          <WorkflowEditorPage
            workflows={workspace.data.workflows}
            reviewTasks={workspace.data.reviewTasks}
            sharedMemories={workspace.data.sharedMemories}
            sampleMode={workspace.isSampleMode}
            onSaved={workspace.reload}
          />
        );
      case "evolution":
        return (
          <PromptEvolutionPage
            templates={workspace.data.promptTemplates}
            feedback={workspace.data.promptFeedback}
          />
        );
      case "monitoring":
        return (
          <MonitoringPage
            monitoring={workspace.data.monitoring}
            jobs={workspace.data.jobs}
            workflows={workspace.data.workflows}
          />
        );
      case "preview":
        return (
          <PreviewPage
            previews={workspace.data.previews}
            artifacts={workspace.data.artifacts}
            storageTargets={workspace.data.storageTargets}
          />
        );
      case "settings":
        return (
          <SettingsPage
            authSession={workspace.data.authSession}
            settingsOverview={workspace.data.settingsOverview}
            auditLogs={workspace.data.auditLogs}
            sampleMode={workspace.isSampleMode}
            onReload={workspace.reload}
          />
        );
      case "overview":
      default:
        return (
          <DashboardPage
            overview={workspace.data.overview}
            jobs={workspace.data.jobs}
            initialization={workspace.data.projectInitialization}
            sampleMode={workspace.isSampleMode}
          />
        );
    }
  };

  return (
    <main className="app-shell">
      <aside className="nav-rail">
        <div className="brand-block">
          <p className="eyebrow">Google Stitch Inspired</p>
          <h1>AI 漫剧工厂</h1>
          <p>项目制资产与生产控制塔</p>
        </div>

        <nav className="nav-stack">
          {NAV_ITEMS.map((item) => (
            <button
              className={item.key === view ? "nav-item active" : "nav-item"}
              key={item.key}
              data-testid={`nav-${item.key}`}
              onClick={() => navigate(item.key)}
              type="button"
            >
              <strong>{item.label}</strong>
              <span>{item.caption}</span>
            </button>
          ))}
        </nav>

        <SectionCard title="运行模式" eyebrow="Workspace Mode">
          <div className="stack-list">
            <div className="list-row">
              <span>项目源</span>
              <StatusPill tone={hasLiveProjects ? "success" : "warning"}>
                {hasLiveProjects ? "live" : "sample"}
              </StatusPill>
            </div>
            <div data-testid="workspace-mode" hidden>
              {hasLiveProjects ? "live" : "sample"}
            </div>
            <div className="list-row">
              <span>数据状态</span>
              <StatusPill tone={workspace.isLoading ? "warning" : "success"}>
                {workspace.isLoading ? "loading" : "ready"}
              </StatusPill>
            </div>
            <div className="list-row">
              <span>提示词版本</span>
              <StatusPill tone="neutral">{String(workspace.data.promptTemplates.length)}</StatusPill>
            </div>
          </div>
        </SectionCard>
      </aside>

      <section className="content-shell">
        <header className="top-bar">
          <div>
            <p className="eyebrow">Phase 9</p>
            <h2>项目总览 / 章节推进 / 资产库 / 编排 / 进化 / 监控 / 预览 / 设置</h2>
          </div>
          <div className="toolbar">
            <select
              className="project-select"
              value={selectedProjectId ?? ""}
              onChange={(event) => {
                startTransition(() => {
                  setSelectedProjectId(Number(event.target.value));
                });
              }}
            >
              {availableProjects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <button className="refresh-button" onClick={() => workspace.reload()} type="button">
              刷新数据
            </button>
          </div>
        </header>

        {projects.error ? (
          <div className="notice-banner warning">
            项目列表读取失败，已切换到示例模式。错误：{projects.error}
          </div>
        ) : null}

        {workspace.error ? (
          <div className="notice-banner warning">
            工作区数据读取失败，当前展示的是示例控制塔。错误：{workspace.error}
          </div>
        ) : null}

        {renderView()}
      </section>
    </main>
  );
}
