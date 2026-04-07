from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html import escape
from io import BytesIO
import math
from pathlib import Path
import tempfile
import wave

from src.core.config import get_settings
from src.domain.execution.engine import ExecutionStepOutcome
from src.infrastructure.db.models import JobRunModel
from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository
from src.infrastructure.providers.ark_runtime import build_ark_runtime_client
from src.infrastructure.storage.archive_adapters import (
    ArchiveWriteResult,
)
from src.infrastructure.storage.archive_index import ArchiveIndexService
from src.infrastructure.storage.archive_registry import build_archive_adapters


@dataclass(slots=True)
class GeneratedArtifactBundle:
    media_kind: str
    mime_type: str
    artifact_bytes: bytes
    preview_bytes: bytes
    artifact_extension: str
    preview_extension: str
    playback_hint: str


@dataclass(slots=True)
class GeneratedArtifactResult:
    bundle: GeneratedArtifactBundle
    provider_attempts: list[dict]
    resolved_provider_key: str


class ArtifactStorageService:
    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository
        self.settings = get_settings()
        self.index = ArchiveIndexService(self.settings.archive_index_path)

    def materialize_step_artifact(self, job: JobRunModel, step: ExecutionStepOutcome, payload: dict | None = None) -> dict | None:
        if step.status != "completed":
            return None

        result = self._build_bundle(job=job, step=step, payload=payload or {})
        bundle = result.bundle
        artifact_relative_path = self._relative_path(job=job, step_key=step.key, suffix="artifact", extension=bundle.artifact_extension)
        preview_relative_path = self._relative_path(job=job, step_key=step.key, suffix="preview", extension=bundle.preview_extension)
        artifact_file = self.settings.artifact_root / artifact_relative_path
        preview_file = self.settings.preview_root / preview_relative_path
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        preview_file.parent.mkdir(parents=True, exist_ok=True)

        artifact_file.write_bytes(bundle.artifact_bytes)
        preview_file.write_bytes(bundle.preview_bytes)
        checksum_sha256 = self._compute_sha256(artifact_file)

        artifact = self.repository.upsert_artifact(
            project_id=job.project_id,
            chapter_id=job.chapter_id,
            job_run_id=job.id,
            step_key=step.key,
            title=f"{step.title} 预览",
            media_kind=bundle.media_kind,
            provider_key=step.provider_key,
            mime_type=bundle.mime_type,
            artifact_path=artifact_relative_path.as_posix(),
            preview_path=preview_relative_path.as_posix(),
            size_bytes=len(bundle.preview_bytes),
            artifact_metadata={
                "playback_hint": bundle.playback_hint,
                "usage_amount": step.usage_amount,
                "usage_unit": step.usage_unit,
                "provider_type": step.provider_type,
                "archive_targets": list(self.settings.archive_targets),
                "checksum_sha256": checksum_sha256,
                "provider_attempts": result.provider_attempts,
                "provider_candidates": list(getattr(step, "provider_candidates", []) or [step.provider_key]),
                "resolved_provider_key": result.resolved_provider_key,
            },
        )
        for write_result in self._write_archives(artifact=artifact, source_file=artifact_file):
            archive = self.repository.upsert_archive(
                artifact_id=artifact.id,
                archive_type=write_result.archive_type,
                archive_path=write_result.archive_path,
                index_key=write_result.index_key,
                remote_url=write_result.public_url,
                checksum_sha256=checksum_sha256,
            )
            self.index.upsert_record(
                record_id=f"{artifact.id}:{write_result.archive_type}",
                payload={
                    "artifact_id": artifact.id,
                    "project_id": artifact.project_id,
                    "chapter_id": artifact.chapter_id,
                    "job_run_id": artifact.job_run_id,
                    "step_key": artifact.step_key,
                    "title": artifact.title,
                    "media_kind": artifact.media_kind,
                    "mime_type": artifact.mime_type,
                    "preview_path": artifact.preview_path,
                    "archive_type": archive.archive_type,
                    "archive_path": archive.archive_path,
                    "archive_status": archive.status,
                    "archive_url": write_result.public_url,
                    "checksum_sha256": checksum_sha256,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        return {
            "provider_attempts": result.provider_attempts,
            "provider_candidates": list(getattr(step, "provider_candidates", []) or [step.provider_key]),
            "resolved_provider_key": result.resolved_provider_key,
            "playback_hint": bundle.playback_hint,
            "mime_type": bundle.mime_type,
            "media_kind": bundle.media_kind,
            "checksum_sha256": checksum_sha256,
        }

    def resolve_preview_file(self, preview_path: str) -> Path:
        return self.settings.preview_root / preview_path

    def sync_existing_artifact(self, artifact) -> int:
        return self.sync_existing_artifact_targets(artifact=artifact, archive_types=None)

    def sync_existing_artifact_targets(self, artifact, archive_types: list[str] | None) -> int:
        source_file = self.settings.artifact_root / artifact.artifact_path
        if not source_file.exists():
            raise FileNotFoundError(f"Artifact source file '{artifact.artifact_path}' is missing.")
        checksum_sha256 = self._compute_sha256(source_file)
        artifact.artifact_metadata = {
            **dict(artifact.artifact_metadata or {}),
            "checksum_sha256": checksum_sha256,
        }

        write_results = self._write_archives(
            artifact=artifact,
            source_file=source_file,
            archive_types=archive_types,
        )
        for write_result in write_results:
            archive = self.repository.upsert_archive(
                artifact_id=artifact.id,
                archive_type=write_result.archive_type,
                archive_path=write_result.archive_path,
                index_key=write_result.index_key,
                remote_url=write_result.public_url,
                checksum_sha256=checksum_sha256,
            )
            self.index.upsert_record(
                record_id=f"{artifact.id}:{write_result.archive_type}",
                payload={
                    "artifact_id": artifact.id,
                    "project_id": artifact.project_id,
                    "chapter_id": artifact.chapter_id,
                    "job_run_id": artifact.job_run_id,
                    "step_key": artifact.step_key,
                    "title": artifact.title,
                    "media_kind": artifact.media_kind,
                    "mime_type": artifact.mime_type,
                    "preview_path": artifact.preview_path,
                    "archive_type": archive.archive_type,
                    "archive_path": archive.archive_path,
                    "archive_status": archive.status,
                    "archive_url": write_result.public_url,
                    "checksum_sha256": checksum_sha256,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return len(write_results)

    def list_enabled_archive_types(self) -> list[str]:
        return [adapter.archive_type for adapter in build_archive_adapters(self.settings)]

    @staticmethod
    def _relative_path(job: JobRunModel, step_key: str, suffix: str, extension: str) -> Path:
        chapter_segment = f"chapter_{job.chapter_id}" if job.chapter_id is not None else "chapter_unassigned"
        return Path(f"project_{job.project_id}") / chapter_segment / f"job_{job.id}" / f"{step_key}-{suffix}{extension}"

    @staticmethod
    def _index_key(job: JobRunModel, step_key: str) -> str:
        chapter_segment = str(job.chapter_id) if job.chapter_id is not None else "none"
        return f"project:{job.project_id}:chapter:{chapter_segment}:job:{job.id}:step:{step_key}"

    def _write_archives(
        self,
        artifact,
        source_file: Path,
        archive_types: list[str] | None = None,
    ) -> list[ArchiveWriteResult]:
        adapters = build_archive_adapters(self.settings)
        if archive_types is not None:
            requested_types = list(dict.fromkeys(archive_types))
            adapters = [adapter for adapter in adapters if adapter.archive_type in requested_types]
            resolved_types = {adapter.archive_type for adapter in adapters}
            missing_types = [archive_type for archive_type in requested_types if archive_type not in resolved_types]
            if missing_types:
                raise ValueError(f"Archive targets are not enabled: {', '.join(missing_types)}.")

        results: list[ArchiveWriteResult] = []
        for adapter in adapters:
            results.append(adapter.write(artifact=artifact, source_file=source_file))
        return results

    def _build_bundle(self, job: JobRunModel, step: ExecutionStepOutcome, payload: dict) -> GeneratedArtifactResult:
        candidates = list(getattr(step, "provider_candidates", []) or [step.provider_key])
        last_error: Exception | None = None
        provider_attempts: list[dict] = []
        for candidate_key in candidates:
            try:
                bundle = self._build_bundle_for_provider(
                    job=job,
                    step=step,
                    provider_key=candidate_key,
                    payload=payload,
                )
                provider_attempts.append({"provider_key": candidate_key, "status": "completed"})
                step.provider_key = candidate_key
                return GeneratedArtifactResult(
                    bundle=bundle,
                    provider_attempts=provider_attempts,
                    resolved_provider_key=candidate_key,
                )
            except Exception as exc:
                last_error = exc
                provider_attempts.append(
                    {
                        "provider_key": candidate_key,
                        "status": "failed",
                        "error_message": str(exc),
                    }
                )
                continue

        if last_error is not None:
            raise RuntimeError(f"All providers failed for step '{step.key}': {last_error}") from last_error
        raise RuntimeError(f"No provider candidates available for step '{step.key}'.")

    def _build_bundle_for_provider(
        self,
        job: JobRunModel,
        step: ExecutionStepOutcome,
        provider_key: str,
        payload: dict,
    ) -> GeneratedArtifactBundle:
        if provider_key == "ark-story":
            client = build_ark_runtime_client(self.settings)
            generated_text = client.generate_text(
                prompt=self._build_storyboard_prompt(job=job, step=step, payload=payload),
                system_prompt="你是 AI 漫剧工厂的分镜编剧，请输出清晰、紧凑、适合镜头拆解的中文分镜说明。",
                model=self.settings.ark_text_model,
            )
            html_preview = self._build_html_preview(job=job, step=step, generated_body=generated_text)
            return GeneratedArtifactBundle(
                media_kind="storyboard",
                mime_type="text/html; charset=utf-8",
                artifact_bytes=html_preview,
                preview_bytes=html_preview,
                artifact_extension=".html",
                preview_extension=".html",
                playback_hint="已通过 Ark API 生成分镜预览。",
            )

        if provider_key == "ark-video":
            client = build_ark_runtime_client(self.settings)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            try:
                client.generate_video_to_file(
                    prompt=self._build_video_prompt(job=job, step=step, payload=payload),
                    output_path=temp_path,
                    model=self.settings.ark_video_model,
                )
                video_bytes = temp_path.read_bytes()
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            return GeneratedArtifactBundle(
                media_kind="video",
                mime_type="video/mp4",
                artifact_bytes=video_bytes,
                preview_bytes=video_bytes,
                artifact_extension=".mp4",
                preview_extension=".mp4",
                playback_hint="已通过 Ark API 生成视频预览。",
            )

        if provider_key == "ark-image":
            client = build_ark_runtime_client(self.settings)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            try:
                client.generate_image_to_file(
                    prompt=self._build_image_prompt(job=job, step=step, payload=payload),
                    output_path=temp_path,
                    model=self.settings.ark_image_model,
                )
                image_bytes = temp_path.read_bytes()
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            return GeneratedArtifactBundle(
                media_kind="image",
                mime_type="image/png",
                artifact_bytes=image_bytes,
                preview_bytes=image_bytes,
                artifact_extension=".png",
                preview_extension=".png",
                playback_hint="已通过 Ark API 生成图片预览。",
            )

        if step.provider_type == "voice":
            audio_bytes = self._build_wave_preview(step.title)
            return GeneratedArtifactBundle(
                media_kind="audio",
                mime_type="audio/wav",
                artifact_bytes=audio_bytes,
                preview_bytes=audio_bytes,
                artifact_extension=".wav",
                preview_extension=".wav",
                playback_hint="已生成可直接播放的音频预览。",
            )

        if step.provider_type == "image":
            svg_bytes = self._build_svg_preview(job=job, step=step)
            return GeneratedArtifactBundle(
                media_kind="image",
                mime_type="image/svg+xml",
                artifact_bytes=svg_bytes,
                preview_bytes=svg_bytes,
                artifact_extension=".svg",
                preview_extension=".svg",
                playback_hint="已生成可直接查看的图片预览。",
            )

        html_preview = self._build_html_preview(job=job, step=step)
        media_kind = "video" if step.provider_type == "video" else "storyboard" if step.provider_type == "llm" else "artifact"
        return GeneratedArtifactBundle(
            media_kind=media_kind,
            mime_type="text/html; charset=utf-8",
            artifact_bytes=html_preview,
            preview_bytes=html_preview,
            artifact_extension=".html",
            preview_extension=".html",
            playback_hint="已生成可访问的预览页面。",
        )

    @staticmethod
    def _build_wave_preview(title: str) -> bytes:
        sample_rate = 22050
        duration_seconds = 1.2
        amplitude = 9000
        total_frames = int(sample_rate * duration_seconds)
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            frames = bytearray()
            for frame_no in range(total_frames):
                envelope = 1 - (frame_no / total_frames) * 0.35
                sample = int(amplitude * envelope * math.sin(2 * math.pi * 440 * (frame_no / sample_rate)))
                frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
            wav_file.writeframes(bytes(frames))
        return buffer.getvalue()

    @staticmethod
    def _compute_sha256(source_file: Path) -> str:
        digest = hashlib.sha256()
        with source_file.open("rb") as artifact_stream:
            for chunk in iter(lambda: artifact_stream.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _build_storyboard_prompt(job: JobRunModel, step: ExecutionStepOutcome, payload: dict) -> str:
        story_context = str(payload.get("story_context") or payload.get("story_prompt") or payload.get("prompt") or "").strip()
        chapter_text = str(job.chapter_id) if job.chapter_id is not None else "未分配章节"
        if story_context:
            return (
                f"项目 {job.project_id}，章节 {chapter_text}，节点 {step.title}。\n"
                f"请基于以下剧情上下文生成 4-6 条镜头分镜说明，并保持角色与场景一致性：\n{story_context}"
            )
        return (
            f"项目 {job.project_id}，章节 {chapter_text}，节点 {step.title}。\n"
            "请生成 4-6 条简明中文分镜说明，包含镜头主体、景别、动作和氛围。"
        )

    @staticmethod
    def _build_video_prompt(job: JobRunModel, step: ExecutionStepOutcome, payload: dict) -> str:
        visual_prompt = str(payload.get("video_prompt") or payload.get("prompt") or payload.get("story_context") or "").strip()
        chapter_text = str(job.chapter_id) if job.chapter_id is not None else "未分配章节"
        if visual_prompt:
            return (
                f"项目 {job.project_id}，章节 {chapter_text}，节点 {step.title}。\n"
                f"请生成一段适合 AI 漫剧预告的短视频镜头：{visual_prompt}"
            )
        return f"项目 {job.project_id}，章节 {chapter_text}，生成一段具有电影感的 AI 漫剧短视频镜头。"

    @staticmethod
    def _build_image_prompt(job: JobRunModel, step: ExecutionStepOutcome, payload: dict) -> str:
        visual_prompt = str(payload.get("image_prompt") or payload.get("prompt") or payload.get("story_context") or "").strip()
        chapter_text = str(job.chapter_id) if job.chapter_id is not None else "未分配章节"
        if visual_prompt:
            return (
                f"项目 {job.project_id}，章节 {chapter_text}，节点 {step.title}。\n"
                f"请生成一张适合 AI 漫剧封面或关键帧的图片：{visual_prompt}"
            )
        return f"项目 {job.project_id}，章节 {chapter_text}，生成一张具有电影感的 AI 漫剧关键帧图片。"

    @staticmethod
    def _build_html_preview(job: JobRunModel, step: ExecutionStepOutcome, generated_body: str | None = None) -> bytes:
        title = escape(step.title)
        provider_key = escape(step.provider_key or "pending")
        provider_type = escape(step.provider_type)
        chapter_text = escape(str(job.chapter_id) if job.chapter_id is not None else "unassigned")
        step_key = escape(step.key)
        generated_section = ""
        if generated_body:
            generated_section = (
                '<article class="card" style="grid-column: 1 / -1;">'
                "<strong>Generated Output</strong>"
                f"<p>{escape(generated_body).replace(chr(10), '<br />')}</p>"
                "</article>"
            )
        body = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title} Preview</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: "IBM Plex Sans", "Noto Sans SC", sans-serif;
        background: linear-gradient(180deg, #0f1724, #1f3b56);
        color: #eef4ff;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
      }}
      .frame {{
        width: min(900px, calc(100vw - 32px));
        border-radius: 28px;
        padding: 28px;
        background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.04));
        border: 1px solid rgba(255,255,255,0.18);
        box-shadow: 0 24px 64px rgba(0,0,0,0.24);
      }}
      .eyebrow {{
        text-transform: uppercase;
        letter-spacing: 0.16em;
        font-size: 12px;
        color: rgba(238,244,255,0.70);
      }}
      h1 {{
        margin: 10px 0 14px;
        font-size: clamp(30px, 5vw, 56px);
        line-height: 0.94;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
        margin-top: 18px;
      }}
      .card {{
        padding: 16px;
        border-radius: 18px;
        background: rgba(255,255,255,0.08);
      }}
      p {{
        margin: 0;
        line-height: 1.7;
        color: rgba(238,244,255,0.86);
      }}
    </style>
  </head>
  <body>
    <main class="frame">
      <div class="eyebrow">AI Manga Factory Preview</div>
      <h1>{title}</h1>
      <p>这是 Step 6 生成的真实预览资源。当前节点已经完成，可通过统一预览服务即时访问。</p>
      <section class="grid">
        <article class="card"><strong>Project</strong><p>#{job.project_id}</p></article>
        <article class="card"><strong>Chapter</strong><p>#{chapter_text}</p></article>
        <article class="card"><strong>Step</strong><p>{step_key}</p></article>
        <article class="card"><strong>Provider</strong><p>{provider_key} / {provider_type}</p></article>
        {generated_section}
      </section>
    </main>
  </body>
</html>
"""
        return body.encode("utf-8")

    @staticmethod
    def _build_svg_preview(job: JobRunModel, step: ExecutionStepOutcome) -> bytes:
        title = escape(step.title)
        provider_key = escape(step.provider_key or "pending")
        chapter_text = escape(str(job.chapter_id) if job.chapter_id is not None else "unassigned")
        body = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#17283f" />
      <stop offset="100%" stop-color="#8b5f2f" />
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#bg)" rx="36" />
  <text x="80" y="120" fill="#f7efe2" font-size="28" font-family="IBM Plex Sans, Noto Sans SC, sans-serif">AI Manga Factory Image Preview</text>
  <text x="80" y="250" fill="#ffffff" font-size="88" font-family="IBM Plex Sans, Noto Sans SC, sans-serif">{title}</text>
  <text x="80" y="330" fill="#d9e1ef" font-size="34" font-family="IBM Plex Sans, Noto Sans SC, sans-serif">Project #{job.project_id} · Chapter #{chapter_text}</text>
  <text x="80" y="390" fill="#d9e1ef" font-size="34" font-family="IBM Plex Sans, Noto Sans SC, sans-serif">Provider: {provider_key}</text>
</svg>
"""
        return body.encode("utf-8")
