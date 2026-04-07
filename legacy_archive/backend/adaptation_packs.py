from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import ADAPTATIONS_DIR
from backend.schemas import JobCreate
from shared.asset_lock import AssetLock, load_asset_lock
from shared.providers.ark import ArkProvider


DEFAULT_VISUAL_STYLE = "dark surreal xianxia, occult tension, high-contrast cinematic manga"


@dataclass(frozen=True)
class AdaptationPack:
    pack_name: str
    source_title: str
    chapter_range: str
    default_project_name: str
    default_scene_count: int
    default_target_duration_seconds: float | None
    recommended_visual_style: str
    chapter_briefs: list[dict[str, Any]]
    root_dir: Path
    asset_lock: AssetLock


def list_adaptation_packs() -> list[AdaptationPack]:
    if not ADAPTATIONS_DIR.exists():
        return []

    packs: list[AdaptationPack] = []
    for path in sorted(ADAPTATIONS_DIR.iterdir()):
        if not path.is_dir():
            continue
        try:
            packs.append(get_adaptation_pack(path.name))
        except (FileNotFoundError, ValueError):
            continue
    return packs


def get_adaptation_pack(pack_name: str) -> AdaptationPack:
    pack_dir = _get_pack_dir(pack_name)
    briefs = _load_chapter_briefs(pack_dir)
    meta = _load_pack_meta(pack_dir, briefs)
    asset_lock = load_asset_lock(pack_dir)
    return AdaptationPack(
        pack_name=pack_name,
        source_title=str(meta.get("source_title", pack_name)).strip() or pack_name,
        chapter_range=str(meta.get("chapter_range", _chapter_range_from_briefs(briefs))).strip() or _chapter_range_from_briefs(briefs),
        default_project_name=str(meta.get("default_project_name", pack_name.replace("_", "-"))).strip() or pack_name.replace("_", "-"),
        default_scene_count=int(meta.get("default_scene_count", 20) or 20),
        default_target_duration_seconds=_coerce_optional_float(meta.get("default_target_duration_seconds")),
        recommended_visual_style=str(meta.get("recommended_visual_style", DEFAULT_VISUAL_STYLE)).strip() or DEFAULT_VISUAL_STYLE,
        chapter_briefs=briefs,
        root_dir=pack_dir,
        asset_lock=asset_lock,
    )


def select_chapter_briefs(
    pack: AdaptationPack,
    *,
    chapter_start: int | None = None,
    chapter_end: int | None = None,
) -> list[dict[str, Any]]:
    if chapter_start is None and chapter_end is None:
        return pack.chapter_briefs

    selected: list[dict[str, Any]] = []
    for item in pack.chapter_briefs:
        chapter = int(item.get("chapter", 0))
        if chapter_start is not None and chapter < chapter_start:
            continue
        if chapter_end is not None and chapter > chapter_end:
            continue
        selected.append(item)

    if not selected:
        raise ValueError("No chapter briefs matched the requested chapter range")
    return selected


def build_adaptation_job_payload(
    *,
    pack: AdaptationPack,
    project_name: str | None,
    scene_count: int,
    target_duration_seconds: float | None = None,
    chapter_keyframe_count: int | None = None,
    chapter_shot_count: int | None = None,
    use_model_storyboard: bool = False,
    use_real_images: bool,
    image_model: str | None,
    video_model: str | None,
    chapter_start: int | None = None,
    chapter_end: int | None = None,
) -> JobCreate:
    chapter_briefs = select_chapter_briefs(pack, chapter_start=chapter_start, chapter_end=chapter_end)
    chapter_numbers = [int(item.get("chapter", index + 1)) for index, item in enumerate(chapter_briefs)]
    chapter_range = f"{min(chapter_numbers)}-{max(chapter_numbers)}"
    resolved_target_duration = _coerce_optional_float(target_duration_seconds)
    duration_source = "request"
    if resolved_target_duration is None:
        resolved_target_duration = pack.default_target_duration_seconds
        duration_source = "pack_default" if resolved_target_duration is not None else "auto"
    chapter_duration_plan = {
        str(int(item.get("chapter", index + 1))): value
        for index, item in enumerate(chapter_briefs)
        if (value := _coerce_optional_float(item.get("target_duration_seconds"))) is not None
    }
    payload_input: dict[str, Any] = {
        "adaptation_pack": pack.pack_name,
        "source_title": pack.source_title,
        "chapter_range": chapter_range,
        "episode_count": len(chapter_briefs),
        "visual_style": pack.recommended_visual_style,
        "storyboard_scene_count": scene_count,
        "target_duration_seconds": resolved_target_duration,
        "target_duration_source": duration_source,
        "chapter_duration_plan": chapter_duration_plan,
        "chapter_keyframe_count": chapter_keyframe_count or 4,
        "chapter_shot_count": chapter_shot_count or 10,
        "use_model_storyboard": use_model_storyboard,
        "use_real_images": use_real_images,
        "image_model": image_model or ArkProvider.DEFAULT_IMAGE_MODEL,
        "video_model": video_model or ArkProvider.DEFAULT_VIDEO_MODEL,
        "chapter_briefs": chapter_briefs,
    }
    if pack.asset_lock.exists:
        payload_input["asset_lock"] = pack.asset_lock.to_payload()
    return JobCreate(
        capability_id="manga",
        project_name=(project_name or pack.default_project_name).strip(),
        input=payload_input,
    )


