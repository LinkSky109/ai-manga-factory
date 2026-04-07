from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.domain.provider.routing import ProviderRouter
from src.infrastructure.db.models import ArtifactModel, ChapterModel, ProjectScriptModel, ProjectStorySummaryModel
from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository
from src.infrastructure.db.repositories.asset_repository import AssetRepository
from src.infrastructure.db.repositories.memory_repository import MemoryRepository
from src.infrastructure.db.repositories.project_repository import ProjectRepository
from src.infrastructure.db.repositories.prompt_repository import PromptRepository
from src.infrastructure.db.repositories.provider_repository import ProviderRepository
from src.infrastructure.db.repositories.review_repository import ReviewRepository
from src.infrastructure.providers.ark_runtime import build_ark_runtime_client


DEFAULT_REVIEW_AGENTS = {
    "script": ["logic-auditor", "continuity-keeper", "character-editor"],
    "storyboard": ["logic-auditor", "continuity-keeper", "visual-director"],
    "character": ["character-editor", "continuity-keeper"],
}


class ReviewFinding(BaseModel):
    agent: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    severity: str = Field(min_length=1, max_length=16)
    summary: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)


class ReviewMemoryCandidate(BaseModel):
    scope_type: str = Field(min_length=1, max_length=32)
    scope_key: str = Field(min_length=1, max_length=160)
    memory_type: str = Field(min_length=1, max_length=32)
    content: dict = Field(default_factory=dict)


class ReviewPromptFeedback(BaseModel):
    template_body: str = Field(min_length=1)
    score: int = Field(ge=1, le=5)
    correction_summary: str = Field(min_length=1)
    corrected_prompt: str | None = None


class ReviewExecutionResult(BaseModel):
    blocking_status: str = Field(min_length=1, max_length=16)
    severity: str = Field(min_length=1, max_length=16)
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)
    memory_candidates: list[ReviewMemoryCandidate] = Field(default_factory=list)
    prompt_feedback: ReviewPromptFeedback | None = None
    execution_trace: dict = Field(default_factory=dict)


class ReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.reviews = ReviewRepository(session)
        self.memories = MemoryRepository(session)
        self.prompts = PromptRepository(session)
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)
        self.artifacts = ArtifactRepository(session)
        self.providers = ProviderRepository(session)

    def create_review(
        self,
        *,
        project_id: int | None,
        chapter_id: int | None,
        review_stage: str,
        review_type: str,
        assigned_agents: list[str],
        checklist: list[str],
        findings_summary: str | None,
        result_payload: dict,
        auto_run: bool = True,
        routing_mode: str = "smart",
        manual_provider: str | None = None,
    ):
        resolved_agents = assigned_agents or DEFAULT_REVIEW_AGENTS.get(review_stage, ["logic-auditor"])
        review = self.reviews.create_review(
            project_id=project_id,
            chapter_id=chapter_id,
            review_stage=review_stage,
            review_type=review_type,
            assigned_agents=resolved_agents,
            checklist=checklist,
            findings_summary=findings_summary,
            result_payload=result_payload,
        )

        should_run = auto_run and review_type == "multi-agent"
        review.status = "running" if should_run else "pending"
        self.session.flush()

        if should_run:
            try:
                execution = self._execute_review(
                    review_stage=review_stage,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    assigned_agents=resolved_agents,
                    checklist=checklist,
                    routing_mode=routing_mode,
                    manual_provider=manual_provider,
                )
                review.status = "completed"
                review.findings_summary = execution.summary
                review.result_payload = execution.model_dump()
                self._sync_review_outputs(
                    review_id=review.id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    review_stage=review_stage,
                    execution=execution,
                )
            except Exception as exc:
                review.status = "failed"
                review.findings_summary = str(exc)
                review.result_payload = {
                    "blocking_status": "blocked",
                    "severity": "high",
                    "summary": str(exc),
                    "findings": [],
                    "memory_candidates": [],
                    "prompt_feedback": None,
                    "execution_trace": {
                        "generation_mode": "failed",
                        "routing_mode": routing_mode,
                        "manual_provider": manual_provider,
                        "resolved_provider_key": None,
                        "provider_candidates": [],
                        "provider_attempts": [],
                        "usage_amount": 0,
                        "usage_unit": "tokens",
                    },
                }

        self.session.commit()
        self.session.refresh(review)
        return review

    def list_reviews(self, project_id: int | None = None):
        return self.reviews.list_reviews(project_id=project_id)

    def _execute_review(
        self,
        *,
        review_stage: str,
        project_id: int | None,
        chapter_id: int | None,
        assigned_agents: list[str],
        checklist: list[str],
        routing_mode: str,
        manual_provider: str | None,
    ) -> ReviewExecutionResult:
        if project_id is None:
            raise ValueError("Project id is required for automatic review execution.")

        context = self._build_review_context(
            project_id=project_id,
            chapter_id=chapter_id,
            review_stage=review_stage,
            assigned_agents=assigned_agents,
            checklist=checklist,
        )
        provider_snapshots = self.providers.list_provider_snapshots()
        router = ProviderRouter(provider_snapshots)
        try:
            decision = router.resolve(provider_type="llm", routing_mode=routing_mode, manual_provider=manual_provider)
        except LookupError as exc:
            raise ValueError(str(exc)) from exc

        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None
        for provider_key in decision.candidates:
            try:
                if provider_key == "ark-story":
                    execution = self._run_model_review(context=context, provider_key=provider_key)
                    generation_mode = "model"
                elif provider_key == "llm-story":
                    execution = self._run_local_review(context=context)
                    generation_mode = "deterministic-fallback"
                else:
                    raise RuntimeError(f"Unsupported review provider '{provider_key}'.")

                usage_amount = self._estimate_usage_amount(context=context, execution=execution)
                self.providers.log_usage(
                    provider_key=provider_key,
                    provider_type="llm",
                    project_id=project_id,
                    job_run_id=None,
                    metric_name="review_generation",
                    usage_amount=usage_amount,
                    usage_unit="tokens",
                )
                attempts.append({"provider_key": provider_key, "status": "completed", "error_message": None})
                execution.execution_trace = {
                    "generation_mode": generation_mode,
                    "routing_mode": "manual" if manual_provider else routing_mode,
                    "manual_provider": manual_provider,
                    "resolved_provider_key": provider_key,
                    "provider_candidates": list(decision.candidates),
                    "provider_attempts": attempts,
                    "usage_amount": usage_amount,
                    "usage_unit": "tokens",
                }
                return execution
            except Exception as exc:
                last_error = exc
                attempts.append({"provider_key": provider_key, "status": "failed", "error_message": str(exc)})

        if last_error is not None:
            raise RuntimeError(f"Review execution failed: {last_error}") from last_error
        raise RuntimeError("Review execution failed: no provider candidates available.")

    def _build_review_context(
        self,
        *,
        project_id: int,
        chapter_id: int | None,
        review_stage: str,
        assigned_agents: list[str],
        checklist: list[str],
    ) -> dict:
        project = self.projects.get_project(project_id)
        if project is None:
            raise LookupError("Project not found.")

        chapter: ChapterModel | None = self.session.get(ChapterModel, chapter_id) if chapter_id is not None else None
        summary: ProjectStorySummaryModel | None = self.projects.get_latest_story_summary(project_id)
        script: ProjectScriptModel | None = self.projects.get_latest_script(project_id)
        characters = self.assets.list_characters(project_id)
        scenes = self.assets.list_scenes(project_id)
        memories = self.memories.list_memories(project_id=project_id)
        artifacts = self.artifacts.list_project_artifacts(project_id)
        storyboard_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.step_key == "storyboard" and (chapter_id is None or artifact.chapter_id == chapter_id)
        ]
        latest_storyboard = storyboard_artifacts[0] if storyboard_artifacts else None

        review_body = self._resolve_review_body(
            review_stage=review_stage,
            chapter=chapter,
            script=script,
            latest_storyboard=latest_storyboard,
        )
        return {
            "project_id": project_id,
            "project_name": project.name,
            "review_stage": review_stage,
            "chapter_id": chapter_id,
            "chapter_title": chapter.title if chapter else None,
            "chapter_summary": chapter.summary if chapter else None,
            "review_body": review_body,
            "script_title": script.title if script else None,
            "summary_body": summary.summary_body if summary else None,
            "characters": [character.name for character in characters],
            "scenes": [scene.name for scene in scenes],
            "memories": [
                {
                    "scope_key": memory.scope_key,
                    "memory_type": memory.memory_type,
                    "content": memory.content,
                }
                for memory in memories[:8]
            ],
            "storyboard_hint": None if latest_storyboard is None else latest_storyboard.artifact_metadata.get("playback_hint"),
            "assigned_agents": assigned_agents,
            "checklist": checklist,
        }

    def _run_model_review(self, *, context: dict, provider_key: str) -> ReviewExecutionResult:
        client = build_ark_runtime_client(self.settings)
        raw_output = client.generate_text(
            prompt=self._build_model_prompt(context),
            system_prompt="你是 AI 漫剧工厂的审核导演组。请只输出合法 JSON，不要输出 markdown 或解释。",
            model=self.settings.ark_text_model,
            temperature=0.2,
            max_tokens=2200,
        )
        execution = self._parse_model_review(raw_output)
        return self._normalize_execution_result(context=context, execution=execution, provider_key=provider_key)

    def _run_local_review(self, *, context: dict) -> ReviewExecutionResult:
        review_body = str(context.get("review_body") or "").strip()
        characters = list(context.get("characters") or [])
        scenes = list(context.get("scenes") or [])
        memories = list(context.get("memories") or [])
        findings: list[dict] = []

        if not review_body:
            findings.append(
                {
                    "agent": "logic-auditor",
                    "title": "审核材料缺失",
                    "severity": "high",
                    "summary": "当前阶段缺少可审核的正文或产物摘要。",
                    "recommendation": "先生成对应阶段内容，再重新发起审核。",
                }
            )
        else:
            if len(review_body) < 140 or ("因为" not in review_body and "因此" not in review_body):
                findings.append(
                    {
                        "agent": "logic-auditor",
                        "title": "转场动机还不够具体",
                        "severity": "medium",
                        "summary": "当前文本已建立事件，但角色为何进入下一段动作的触发原因还可以再压实。",
                        "recommendation": "补一条角色即时动机或外部刺激，让剧情推进更顺。",
                    }
                )
            if characters and not any(name in review_body for name in characters[:3]):
                findings.append(
                    {
                        "agent": "character-editor",
                        "title": "角色锚点不够稳定",
                        "severity": "medium",
                        "summary": "审核文本没有清晰点名核心角色，后续镜头和配音容易漂移。",
                        "recommendation": "至少明确 1-2 个角色名字和对应动作，稳定角色焦点。",
                    }
                )
            if scenes and not any(scene in review_body for scene in scenes[:2]):
                findings.append(
                    {
                        "agent": "continuity-keeper",
                        "title": "空间连续性信号偏弱",
                        "severity": "low",
                        "summary": "文本没有稳定引用主场景，后续镜头转场可能缺少空间锚点。",
                        "recommendation": "补充场景名称、入口方位或主光源，稳住空间连续性。",
                    }
                )
            if memories and not findings:
                findings.append(
                    {
                        "agent": "continuity-keeper",
                        "title": "共享记忆建议已纳入",
                        "severity": "low",
                        "summary": "当前文本整体可用，但建议继续对照共享记忆核验服装、站位与场景朝向。",
                        "recommendation": "在分镜或剧本里显式引用 1 条关键连续性规则。",
                    }
                )

        if not findings:
            findings.append(
                {
                    "agent": "logic-auditor",
                    "title": "建议补一条镜头意图提示",
                    "severity": "low",
                    "summary": "当前内容基本通过，但为了后续生成稳定，建议显式写出镜头目标。",
                    "recommendation": "给这一段补一条镜头目标或情绪目标，减少后续生成漂移。",
                }
            )

        severity_order = {"high": 3, "medium": 2, "low": 1}
        highest = max(findings, key=lambda item: severity_order.get(str(item["severity"]), 0))
        blocking_status = "blocked" if highest["severity"] == "high" else "warning"
        summary = "；".join(item["summary"] for item in findings[:2])
        memory_candidates = [
            {
                "scope_type": "chapter" if context.get("chapter_id") is not None else "project",
                "scope_key": f"review:{context['review_stage']}:chapter:{context.get('chapter_id') or 'project'}:{item['agent']}",
                "memory_type": "review_guideline",
                "content": {
                    "rule": item["recommendation"],
                    "owner": item["agent"],
                    "severity": item["severity"],
                },
            }
            for item in findings[:3]
        ]
        recommendations = "；".join(item["recommendation"] for item in findings[:2])
        return ReviewExecutionResult.model_validate(
            {
                "blocking_status": blocking_status,
                "severity": highest["severity"],
                "summary": summary,
                "findings": findings,
                "memory_candidates": memory_candidates,
                "prompt_feedback": {
                    "template_body": f"生成 {context['review_stage']} 内容时，必须明确角色、场景连续性和剧情推进动机。",
                    "score": 3 if blocking_status == "warning" else 2 if blocking_status == "blocked" else 5,
                    "correction_summary": summary,
                    "corrected_prompt": f"生成 {context['review_stage']} 内容时，必须明确角色、场景连续性和剧情推进动机。{recommendations}",
                },
                "execution_trace": {},
            }
        )

    def _sync_review_outputs(
        self,
        *,
        review_id: int,
        project_id: int | None,
        chapter_id: int | None,
        review_stage: str,
        execution: ReviewExecutionResult,
    ) -> None:
        for item in execution.memory_candidates:
            self.memories.upsert_memory(
                project_id=project_id,
                scope_type=item.scope_type,
                scope_key=item.scope_key,
                memory_type=item.memory_type,
                content={
                    **item.content,
                    "review_id": review_id,
                    "chapter_id": chapter_id,
                    "review_stage": review_stage,
                },
            )

        if execution.prompt_feedback is not None:
            template = self.prompts.find_or_create_template(
                project_id=project_id,
                workflow_key=f"{review_stage}-review",
                template_version="auto-v1",
                template_body=execution.prompt_feedback.template_body,
            )
            self.prompts.create_feedback(
                prompt_template_id=template.id,
                job_run_id=None,
                score=execution.prompt_feedback.score,
                correction_summary=execution.prompt_feedback.correction_summary,
                corrected_prompt=execution.prompt_feedback.corrected_prompt,
            )
        self.session.flush()

    def _resolve_review_body(
        self,
        *,
        review_stage: str,
        chapter: ChapterModel | None,
        script: ProjectScriptModel | None,
        latest_storyboard: ArtifactModel | None,
    ) -> str:
        if review_stage == "storyboard":
            if latest_storyboard is None:
                return ""
            hint = str(latest_storyboard.artifact_metadata.get("playback_hint") or "").strip()
            return "\n".join(
                part
                for part in [
                    latest_storyboard.title,
                    hint,
                    latest_storyboard.media_kind,
                    latest_storyboard.provider_key or "",
                ]
                if part
            )

        if script is not None:
            body = script.script_body
            if chapter is None:
                return body
            section = self._extract_script_section(body=body, chapter_title=chapter.title)
            if section:
                return section
        return chapter.summary or "" if chapter is not None else ""

    @staticmethod
    def _extract_script_section(*, body: str, chapter_title: str) -> str:
        pattern = re.compile(
            rf"(^##\s+{re.escape(chapter_title)}.*?)(?=^##\s+|\Z)",
            flags=re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(body)
        return match.group(1).strip() if match else body.strip()

    @staticmethod
    def _build_model_prompt(context: dict) -> str:
        memories_text = "\n".join(
            f"- {item['scope_key']}: {json.dumps(item['content'], ensure_ascii=False)}"
            for item in context.get("memories", [])[:6]
        )
        return f"""
请对 AI 漫剧工厂的当前内容执行多智能体审核，并只输出一个 JSON 对象。

要求：
1. 结合 agent 分工输出 findings。
2. `blocking_status` 只能是 `pass`、`warning`、`blocked`。
3. `severity` 只能是 `low`、`medium`、`high`。
4. `memory_candidates` 至少输出 0-3 条。
5. `prompt_feedback.score` 范围 1-5。

JSON Schema:
{{
  "blocking_status": "warning",
  "severity": "medium",
  "summary": "string",
  "findings": [
    {{
      "agent": "logic-auditor",
      "title": "string",
      "severity": "medium",
      "summary": "string",
      "recommendation": "string"
    }}
  ],
  "memory_candidates": [
    {{
      "scope_type": "chapter",
      "scope_key": "string",
      "memory_type": "review_guideline",
      "content": {{"rule": "string", "owner": "string"}}
    }}
  ],
  "prompt_feedback": {{
    "template_body": "string",
    "score": 4,
    "correction_summary": "string",
    "corrected_prompt": "string"
  }}
}}

项目：{context.get('project_name')}
审核阶段：{context.get('review_stage')}
章节标题：{context.get('chapter_title') or 'project-level'}
审核 agents：{", ".join(context.get('assigned_agents', []))}
检查清单：{", ".join(context.get('checklist', []))}
角色资产：{", ".join(context.get('characters', []))}
场景资产：{", ".join(context.get('scenes', []))}
共享记忆：
{memories_text or '- 无'}

待审核内容：
{context.get('review_body') or '无可用内容'}
        """.strip()

    def _parse_model_review(self, raw_output: str) -> ReviewExecutionResult:
        compact = raw_output.strip()
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", compact, flags=re.DOTALL)
        candidate = fenced_match.group(1) if fenced_match else compact
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Model review output does not contain a JSON object.")
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model review JSON parsing failed: {exc.msg}") from exc
        try:
            return ReviewExecutionResult.model_validate(parsed)
        except ValidationError as exc:
            raise RuntimeError(f"Model review validation failed: {exc}") from exc

    def _normalize_execution_result(
        self,
        *,
        context: dict,
        execution: ReviewExecutionResult,
        provider_key: str,
    ) -> ReviewExecutionResult:
        findings = execution.findings or []
        if not findings:
            findings = [
                ReviewFinding(
                    agent=(context.get("assigned_agents") or ["logic-auditor"])[0],
                    title="建议补一条审核说明",
                    severity="low",
                    summary="模型返回了总体判断，但没有具体问题条目。",
                    recommendation="补充至少一条可执行建议，方便后续修订。",
                )
            ]
        memory_candidates = execution.memory_candidates or [
            ReviewMemoryCandidate(
                scope_type="chapter" if context.get("chapter_id") is not None else "project",
                scope_key=f"review:{context['review_stage']}:chapter:{context.get('chapter_id') or 'project'}:{findings[0].agent}",
                memory_type="review_guideline",
                content={"rule": findings[0].recommendation, "owner": findings[0].agent},
            )
        ]
        prompt_feedback = execution.prompt_feedback or ReviewPromptFeedback(
            template_body=f"生成 {context['review_stage']} 内容时，保持逻辑、连续性与角色一致性。",
            score=4,
            correction_summary=execution.summary,
            corrected_prompt=f"生成 {context['review_stage']} 内容时，保持逻辑、连续性与角色一致性，并落实：{findings[0].recommendation}",
        )
        normalized = ReviewExecutionResult.model_validate(
            {
                "blocking_status": execution.blocking_status,
                "severity": execution.severity,
                "summary": execution.summary,
                "findings": [item.model_dump() if isinstance(item, ReviewFinding) else item for item in findings],
                "memory_candidates": [
                    item.model_dump() if isinstance(item, ReviewMemoryCandidate) else item for item in memory_candidates
                ],
                "prompt_feedback": prompt_feedback.model_dump(),
                "execution_trace": execution.execution_trace,
            }
        )
        if normalized.blocking_status == "pass" and provider_key == "llm-story" and not normalized.findings:
            normalized.findings = []
        return normalized

    @staticmethod
    def _estimate_usage_amount(*, context: dict, execution: ReviewExecutionResult) -> float:
        total_chars = len(str(context.get("review_body") or "")) + len(execution.summary)
        total_chars += sum(len(item.summary) + len(item.recommendation) for item in execution.findings)
        return float(max(400, total_chars // 2))
