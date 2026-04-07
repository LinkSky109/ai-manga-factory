from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.domain.provider.routing import ProviderRouter
from src.infrastructure.db.repositories.asset_repository import AssetRepository
from src.infrastructure.db.repositories.provider_repository import ProviderRepository
from src.infrastructure.db.repositories.project_repository import ProjectRepository
from src.infrastructure.providers.ark_runtime import build_ark_runtime_client


CHAPTER_HEADER_PATTERN = re.compile(
    r"(?m)^第\s*([0-9一二三四五六七八九十百千零两]+)\s*章[^\n]*$"
)
CJK_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,4}")
SCENE_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{1,8}(?:城|殿|阁|宫|院|楼|山|谷|台|堂|林|原|府|门|峰|海|岛|街|村|镇|塔)")
COMMON_STOPWORDS = {
    "他们",
    "她们",
    "我们",
    "你们",
    "自己",
    "这里",
    "那里",
    "一个",
    "一种",
    "这个",
    "那个",
    "现在",
    "已经",
    "没有",
    "不是",
    "可以",
    "时候",
    "出来",
    "进去",
    "议事",
    "中央",
    "月光",
    "夜色",
    "族人",
    "大堂",
    "后山",
    "石台",
    "古树",
}


class InitializationChapterResult(BaseModel):
    chapter_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1)


