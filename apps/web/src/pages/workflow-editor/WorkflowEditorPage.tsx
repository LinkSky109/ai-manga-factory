import { useEffect, useMemo, useState } from "react";

import { SectionCard } from "../../components/stitch/SectionCard";
import { StatusPill } from "../../components/stitch/StatusPill";
import { api } from "../../lib/api";
import type { ReviewTask, SharedMemory, WorkflowDefinition, WorkflowNode } from "../../types/api";

interface WorkflowEditorPageProps {
  workflows: WorkflowDefinition[];
  reviewTasks: ReviewTask[];
  sharedMemories: SharedMemory[];
  sampleMode: boolean;
  onSaved: () => void;
}

function reorderNodes(nodes: WorkflowNode[], fromIndex: number, toIndex: number): WorkflowNode[] {
  const nextNodes = [...nodes];
  const [movedNode] = nextNodes.splice(fromIndex, 1);
  nextNodes.splice(toIndex, 0, movedNode);
  return nextNodes;
}

function buildLinearEdges(nodes: WorkflowNode[]) {
  return nodes.slice(0, -1).map((node, index) => ({
    source: node.key,
    target: nodes[index + 1].key,
  }));
}

export function WorkflowEditorPage({
  workflows,
  reviewTasks,
  sharedMemories,
  sampleMode,
  onSaved,
}: WorkflowEditorPageProps) {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<number | null>(workflows[0]?.id ?? null);
  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? workflows[0] ?? null,
    [selectedWorkflowId, workflows],
  );
  const [draftNodes, setDraftNodes] = useState<WorkflowNode[]>(selectedWorkflow?.spec.nodes ?? []);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [saveStatus, setSaveStatus] = useState<string>("idle");

  const parseReviewPayload = (task: ReviewTask) => {
    const payload = task.result_payload ?? {};
    const findings = Array.isArray(payload.findings)
      ? payload.findings.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      : [];
    const executionTrace =
      payload.execution_trace && typeof payload.execution_trace === "object"
        ? (payload.execution_trace as Record<string, unknown>)
        : null;
    return {
      blockingStatus: typeof payload.blocking_status === "string" ? payload.blocking_status : "pending",
      findings,
      resolvedProvider:
        executionTrace && typeof executionTrace.resolved_provider_key === "string"
          ? executionTrace.resolved_provider_key
          : "n/a",
    };
  };

  useEffect(() => {
    setDraftNodes(selectedWorkflow?.spec.nodes ?? []);
    setSaveStatus("idle");
  }, [selectedWorkflow]);

  const saveDraft = async () => {
    if (!selectedWorkflow) {
      return;
    }
    setSaveStatus("saving");

    if (sampleMode) {
      window.setTimeout(() => {
        setSaveStatus("sample");
      }, 150);
      return;
    }

    try {
      await api.updateWorkflow(selectedWorkflow.id, {
        name: selectedWorkflow.name,
        description: selectedWorkflow.description,
        routing_mode: selectedWorkflow.routing_mode,
        nodes: draftNodes,
        edges: buildLinearEdges(draftNodes),
      });
      setSaveStatus("saved");
      onSaved();
    } catch (error) {
      setSaveStatus(error instanceof Error ? error.message : "保存失败");
    }
  };

  return (
    <div className="page-stack">
      <SectionCard
        title="节点化工作流编排"
        eyebrow="Workflow Editor"
        actions={
          <div className="toolbar">
            <select
              className="project-select"
              value={selectedWorkflow?.id ?? ""}
              onChange={(event) => setSelectedWorkflowId(Number(event.target.value))}
            >
              {workflows.map((workflow) => (
                <option key={workflow.id} value={workflow.id}>
                  {workflow.name}
                </option>
              ))}
            </select>
            <button className="refresh-button" onClick={() => void saveDraft()} type="button">
              保存顺序
            </button>
          </div>
        }
      >
        <div className="editor-grid">
          <div className="editor-lane">
            {draftNodes.map((node, index) => (
              <article
                className="workflow-node-card"
                draggable
                key={node.key}
                onDragStart={() => setDragIndex(index)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (dragIndex === null || dragIndex === index) {
                    return;
                  }
                  setDraftNodes((current) => reorderNodes(current, dragIndex, index));
                  setDragIndex(null);
                  setSaveStatus("dirty");
                }}
              >
                <div className="asset-card-header">
                  <strong>{node.title}</strong>
                  <StatusPill tone="neutral">{node.provider_type}</StatusPill>
                </div>
                <p>节点键：{node.key}</p>
                <p>支持断点续跑：{node.checkpointable ? "是" : "否"}</p>
              </article>
            ))}
          </div>

          <div className="editor-side">
            <SectionCard title="保存状态" eyebrow="State">
              <div className="stack-list">
                <div className="list-row">
                  <span>工作流模式</span>
                  <StatusPill tone="neutral">{selectedWorkflow?.routing_mode ?? "n/a"}</StatusPill>
                </div>
                <div className="list-row">
                  <span>当前保存状态</span>
                  <StatusPill tone={saveStatus === "saved" ? "success" : saveStatus === "dirty" ? "warning" : "neutral"}>
                    {saveStatus}
                  </StatusPill>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="审核任务" eyebrow="Review Queue">
              <div className="stack-list">
                {reviewTasks.map((task) => (
                  (() => {
                    const parsed = parseReviewPayload(task);
                    return (
                      <article className="review-card" key={task.id}>
                        <div className="asset-card-header">
                          <strong>{task.review_stage}</strong>
                          <StatusPill tone={task.status === "completed" ? "success" : task.status === "failed" ? "danger" : "warning"}>
                            {task.status}
                          </StatusPill>
                        </div>
                        <div className="list-row">
                          <span>阻塞状态</span>
                          <StatusPill
                            tone={
                              parsed.blockingStatus === "pass"
                                ? "success"
                                : parsed.blockingStatus === "blocked"
                                  ? "danger"
                                  : "warning"
                            }
                          >
                            {parsed.blockingStatus}
                          </StatusPill>
                        </div>
                        <div className="list-row">
                          <span>命中 Provider</span>
                          <StatusPill tone="neutral">{parsed.resolvedProvider}</StatusPill>
                        </div>
                        <p>{task.findings_summary ?? "暂无摘要"}</p>
                        {parsed.findings.slice(0, 2).map((finding, index) => (
                          <div className="prompt-diff-box" key={`${task.id}-${index}`}>
                            <strong>{typeof finding.title === "string" ? finding.title : "审核发现"}</strong>
                            <p>{typeof finding.summary === "string" ? finding.summary : "暂无说明"}</p>
                            <p>{typeof finding.recommendation === "string" ? finding.recommendation : "暂无建议"}</p>
                          </div>
                        ))}
                        <div className="tag-row">
                          {task.assigned_agents.map((agent) => (
                            <StatusPill key={agent} tone="neutral">
                              {agent}
                            </StatusPill>
                          ))}
                        </div>
                      </article>
                    );
                  })()
                ))}
              </div>
            </SectionCard>

            <SectionCard title="共享记忆库" eyebrow="Shared Memory">
              <div className="stack-list">
                {sharedMemories.map((memory) => (
                  <article className="memory-card" key={memory.id}>
                    <div className="asset-card-header">
                      <strong>{memory.scope_key}</strong>
                      <StatusPill tone="neutral">{memory.memory_type}</StatusPill>
                    </div>
                    <p>{JSON.stringify(memory.content)}</p>
                  </article>
                ))}
              </div>
            </SectionCard>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
