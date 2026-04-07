from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ASSET_LOCK_FILENAME = "asset_lock.json"
ASSET_LOCK_DIRECTORIES = (
    "assets/characters",
    "assets/scenes",
    "assets/voices",
    "assets/loras",
)
CHARACTER_CARDS_PATH = Path("assets/characters/character_cards.json")
SCENE_CARDS_PATH = Path("assets/scenes/scene_cards.json")
DEFAULT_TEMPLATE_VOICE_IDS = {
    "待补角色01": "zh-CN-YunxiNeural",
    "待补角色02": "zh-CN-XiaoyiNeural",
    "待补角色03": "zh-CN-YunjianNeural",
    "旁白": "zh-CN-XiaoxiaoNeural",
}


def _normalize_alias_key(value: str) -> str:
    normalized = re.sub(r"\s+", "", str(value or "").strip().lower())
    normalized = re.sub(r"[，、,;；/|]+", "", normalized)
    return normalized


def split_character_tokens(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    tokens = re.split(r"[，、,;；/|]+", raw)
    return [token.strip() for token in tokens if token and token.strip()]


def _coerce_aliases(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return split_character_tokens(value)
    if isinstance(value, list):
        aliases: list[str] = []
        for item in value:
            aliases.extend(split_character_tokens(str(item)))
        return aliases
    raise ValueError("asset_lock aliases must be a string or list")


def _draft_character_names() -> tuple[str, ...]:
    return ("待补角色01", "待补角色02", "待补角色03", "旁白")


def _split_visual_traits(value: str, *, limit: int = 6) -> list[str]:
    parts = [item.strip() for item in re.split(r"[，。；、,.!！?？]+", str(value or "").strip()) if item.strip()]
    return parts[:limit]


def _build_asset_status(*, reference_image_path: Path | None, notes: str) -> str:
    lowered = str(notes or "").lower()
    if "占位" in str(notes or "") or "placeholder" in lowered:
        return "reference_placeholder"
    if reference_image_path is not None:
        return "reference_ready"
    return "missing_reference"


def _infer_dramatic_role(*, index: int, name: str) -> str:
    if name == "旁白":
        return "narrator"
    if index == 1:
        return "lead"
    lowered = name.lower()
    if any(token in name for token in ("敌", "反派", "对决", "对手")) or "rival" in lowered:
        return "rival"
    return "support"


def _default_review_fields(*, asset_status: str) -> dict[str, Any]:
    return {
        "review_status": "pending" if asset_status in {"needs_definition", "missing_reference", "reference_placeholder"} else "in_review",
        "review_notes": "",
        "approval_notes": "",
        "reviewed_by": "",
        "reviewed_at": None,
        "owner": "",
        "review_checklist": [],
        "source_evidence": [],
        "last_verified_job_id": None,
        "usage_scope": "storyboard_audio_video",
        "continuity_guardrails": [],
    }


def _normalize_character_card(card: dict[str, Any]) -> dict[str, Any]:
    asset_status = str(card.get("asset_status") or "needs_definition").strip() or "needs_definition"
    normalized = dict(card)
    normalized.setdefault("display_name", normalized.get("name"))
    normalized.setdefault("visual_traits", [])
    normalized.setdefault("costume_notes", "")
    normalized.setdefault("expression_notes", "")
    normalized.setdefault("reference_assets", {"image": normalized.get("reference_image_path"), "lora": normalized.get("lora_path")})
    normalized.setdefault("approval_gate", "art_review")
    normalized.setdefault("missing_assets", [])
    normalized.setdefault("asset_status_detail", "")
    normalized.update({key: normalized.get(key, value) for key, value in _default_review_fields(asset_status=asset_status).items()})
    return normalized


def _normalize_scene_card(card: dict[str, Any]) -> dict[str, Any]:
    asset_status = str(card.get("asset_status") or "needs_definition").strip() or "needs_definition"
    normalized = dict(card)
    normalized.setdefault("lighting_notes", "")
    normalized.setdefault("material_notes", "")
    normalized.setdefault("camera_guardrails", [])
    normalized.setdefault("reference_assets", {"image": normalized.get("reference_image_path")})
    normalized.setdefault("approval_gate", "art_review")
    normalized.setdefault("missing_assets", [])
    normalized.setdefault("asset_status_detail", "")
    normalized.update({key: normalized.get(key, value) for key, value in _default_review_fields(asset_status=asset_status).items()})
    return normalized


def _resolve_optional_path(
    pack_root: Path,
    value: Any,
    *,
    validation_errors: list[str],
) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (pack_root / path).resolve()
    if not path.exists():
        validation_errors.append(f"资产锁引用路径无效：{raw}")
    return path


@dataclass(frozen=True)
class AssetLockCharacter:
    name: str
    aliases: tuple[str, ...]
    fixed_prompt: str
    voice_id: str
    reference_image_path: Path | None = None
    lora_path: Path | None = None
    notes: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "fixed_prompt": self.fixed_prompt,
            "voice_id": self.voice_id,
            "reference_image_path": str(self.reference_image_path) if self.reference_image_path else None,
            "lora_path": str(self.lora_path) if self.lora_path else None,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AssetLock:
    pack_root: Path
    source_path: Path | None = None
    exists: bool = False
    scene_baseline_prompt: str = ""
    scene_reference_image_path: Path | None = None
    characters: tuple[AssetLockCharacter, ...] = ()
    validation_errors: tuple[str, ...] = ()
    _alias_lookup: dict[str, int] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        alias_lookup: dict[str, int] = {}
        for index, character in enumerate(self.characters):
            for alias in (character.name, *character.aliases):
                key = _normalize_alias_key(alias)
                if key and key not in alias_lookup:
                    alias_lookup[key] = index
        object.__setattr__(self, "_alias_lookup", alias_lookup)

    @classmethod
    def empty(cls, *, pack_root: Path, source_path: Path | None = None, exists: bool = False) -> AssetLock:
        return cls(pack_root=pack_root, source_path=source_path, exists=exists)

    @property
    def enabled(self) -> bool:
        return self.exists and bool(self.scene_baseline_prompt or self.characters)

    def resolve_character(self, raw_name: str | None) -> AssetLockCharacter | None:
        key = _normalize_alias_key(str(raw_name or ""))
        if not key:
            return None
        index = self._alias_lookup.get(key)
        if index is None:
            return None
        return self.characters[index]

    def resolve_many(self, raw_names: Iterable[str]) -> tuple[AssetLockCharacter, ...]:
        seen: set[str] = set()
        resolved: list[AssetLockCharacter] = []
        for raw_name in raw_names:
            character = self.resolve_character(raw_name)
            if character is None or character.name in seen:
                continue
            seen.add(character.name)
            resolved.append(character)
        return tuple(resolved)

    def lead_character(self) -> AssetLockCharacter | None:
        for alias in ("主角", "男主", "女主", "lead"):
            character = self.resolve_character(alias)
            if character is not None:
                return character
        return self.characters[0] if self.characters else None

    def narrator_character(self) -> AssetLockCharacter | None:
        for alias in ("旁白", "解说", "narrator"):
            character = self.resolve_character(alias)
            if character is not None:
                return character
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "pack_root": str(self.pack_root),
            "source_path": str(self.source_path) if self.source_path else None,
            "scene": {
                "baseline_prompt": self.scene_baseline_prompt,
                "reference_image_path": str(self.scene_reference_image_path) if self.scene_reference_image_path else None,
            },
            "characters": [character.to_payload() for character in self.characters],
            "validation_errors": list(self.validation_errors),
        }

    def to_summary(self) -> dict[str, Any]:
        return {
            **self.to_payload(),
            "enabled": self.enabled,
            "character_count": len(self.characters),
            "voice_mappings": [
                {"name": character.name, "voice_id": character.voice_id}
                for character in self.characters
            ],
        }


def asset_lock_from_payload(data: dict[str, Any] | None) -> AssetLock:
    if not isinstance(data, dict):
        return AssetLock.empty(pack_root=Path("."))

    validation_errors = tuple(str(item).strip() for item in data.get("validation_errors", []) if str(item).strip())
    scene = data.get("scene") if isinstance(data.get("scene"), dict) else {}
    characters: list[AssetLockCharacter] = []
    for item in data.get("characters", []):
        if not isinstance(item, dict):
            continue
        characters.append(
            AssetLockCharacter(
                name=str(item.get("name", "")).strip(),
                aliases=tuple(str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()),
                fixed_prompt=str(item.get("fixed_prompt", "")).strip(),
                voice_id=str(item.get("voice_id", "")).strip(),
                reference_image_path=Path(item["reference_image_path"]) if item.get("reference_image_path") else None,
                lora_path=Path(item["lora_path"]) if item.get("lora_path") else None,
                notes=str(item.get("notes", "")).strip(),
            )
        )

    return AssetLock(
        pack_root=Path(str(data.get("pack_root") or ".")),
        source_path=Path(str(data["source_path"])) if data.get("source_path") else None,
        exists=bool(data.get("exists", False)),
        scene_baseline_prompt=str(scene.get("baseline_prompt", "")).strip(),
        scene_reference_image_path=Path(scene["reference_image_path"]) if scene.get("reference_image_path") else None,
        characters=tuple(characters),
        validation_errors=validation_errors,
    )


def load_asset_lock(pack_root: Path) -> AssetLock:
    source_path = pack_root / ASSET_LOCK_FILENAME
    if not source_path.exists():
        return AssetLock.empty(pack_root=pack_root, source_path=source_path, exists=False)

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("asset_lock.json must contain an object")

    validation_errors: list[str] = []
    scene = payload.get("scene") if isinstance(payload.get("scene"), dict) else {}
    characters_payload = payload.get("characters", [])
    if characters_payload in ("", None):
        characters_payload = []
    if not isinstance(characters_payload, list):
        raise ValueError("asset_lock characters must be a list")

    alias_registry: dict[str, str] = {}
    characters: list[AssetLockCharacter] = []
    for index, item in enumerate(characters_payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"asset_lock character at index {index} must be an object")
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(f"asset_lock character at index {index} is missing name")
        aliases = [alias for alias in _coerce_aliases(item.get("aliases")) if alias]
        normalized_aliases = []
        for alias in [name, *aliases]:
            key = _normalize_alias_key(alias)
            if not key:
                continue
            owner = alias_registry.get(key)
            if owner and owner != name:
                raise ValueError(f"duplicate alias '{alias}' between '{owner}' and '{name}'")
            alias_registry[key] = name
            if alias != name and alias not in normalized_aliases:
                normalized_aliases.append(alias)
        characters.append(
            AssetLockCharacter(
                name=name,
                aliases=tuple(normalized_aliases),
                fixed_prompt=str(item.get("fixed_prompt", "")).strip(),
                voice_id=str(item.get("voice_id", "")).strip(),
                reference_image_path=_resolve_optional_path(
                    pack_root,
                    item.get("reference_image_path"),
                    validation_errors=validation_errors,
                ),
                lora_path=_resolve_optional_path(
                    pack_root,
                    item.get("lora_path"),
                    validation_errors=validation_errors,
                ),
                notes=str(item.get("notes", "")).strip(),
            )
        )

    return AssetLock(
        pack_root=pack_root,
        source_path=source_path,
        exists=True,
        scene_baseline_prompt=str(scene.get("baseline_prompt", "")).strip(),
        scene_reference_image_path=_resolve_optional_path(
            pack_root,
            scene.get("reference_image_path"),
            validation_errors=validation_errors,
        ),
        characters=tuple(characters),
        validation_errors=tuple(validation_errors),
    )


def build_asset_lock_template(source_title: str) -> dict[str, Any]:
    return {
        "scene": {
            "baseline_prompt": f"请填写《{source_title}》统一的场景基线：空间材质、光源、色温、时代细节与镜头禁忌。",
            "reference_image_path": None,
        },
        "characters": [
            {
                "name": role_name,
                "aliases": [],
                "fixed_prompt": f"请填写 {role_name} 的固定外观特征、服装、年龄、神态与镜头禁忌。",
                "voice_id": DEFAULT_TEMPLATE_VOICE_IDS[role_name],
                "reference_image_path": None,
                "lora_path": None,
                "notes": "待补真实角色设定，不要直接把模板名称带入正式分镜与音频链路。",
            }
            for role_name in _draft_character_names()
        ],
    }


def build_character_cards_template(source_title: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for index, role_name in enumerate(_draft_character_names(), start=1):
        cards.append(
            {
                "character_id": f"character_{index:02d}",
                "name": role_name,
                "display_name": role_name,
                "source_title": source_title,
                "voice_id": DEFAULT_TEMPLATE_VOICE_IDS[role_name],
                "aliases": [],
                "fixed_prompt": f"请补充 {role_name} 的固定外观、服装、年龄、神态和镜头禁忌。",
                "reference_image_path": None,
                "lora_path": None,
                "dramatic_role": "narrator" if role_name == "旁白" else ("lead" if index == 1 else "support"),
                "visual_traits": [],
                "costume_notes": "",
                "expression_notes": "",
                "asset_status": "needs_definition",
                "reference_assets": {"image": None, "lora": None},
                "approval_gate": "art_review",
                "missing_assets": ["reference_image", "visual_traits"],
                "asset_status_detail": "waiting_for_real_design_reference",
                "review_status": "pending",
                "review_notes": "",
                "approval_notes": "",
                "reviewed_by": "",
                "reviewed_at": None,
                "owner": "",
                "review_checklist": [],
                "source_evidence": [],
                "last_verified_job_id": None,
                "usage_scope": "storyboard_audio_video",
                "continuity_guardrails": [],
                "notes": "待补真实角色卡；模板名称不能进入正式分镜和音频。",
            }
        )
    return cards


def build_scene_cards_template(source_title: str) -> list[dict[str, Any]]:
    return [
        {
            "scene_id": "primary_world",
            "name": f"{source_title} 主场景基线",
            "source_title": source_title,
            "baseline_prompt": f"请补充《{source_title}》统一的空间材质、光源、色温、时代细节和镜头禁忌。",
            "reference_image_path": None,
            "lighting_notes": "",
            "material_notes": "",
            "camera_guardrails": [],
            "asset_status": "needs_definition",
            "reference_assets": {"image": None},
            "approval_gate": "art_review",
            "missing_assets": ["reference_image", "lighting_notes"],
            "asset_status_detail": "waiting_for_world_scene_reference",
            "review_status": "pending",
            "review_notes": "",
            "approval_notes": "",
            "reviewed_by": "",
            "reviewed_at": None,
            "owner": "",
            "review_checklist": [],
            "source_evidence": [],
            "last_verified_job_id": None,
            "usage_scope": "storyboard_audio_video",
            "continuity_guardrails": [],
            "notes": "待补正式场景卡和场景参考图。",
        }
    ]


def build_asset_cards_from_lock(*, source_title: str, asset_lock: AssetLock) -> dict[str, Any]:
    character_cards = [
        {
            "character_id": f"character_{index:02d}",
            "name": character.name,
            "display_name": character.name,
            "source_title": source_title,
            "voice_id": character.voice_id,
            "aliases": list(character.aliases),
            "fixed_prompt": character.fixed_prompt,
            "reference_image_path": str(character.reference_image_path) if character.reference_image_path else None,
            "lora_path": str(character.lora_path) if character.lora_path else None,
            "dramatic_role": _infer_dramatic_role(index=index, name=character.name),
            "visual_traits": _split_visual_traits(character.fixed_prompt),
            "costume_notes": "",
            "expression_notes": "",
            "asset_status": _build_asset_status(
                reference_image_path=character.reference_image_path,
                notes=character.notes,
            ),
            "reference_assets": {
                "image": str(character.reference_image_path) if character.reference_image_path else None,
                "lora": str(character.lora_path) if character.lora_path else None,
            },
            "approval_gate": "art_review",
            "missing_assets": [] if character.reference_image_path else ["reference_image"],
            "asset_status_detail": "placeholder_reference_based_on_text" if character.reference_image_path else "missing_reference_image",
            "review_status": "in_review",
            "review_notes": "",
            "approval_notes": "",
            "reviewed_by": "",
            "reviewed_at": None,
            "owner": "",
            "review_checklist": [],
            "source_evidence": [],
            "last_verified_job_id": None,
            "usage_scope": "storyboard_audio_video",
            "continuity_guardrails": [],
            "notes": character.notes,
        }
        for index, character in enumerate(asset_lock.characters, start=1)
    ]
    if not character_cards:
        character_cards = build_character_cards_template(source_title)
    scene_cards = [
        {
            "scene_id": "primary_world",
            "name": f"{source_title} 主场景基线",
            "source_title": source_title,
            "baseline_prompt": asset_lock.scene_baseline_prompt,
            "reference_image_path": str(asset_lock.scene_reference_image_path) if asset_lock.scene_reference_image_path else None,
            "lighting_notes": "",
            "material_notes": "",
            "camera_guardrails": [],
            "asset_status": _build_asset_status(
                reference_image_path=asset_lock.scene_reference_image_path,
                notes="",
            ),
            "reference_assets": {
                "image": str(asset_lock.scene_reference_image_path) if asset_lock.scene_reference_image_path else None,
            },
            "approval_gate": "art_review",
            "missing_assets": [] if asset_lock.scene_reference_image_path else ["reference_image"],
            "asset_status_detail": "scene_reference_ready" if asset_lock.scene_reference_image_path else "missing_scene_reference",
            "review_status": "in_review",
            "review_notes": "",
            "approval_notes": "",
            "reviewed_by": "",
            "reviewed_at": None,
            "owner": "",
            "review_checklist": [],
            "source_evidence": [],
            "last_verified_job_id": None,
            "usage_scope": "storyboard_audio_video",
            "continuity_guardrails": [],
            "notes": "",
        }
    ]
    if not scene_cards:
        scene_cards = build_scene_cards_template(source_title)
    return {
        "source_title": source_title,
        "character_cards": character_cards,
        "scene_cards": scene_cards,
    }


def load_asset_cards(pack_root: Path, *, source_title: str | None = None, asset_lock: AssetLock | None = None) -> dict[str, Any]:
    source_title = str(source_title or pack_root.name).strip() or pack_root.name
    asset_lock_model = asset_lock or load_asset_lock(pack_root)
    character_cards_path = pack_root / CHARACTER_CARDS_PATH
    scene_cards_path = pack_root / SCENE_CARDS_PATH

    if character_cards_path.exists():
        character_cards = json.loads(character_cards_path.read_text(encoding="utf-8"))
    else:
        character_cards = build_asset_cards_from_lock(source_title=source_title, asset_lock=asset_lock_model)["character_cards"]

    if scene_cards_path.exists():
        scene_cards = json.loads(scene_cards_path.read_text(encoding="utf-8"))
    else:
        scene_cards = build_asset_cards_from_lock(source_title=source_title, asset_lock=asset_lock_model)["scene_cards"]

    return {
        "source_title": source_title,
        "character_cards": [
            _normalize_character_card(item)
            for item in (character_cards if isinstance(character_cards, list) else build_character_cards_template(source_title))
            if isinstance(item, dict)
        ],
        "scene_cards": [
            _normalize_scene_card(item)
            for item in (scene_cards if isinstance(scene_cards, list) else build_scene_cards_template(source_title))
            if isinstance(item, dict)
        ],
    }


def ensure_asset_lock_scaffold(pack_root: Path, *, source_title: str) -> Path:
    for relative_dir in ASSET_LOCK_DIRECTORIES:
        (pack_root / relative_dir).mkdir(parents=True, exist_ok=True)
    asset_lock_path = pack_root / ASSET_LOCK_FILENAME
    if not asset_lock_path.exists():
        asset_lock_path.write_text(
            json.dumps(build_asset_lock_template(source_title), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    asset_cards = load_asset_cards(pack_root, source_title=source_title)
    character_cards_path = pack_root / CHARACTER_CARDS_PATH
    scene_cards_path = pack_root / SCENE_CARDS_PATH
    if not character_cards_path.exists():
        character_cards_path.write_text(json.dumps(asset_cards["character_cards"], ensure_ascii=False, indent=2), encoding="utf-8")
    if not scene_cards_path.exists():
        scene_cards_path.write_text(json.dumps(asset_cards["scene_cards"], ensure_ascii=False, indent=2), encoding="utf-8")
    return asset_lock_path