class InitializationCharacterResult(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    appearance: str = Field(min_length=1)
    personality: str = Field(min_length=1)


class InitializationSceneResult(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    baseline_prompt: str = Field(min_length=1)
    continuity_guardrails: str | None = None


class InitializationModelPayload(BaseModel):
    summary_body: str = Field(min_length=1)
    highlights: list[str] = Field(default_factory=list)
    chapters: list[InitializationChapterResult] = Field(default_factory=list)
    script_title: str = Field(min_length=1, max_length=160)
    script_body: str = Field(min_length=1)
    characters: list[InitializationCharacterResult] = Field(default_factory=list)
    scenes: list[InitializationSceneResult] = Field(default_factory=list)


class ProjectInitializationOrchestrator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)
        self.providers = ProviderRepository(session)

    def initialize_project(
        self,
        *,
        project_id: int,
        source_title: str,
        source_type: str,
        source_text: str,
        overwrite_assets: bool = False,
        routing_mode: str = "smart",
        manual_provider: str | None = None,
    ) -> dict:
        project = self.projects.get_project(project_id)
        if project is None:
            raise LookupError("Project not found.")

        extracted_chapters = self._extract_chapters(source_text)
        generated_payload = self._generate_initialization_payload(
            project_id=project_id,
            source_title=source_title,
            source_text=source_text,
            extracted_chapters=extracted_chapters,
            routing_mode=routing_mode,
            manual_provider=manual_provider,
        )
        chapter_drafts = self._merge_chapter_drafts(
            extracted_chapters=extracted_chapters,
            generated_chapters=generated_payload["chapters"],
        )
        source = self.projects.create_source_material(
            project_id=project_id,
            source_title=source_title,
            source_type=source_type,
            body=source_text,
            chapter_count=len(chapter_drafts),
            source_metadata={
                "overwrite_assets": overwrite_assets,
                "generation_trace": generated_payload["generation_trace"],
            },
        )

        summary = self.projects.create_story_summary(
            project_id=project_id,
            source_material_id=source.id,
            summary_body=generated_payload["summary_body"],
            highlights=generated_payload["highlights"],
        )
        script = self.projects.create_script(
            project_id=project_id,
            story_summary_id=summary.id,
            title=generated_payload["script_title"],
            script_body=generated_payload["script_body"],
        )

        chapters = [
            self.projects.create_or_update_chapter(
                project_id=project_id,
                chapter_number=item["chapter_number"],
                title=item["title"],
                summary=item["summary"],
            )
            for item in chapter_drafts
        ]

        if overwrite_assets:
            self.assets.delete_project_characters(project_id)
            self.assets.delete_project_scenes(project_id)

        if overwrite_assets or not self.assets.list_characters(project_id):
            for item in generated_payload["characters"]:
                self.assets.create_character(
                    project_id=project_id,
                    name=item["name"],
                    appearance=item["appearance"],
                    personality=item["personality"],
                    lora_path=None,
                    reference_images=[],
                )

        if overwrite_assets or not self.assets.list_scenes(project_id):
            for item in generated_payload["scenes"]:
                self.assets.create_scene(
                    project_id=project_id,
                    name=item["name"],
                    baseline_prompt=item["baseline_prompt"],
                    continuity_guardrails=item["continuity_guardrails"],
                )

        self.projects.update_project_status(project, "active")
        self.session.commit()
        self.session.refresh(source)
        self.session.refresh(summary)
        self.session.refresh(script)
        return self.get_snapshot(project_id)

    def get_snapshot(self, project_id: int) -> dict:
        project = self.projects.get_project(project_id)
        if project is None:
            raise LookupError("Project not found.")

        source = self.projects.get_latest_source_material(project_id)
        summary = self.projects.get_latest_story_summary(project_id)
        script = self.projects.get_latest_script(project_id)
        chapters = self.projects.list_chapters(project_id)
        characters = sorted(self.assets.list_characters(project_id), key=lambda item: item.id)
        scenes = sorted(self.assets.list_scenes(project_id), key=lambda item: item.id)
        generation_trace = self._read_generation_trace(source)

        status = "completed" if source and summary and script else "pending"
        return {
            "project_id": project_id,
            "status": status,
            "stage_cards": self._build_stage_cards(source, summary, script, characters, scenes),
            "generation_trace": generation_trace,
            "source": None
            if source is None
            else {
                "id": source.id,
                "project_id": source.project_id,
                "source_title": source.source_title,
                "source_type": source.source_type,
                "import_status": source.import_status,
                "chapter_count": source.chapter_count,
                "content_preview": self._clip_text(source.body, limit=180),
                "created_at": source.created_at,
                "updated_at": source.updated_at,
            },
            "summary": None
            if summary is None
            else {
                "id": summary.id,
                "project_id": summary.project_id,
                "status": summary.status,
                "summary_body": summary.summary_body,
                "highlights": list(summary.highlights or []),
                "created_at": summary.created_at,
                "updated_at": summary.updated_at,
            },
            "script": None
            if script is None
            else {
                "id": script.id,
                "project_id": script.project_id,
                "status": script.status,
                "title": script.title,
                "script_body": script.script_body,
                "created_at": script.created_at,
                "updated_at": script.updated_at,
            },
            "chapters": chapters,
            "character_drafts": characters,
            "scene_drafts": scenes,
        }

    def _generate_initialization_payload(
        self,
        *,
        project_id: int,
        source_title: str,
        source_text: str,
        extracted_chapters: list[dict],
        routing_mode: str,
        manual_provider: str | None,
    ) -> dict:
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
                    payload = self._generate_with_ark(
                        source_title=source_title,
                        source_text=source_text,
                        extracted_chapters=extracted_chapters,
                    )
                    generation_mode = "model"
                elif provider_key == "llm-story":
                    payload = self._build_local_generation_payload(
                        source_title=source_title,
                        source_text=source_text,
                        chapter_drafts=extracted_chapters,
                    )
                    generation_mode = "deterministic-fallback"
                else:
                    raise RuntimeError(f"Unsupported initialization provider '{provider_key}'.")

                usage_amount = self._estimate_usage_amount(source_text=source_text, payload=payload)
                self.providers.log_usage(
                    provider_key=provider_key,
                    provider_type="llm",
                    project_id=project_id,
                    job_run_id=None,
                    metric_name="project_initialization",
                    usage_amount=usage_amount,
                    usage_unit="tokens",
                )
                attempts.append({"provider_key": provider_key, "status": "completed", "error_message": None})
                return {
                    **payload.model_dump(),
                    "generation_trace": {
                        "generation_mode": generation_mode,
                        "routing_mode": "manual" if manual_provider else routing_mode,
                        "manual_provider": manual_provider,
                        "resolved_provider_key": provider_key,
                        "provider_candidates": list(decision.candidates),
                        "provider_attempts": attempts,
                        "usage_amount": usage_amount,
                        "usage_unit": "tokens",
                    },
                }
            except Exception as exc:
                last_error = exc
                attempts.append({"provider_key": provider_key, "status": "failed", "error_message": str(exc)})

        if last_error is not None:
            raise RuntimeError(f"Project initialization failed: {last_error}") from last_error
        raise RuntimeError("Project initialization failed: no provider candidates available.")

    def _generate_with_ark(
        self,
        *,
        source_title: str,
        source_text: str,
        extracted_chapters: list[dict],
    ) -> InitializationModelPayload:
        client = build_ark_runtime_client(self.settings)
        raw_output = client.generate_text(
            prompt=self._build_model_prompt(
                source_title=source_title,
                source_text=source_text,
                extracted_chapters=extracted_chapters,
            ),
            system_prompt="你是 AI 漫剧工厂的项目初始化总编导。请只输出合法 JSON，不要输出解释、标题或 markdown。",
            model=self.settings.ark_text_model,
            temperature=0.2,
            max_tokens=4000,
        )
        parsed = self._parse_model_json(raw_output)
        return self._normalize_generated_payload(
            source_title=source_title,
            source_text=source_text,
            extracted_chapters=extracted_chapters,
            payload=parsed,
        )

    def _build_local_generation_payload(
        self,
        *,
        source_title: str,
        source_text: str,
        chapter_drafts: list[dict],
    ) -> InitializationModelPayload:
        summary_body, highlights = self._build_project_summary(chapter_drafts)
        characters = [
            {
                "name": name,
                "appearance": f"{name} 的外观仍为初始化草稿，待补充服装、年龄和镜头特征。",
                "personality": f"{name} 来自原文高频角色抽取，待补充完整性格侧写。",
            }
            for name in self._extract_character_names(source_text)
        ]
        scenes = [
            {
                "name": scene_name,
                "baseline_prompt": f"{scene_name}，延续原文氛围，保持空间连续性、镜头方向和人物站位清晰。",
                "continuity_guardrails": f"保持 {scene_name} 的入口方位、主光源和空间尺度一致。",
            }
            for scene_name in self._extract_scene_names(source_text)
        ]
        return InitializationModelPayload.model_validate(
            {
                "summary_body": summary_body,
                "highlights": highlights,
                "chapters": [
                    {
                        "chapter_number": item["chapter_number"],
                        "title": item["title"],
                        "summary": item["summary"],
                    }
                    for item in chapter_drafts
                ],
                "script_title": f"{source_title} 项目剧本初稿",
                "script_body": self._build_script(source_title=source_title, chapters=chapter_drafts),
                "characters": characters,
                "scenes": scenes,
            }
        )

    def _normalize_generated_payload(
        self,
        *,
        source_title: str,
        source_text: str,
        extracted_chapters: list[dict],
        payload: InitializationModelPayload,
    ) -> InitializationModelPayload:
        normalized_chapters = self._merge_chapter_drafts(
            extracted_chapters=extracted_chapters,
            generated_chapters=payload.chapters,
        )
        fallback_payload = self._build_local_generation_payload(
            source_title=source_title,
            source_text=source_text,
            chapter_drafts=extracted_chapters,
        )
        highlights = list(payload.highlights or [])[:8]
        if not highlights:
            highlights = [f"{item['title']}：{item['summary']}" for item in normalized_chapters[:6]]
        characters = self._dedupe_named_items(
            [
                item.model_dump()
                for item in payload.characters
                if item.name.strip() and item.appearance.strip() and item.personality.strip()
            ],
            fallback=[item.model_dump() for item in fallback_payload.characters],
        )
        scenes = self._dedupe_named_items(
            [
                item.model_dump()
                for item in payload.scenes
                if item.name.strip() and item.baseline_prompt.strip()
            ],
            fallback=[item.model_dump() for item in fallback_payload.scenes],
        )
        return InitializationModelPayload.model_validate(
            {
                "summary_body": payload.summary_body.strip() or fallback_payload.summary_body,
                "highlights": highlights,
                "chapters": normalized_chapters,
                "script_title": payload.script_title.strip() or f"{source_title} 模型剧本初稿",
                "script_body": payload.script_body.strip() or fallback_payload.script_body,
                "characters": characters,
                "scenes": scenes,
            }
        )

    def _merge_chapter_drafts(
        self,
        *,
        extracted_chapters: list[dict],
        generated_chapters: list[InitializationChapterResult] | list[dict],
    ) -> list[dict]:
        by_number: dict[int, str] = {}
        by_title: dict[str, str] = {}
        for item in generated_chapters:
            entry = item.model_dump() if isinstance(item, InitializationChapterResult) else dict(item)
            chapter_number = int(entry.get("chapter_number") or 0)
            summary = str(entry.get("summary") or "").strip()
            title = str(entry.get("title") or "").strip()
            if chapter_number >= 1 and summary:
                by_number[chapter_number] = summary
            if title and summary:
                by_title[title] = summary

        merged: list[dict] = []
        for item in extracted_chapters:
            summary = by_number.get(item["chapter_number"]) or by_title.get(item["title"]) or item["summary"]
            merged.append(
                {
                    **item,
                    "summary": summary,
                }
            )
        return merged

    def _build_model_prompt(
        self,
        *,
        source_title: str,
        source_text: str,
        extracted_chapters: list[dict],
    ) -> str:
        chapter_outline = "\n".join(
            f"- {item['chapter_number']}. {item['title']}: {self._clip_text(item['body'], limit=180)}"
            for item in extracted_chapters[:12]
        )
        clipped_source = self._clip_text(source_text, limit=6000)
        return f"""
请为 AI 漫剧工厂输出项目初始化 JSON，对小说原文做首轮生产化整理。

返回要求：
1. 只能输出一个 JSON 对象。
2. 不要输出 markdown 代码块。
3. `chapters` 数组的章节数必须和给定章节数一致。
4. `title` 请沿用给定章节标题。
5. `characters` 输出 2-6 个核心角色。
6. `scenes` 输出 2-6 个核心场景。

JSON Schema:
{{
  "summary_body": "string",
  "highlights": ["string"],
  "chapters": [{{"chapter_number": 1, "title": "string", "summary": "string"}}],
  "script_title": "string",
  "script_body": "string",
  "characters": [{{"name": "string", "appearance": "string", "personality": "string"}}],
  "scenes": [{{"name": "string", "baseline_prompt": "string", "continuity_guardrails": "string"}}]
}}

项目标题：
{source_title}

已识别章节：
{chapter_outline}

原文节选：
{clipped_source}
        """.strip()

    @staticmethod
    def _parse_model_json(raw_output: str) -> InitializationModelPayload:
        compact = raw_output.strip()
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", compact, flags=re.DOTALL)
        candidate = fenced_match.group(1) if fenced_match else compact
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Model output does not contain a JSON object.")
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model output JSON parsing failed: {exc.msg}") from exc
        try:
            return InitializationModelPayload.model_validate(parsed)
        except ValidationError as exc:
            raise RuntimeError(f"Model output validation failed: {exc}") from exc

    @staticmethod
    def _dedupe_named_items(items: list[dict], *, fallback: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        seen: set[str] = set()
        source_items = items if items else fallback
        for item in source_items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:8]

    @staticmethod
    def _estimate_usage_amount(*, source_text: str, payload: InitializationModelPayload) -> float:
        total_chars = len(source_text) + len(payload.summary_body) + len(payload.script_body)
        total_chars += sum(len(item.summary) for item in payload.chapters)
        return float(max(600, total_chars // 2))

    @staticmethod
    def _read_generation_trace(source) -> dict | None:
        if source is None:
            return None
        metadata = dict(source.source_metadata or {})
        trace = metadata.get("generation_trace")
        if isinstance(trace, dict):
            return trace
        return {
            "generation_mode": "deterministic-fallback",
            "routing_mode": "smart",
            "manual_provider": None,
            "resolved_provider_key": "llm-story",
            "provider_candidates": ["llm-story"],
            "provider_attempts": [{"provider_key": "llm-story", "status": "completed", "error_message": None}],
            "usage_amount": 0,
            "usage_unit": "tokens",
        }

    def _extract_chapters(self, source_text: str) -> list[dict]:
        normalized = source_text.replace("\r\n", "\n").strip()
        matches = list(CHAPTER_HEADER_PATTERN.finditer(normalized))
        if not matches:
            return [
                {
                    "chapter_number": 1,
                    "title": "第1章 导入原文",
                    "body": normalized,
                    "summary": self._build_chapter_summary(normalized),
                }
            ]

        chapters: list[dict] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            title = match.group(0).strip()
            body = normalized[start:end].strip()
            chapters.append(
                {
                    "chapter_number": index + 1,
                    "title": title,
                    "body": body,
                    "summary": self._build_chapter_summary(body),
                }
            )
        return chapters

    def _build_project_summary(self, chapters: list[dict]) -> tuple[str, list[str]]:
        highlights = [f"{item['title']}：{item['summary']}" for item in chapters[:6]]
        body = "\n".join(highlights) if highlights else "已导入原文，等待补充摘要。"
        return body, highlights

    def _build_script(self, *, source_title: str, chapters: list[dict]) -> str:
        sections = [f"# {source_title} 项目剧本初稿", "", "以下内容为项目初始化阶段生成的结构化草稿。", ""]
        for item in chapters:
            chapter_characters = ", ".join(self._extract_character_names(item["body"])[:3]) or "待补角色"
            chapter_scenes = ", ".join(self._extract_scene_names(item["body"])[:2]) or "待补场景"
            sections.extend(
                [
                    f"## {item['title']}",
                    f"- 剧情摘要：{item['summary']}",
                    f"- 角色焦点：{chapter_characters}",
                    f"- 场景焦点：{chapter_scenes}",
                    "- 镜头目标：先明确冲突，再补充空间调度与角色动作。",
                    "",
                ]
            )
        return "\n".join(sections).strip()

    def _extract_character_names(self, source_text: str) -> list[str]:
        counter: Counter[str] = Counter()
        for match in CJK_TOKEN_PATTERN.finditer(source_text):
            token = match.group(0)
            if token in COMMON_STOPWORDS:
                continue
            if SCENE_TOKEN_PATTERN.fullmatch(token):
                continue
            counter[token] += 1

        names = [token for token, count in counter.most_common() if count >= 1 and token not in COMMON_STOPWORDS]
        filtered = [token for token in names if not token.startswith("第")][:5]
        return filtered or ["主角"]

    def _extract_scene_names(self, source_text: str) -> list[str]:
        counter: Counter[str] = Counter()
        for match in SCENE_TOKEN_PATTERN.finditer(source_text):
            token = match.group(0)
            if token in COMMON_STOPWORDS:
                continue
            counter[token] += 1
        scenes = [token for token, _ in counter.most_common(5)]
        return scenes or ["主场景"]

    @staticmethod
    def _build_chapter_summary(body: str) -> str:
        cleaned = re.sub(r"\s+", " ", body).strip()
        if not cleaned:
            return "原文章节已导入，等待补充章节摘要。"
        return ProjectInitializationOrchestrator._clip_text(cleaned, limit=96)

    @staticmethod
    def _clip_text(text: str, *, limit: int) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

    @staticmethod
    def _build_stage_cards(
        source,
        summary,
        script,
        characters: list,
        scenes: list,
    ) -> list[dict]:
        return [
            {"label": "原文导入", "value": source.import_status if source else "pending", "tone": "success" if source else "warning"},
            {"label": "摘要生成", "value": summary.status if summary else "pending", "tone": "success" if summary else "warning"},
            {"label": "剧本初稿", "value": script.status if script else "pending", "tone": "success" if script else "warning"},
            {"label": "角色初稿", "value": str(len(characters)), "tone": "success" if characters else "warning"},
            {"label": "场景初稿", "value": str(len(scenes)), "tone": "success" if scenes else "warning"},
        ]