def build_batch_job_payloads(
    *,
    pack: AdaptationPack,
    project_name: str | None,
    batch_size: int,
    scene_count: int,
    target_duration_seconds: float | None = None,
    chapter_keyframe_count: int | None = None,
    chapter_shot_count: int | None = None,
    use_model_storyboard: bool = False,
    use_real_images: bool,
    image_model: str | None,
    video_model: str | None,
) -> list[dict[str, Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    items: list[dict[str, Any]] = []
    for index in range(0, len(pack.chapter_briefs), batch_size):
        batch_briefs = pack.chapter_briefs[index:index + batch_size]
        payload = build_adaptation_job_payload(
            pack=pack,
            project_name=project_name,
            scene_count=scene_count,
            target_duration_seconds=target_duration_seconds,
            chapter_keyframe_count=chapter_keyframe_count,
            chapter_shot_count=chapter_shot_count,
            use_model_storyboard=use_model_storyboard,
            use_real_images=use_real_images,
            image_model=image_model,
            video_model=video_model,
            chapter_start=int(batch_briefs[0].get("chapter")),
            chapter_end=int(batch_briefs[-1].get("chapter")),
        )
        items.append(
            {
                "chapter_range": payload.input["chapter_range"],
                "chapter_count": len(batch_briefs),
                "job_payload": payload,
            }
        )
    return items


def _get_pack_dir(pack_name: str) -> Path:
    if not pack_name or pack_name != Path(pack_name).name or ".." in pack_name:
        raise KeyError(f"Invalid adaptation pack name: {pack_name}")
    pack_dir = ADAPTATIONS_DIR / pack_name
    if not pack_dir.exists() or not pack_dir.is_dir():
        raise KeyError(f"Adaptation pack '{pack_name}' not found")
    return pack_dir


def _load_pack_meta(pack_dir: Path, briefs: list[dict[str, Any]]) -> dict[str, Any]:
    meta_path = pack_dir / "pack.json"
    if not meta_path.exists():
        return {
            "source_title": pack_dir.name,
            "chapter_range": _chapter_range_from_briefs(briefs),
            "default_project_name": pack_dir.name.replace("_", "-"),
            "default_scene_count": 20,
            "default_target_duration_seconds": None,
            "recommended_visual_style": DEFAULT_VISUAL_STYLE,
        }
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _load_chapter_briefs(pack_dir: Path) -> list[dict[str, Any]]:
    briefs_path = pack_dir / "chapter_briefs.json"
    if not briefs_path.exists():
        raise FileNotFoundError(f"chapter_briefs.json not found: {briefs_path}")

    data = json.loads(briefs_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"Invalid chapter briefs: {briefs_path}")

    briefs = [item for item in data if isinstance(item, dict)]
    if not briefs:
        raise ValueError(f"Chapter briefs are empty: {briefs_path}")
    return sorted(briefs, key=lambda item: int(item.get("chapter", 0) or 0))


def _chapter_range_from_briefs(briefs: list[dict[str, Any]]) -> str:
    numbers = [int(item.get("chapter", index + 1)) for index, item in enumerate(briefs)]
    if not numbers:
        return ""
    return f"{min(numbers)}-{max(numbers)}"


def _coerce_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
