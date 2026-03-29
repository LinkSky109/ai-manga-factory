import json

from backend.schemas import ArtifactPreview, CapabilityDescriptor, CapabilityField, WorkflowStep
from modules.base import CapabilityModule, ExecutionContext, ExecutionResult, PlannedJob


class FinanceCapability(CapabilityModule):
    descriptor = CapabilityDescriptor(
        id="finance",
        name="财经分析",
        description="规划并执行结构化财经分析任务。",
        category="analysis",
        outputs=["摘要", "报告", "图表", "风险提示"],
        input_fields=[
            CapabilityField(
                key="target",
                label="分析对象",
                description="股票、公司、行业或宏观主题。",
            ),
            CapabilityField(
                key="time_range",
                label="时间范围",
                description="例如：最近 7 天、最近一个季度。",
            ),
            CapabilityField(
                key="analysis_goal",
                label="分析目标",
                description="例如：事件驱动分析、财报解读。",
            ),
            CapabilityField(
                key="audience",
                label="受众",
                required=False,
                description="例如：投资人、研究员、运营团队。",
            ),
        ],
    )

    def plan_job(self, payload: dict) -> PlannedJob:
        target = payload.get("target", "未命名对象")
        time_range = payload.get("time_range", "最近阶段")
        analysis_goal = payload.get("analysis_goal", "常规分析")
        audience = payload.get("audience", "决策团队")

        workflow = [
            WorkflowStep(
                key="collect_market_data",
                title="采集数据",
                description=f"收集 {target} 在 {time_range} 内的市场、新闻和公开信号。",
            ),
            WorkflowStep(
                key="normalize_signals",
                title="信号整理",
                description="把原始信息整理成可比较的财经信号。",
            ),
            WorkflowStep(
                key="llm_analysis",
                title="智能分析",
                description=f"围绕“{analysis_goal}”生成分析结论。",
            ),
            WorkflowStep(
                key="report_packaging",
                title="报告封装",
                description=f"为 {audience} 生成摘要、报告和风险提示。",
            ),
        ]

        artifacts = [
            ArtifactPreview(artifact_type="markdown", label="摘要", path_hint="summary.md"),
            ArtifactPreview(artifact_type="markdown", label="完整报告", path_hint="report.md"),
            ArtifactPreview(artifact_type="json", label="结构化结果", path_hint="result.json"),
        ]

        summary = f"已规划 {target} 在 {time_range} 内的财经分析任务。"
        return PlannedJob(workflow=workflow, artifacts=artifacts, summary=summary)

    def execute_job(self, payload: dict, context: ExecutionContext) -> ExecutionResult:
        plan = self.plan_job(payload)
        job_dir = context.job_dir
        job_dir.mkdir(parents=True, exist_ok=True)

        target = payload.get("target", "未命名对象")
        time_range = payload.get("time_range", "最近阶段")
        analysis_goal = payload.get("analysis_goal", "常规分析")
        audience = payload.get("audience", "决策团队")

        summary_path = job_dir / "summary.md"
        report_path = job_dir / "report.md"
        result_path = job_dir / "result.json"

        summary_path.write_text(
            "\n".join(
                [
                    f"# 分析摘要：{target}",
                    "",
                    f"- 时间范围：{time_range}",
                    f"- 分析目标：{analysis_goal}",
                    f"- 受众：{audience}",
                    "- 输出类型：平台占位分析包。",
                ]
            ),
            encoding="utf-8",
        )

        report_path.write_text(
            "\n".join(
                [
                    f"# 财经分析报告：{target}",
                    "",
                    "## 核心观点",
                    f"当前报告模板聚焦于“{analysis_goal}”。",
                    "",
                    "## 信号检查清单",
                    "- 价格走势",
                    "- 新闻流",
                    "- 估值背景",
                    "- 风险提示",
                    "",
                    "## 运行说明",
                    "当前内容仍是平台执行脚手架，后续会在这里接入真实市场数据连接器与模型分析输出。",
                ]
            ),
            encoding="utf-8",
        )

        result_path.write_text(
            json.dumps(
                {
                    "job_id": context.job_id,
                    "project_id": context.project_id,
                    "target": target,
                    "time_range": time_range,
                    "analysis_goal": analysis_goal,
                    "audience": audience,
                    "status": "completed",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        artifacts = [
            ArtifactPreview(artifact_type="markdown", label="摘要", path_hint="summary.md"),
            ArtifactPreview(artifact_type="markdown", label="完整报告", path_hint="report.md"),
            ArtifactPreview(artifact_type="json", label="结构化结果", path_hint="result.json"),
        ]

        summary = f"已完成 {target} 的财经分析脚手架，并输出本地报告产物。"
        return ExecutionResult(workflow=plan.workflow, artifacts=artifacts, summary=summary)
