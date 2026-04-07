import base64
import os
import time
from pathlib import Path
from typing import Iterable

import requests

from shared.providers.model_usage import (
    ModelUsageManager,
    estimate_text_tokens_from_messages,
    estimate_text_tokens_from_text,
)


class ArkProvider:
    DEFAULT_IMAGE_MODEL = "Doubao-Seedream-4.5"
    DEFAULT_VIDEO_MODEL = "Doubao-Seedance-1.5-pro"
    DEFAULT_TEXT_MODEL = "Doubao-Seed-1.6"
    DEFAULT_BRIEF_TEXT_MODEL = "Doubao-Seed-1.6"
    DEFAULT_STORYBOARD_TEXT_MODEL = "Doubao-Seed-1.6"
    DEFAULT_LEAD_IMAGE_MODEL = "Doubao-Seedream-4.5"
    DEFAULT_KEYFRAME_IMAGE_MODEL = "Doubao-Seedream-4.5"

    # Fallbacks are kept to improve compatibility across model alias/version naming.
    # Requested defaults follow the preferred business order first, then fall back to
    # dated aliases or lower-cost variants for compatibility.
    IMAGE_MODEL_FALLBACKS = (
        "doubao-seedream-4-5-251128",
        "doubao-seedream-5-0-lite-260128",
        "doubao-seedream-5-0-260128",
        "doubao-seedream-4-0-250828",
    )
    VIDEO_MODEL_FALLBACKS = (
        "doubao-seedance-1-5-pro-251215",
        "Doubao-Seedance-1.0-pro",
        "doubao-seedance-1-0-pro-250528",
    )
    TEXT_MODEL_FALLBACKS = (
        "doubao-seed-1-6-251015",
        "doubao-seed-1.6",
        "doubao-seed-1.6-flash",
        "doubao-seed-2-0-lite-260215",
        "doubao-seed-2-0-mini-260215",
        "doubao-seed-2-0-pro-260215",
    )

    def __init__(
        self,
        api_key: str,
        image_model: str = DEFAULT_IMAGE_MODEL,
        video_model: str = DEFAULT_VIDEO_MODEL,
        text_model: str = DEFAULT_TEXT_MODEL,
    ):
        if not api_key or not api_key.strip():
            raise ValueError("ARK API key is empty")

        try:
            from volcenginesdkarkruntime import Ark
        except ImportError as exc:
            raise RuntimeError(
                "Missing Ark SDK dependency. Install with: pip install 'volcengine-python-sdk[ark]'"
            ) from exc

        self.api_key = api_key.strip()
        self.image_model = image_model
        self.video_model = video_model
        self.text_model = text_model
        self.client = Ark(api_key=self.api_key)
        self.usage_manager = ModelUsageManager()
        self.last_video_task_details: dict[str, object] = {}

    @classmethod
    def from_local_secrets(
        cls,
        root_dir: Path,
        image_model: str = DEFAULT_IMAGE_MODEL,
        video_model: str = DEFAULT_VIDEO_MODEL,
        text_model: str = DEFAULT_TEXT_MODEL,
    ) -> "ArkProvider | None":
        env_key = os.getenv("ARK_API_KEY") or os.getenv("VOLC_ARK_API_KEY")
        if env_key:
            return cls(env_key, image_model=image_model, video_model=video_model, text_model=text_model)

        key_path = root_dir / "secrets" / "ark_api_key.txt"
        if key_path.exists():
            key = key_path.read_text(encoding="utf-8").strip()
            if key:
                return cls(key, image_model=image_model, video_model=video_model, text_model=text_model)

        return None

    def generate_text(
        self,
        *,
        messages: list[dict],
        text_model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> str:
        requested_model = str(text_model or self.text_model).strip() or self.text_model
        input_tokens = estimate_text_tokens_from_messages(messages)
        estimated_cost = input_tokens + min(max(200, input_tokens // 2), max_tokens)
        routing = self.usage_manager.plan_call(
            provider="ark",
            capability="text",
            primary=requested_model,
            fallbacks=self.TEXT_MODEL_FALLBACKS,
            estimated_cost=estimated_cost,
        )

        last_error: Exception | None = None
        for model in routing.candidates:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = self._read_text_response(response)
                if not content:
                    raise RuntimeError("Ark text generation returned empty content")
                usage_obj = self._read_obj(response, "usage")
                official_input_tokens = self._safe_int(self._read_obj(usage_obj, "prompt_tokens")) or input_tokens
                output_tokens = self._safe_int(self._read_obj(usage_obj, "completion_tokens")) or estimate_text_tokens_from_text(content)
                self.usage_manager.record_success(
                    provider="ark",
                    capability="text",
                    model=model,
                    input_tokens=official_input_tokens,
                    output_tokens=output_tokens,
                )
                self.text_model = model
                return content
            except Exception as exc:
                last_error = exc
                retryable = self._looks_like_retryable_model_unavailable(exc)
                self.usage_manager.record_failure(
                    provider="ark",
                    capability="text",
                    model=model,
                    error_message=str(exc),
                    input_tokens=input_tokens,
                    quota_like=self._looks_like_quota_error(exc),
                )
                if retryable:
                    continue
                break

        if last_error is not None:
            raise RuntimeError(f"Ark text generation failed: {last_error}") from last_error
        raise RuntimeError("Ark text generation failed with unknown error")

    def generate_image_to_file(
        self,
        prompt: str,
        output_path: Path,
        width: int = 1024,
        height: int = 1024,
        image_model: str | None = None,
    ) -> Path:
        normalized_width, normalized_height = self._normalize_image_size(width=width, height=height)
        size = f"{normalized_width}x{normalized_height}"
        requested_model = str(image_model or self.image_model).strip() or self.image_model
        model_candidates = self._candidate_models(
            primary=requested_model,
            fallbacks=self.IMAGE_MODEL_FALLBACKS,
        )
        routing = self.usage_manager.plan_call(
            provider="ark",
            capability="image",
            primary=requested_model,
            fallbacks=model_candidates[1:],
            estimated_cost=1.0,
        )

        last_error: Exception | None = None
        for model in routing.candidates:
            try:
                response = self.client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
                    response_format="b64_json",
                )
                self._write_image_response(output_path=output_path, response=response)
                self.usage_manager.record_success(
                    provider="ark",
                    capability="image",
                    model=model,
                    cost_value=1.0,
                )
                self.image_model = model
                return output_path
            except Exception as exc:
                last_error = exc
                self.usage_manager.record_failure(
                    provider="ark",
                    capability="image",
                    model=model,
                    error_message=str(exc),
                    cost_value=1.0,
                    quota_like=self._looks_like_quota_error(exc),
                )
                if not self._looks_like_retryable_model_unavailable(exc):
                    break

        if last_error is not None:
            raise RuntimeError(f"Ark image generation failed: {last_error}") from last_error
        raise RuntimeError("Ark image generation failed with unknown error")

    def generate_video_to_file(
        self,
        prompt: str,
        output_path: Path,
        *,
        image_paths: Iterable[Path] | None = None,
        image_roles: Iterable[str] | None = None,
        video_model: str | None = None,
        duration_seconds: int = 5,
        ratio: str = "16:9",
        resolution: str = "720p",
        generate_audio: bool | None = None,
        return_last_frame: bool = False,
        camera_fixed: bool | None = None,
        draft: bool | None = None,
        max_wait_seconds: int = 600,
        poll_interval_seconds: int = 8,
    ) -> Path:
        requested_model = str(video_model or self.video_model).strip() or self.video_model
        model_candidates = self._candidate_models(
            primary=requested_model,
            fallbacks=self.VIDEO_MODEL_FALLBACKS,
        )
        routing = self.usage_manager.plan_call(
            provider="ark",
            capability="video",
            primary=requested_model,
            fallbacks=model_candidates[1:],
            estimated_cost=1.0,
        )
        prompt_candidates = self._build_video_prompt_candidates(prompt)
        image_payloads = self._build_video_image_payloads(image_paths=image_paths, image_roles=image_roles)
        if not prompt_candidates and image_payloads:
            prompt_candidates = [""]
        last_error: Exception | None = None

        for model in routing.candidates:
            for prompt_text in prompt_candidates:
                try:
                    content_items = self._build_video_content(prompt=prompt_text, image_payloads=image_payloads)
                    task = self.client.content_generation.tasks.create(
                        model=model,
                        content=content_items,
                        ratio=ratio,
                        resolution=resolution,
                        duration=duration_seconds,
                        generate_audio=generate_audio,
                        return_last_frame=return_last_frame,
                        camera_fixed=camera_fixed,
                        draft=draft,
                        watermark=False,
                    )
                    task_id = self._read_obj(task, "id")
                    if not task_id:
                        raise RuntimeError("Ark returned empty task id for video generation")

                    deadline = time.time() + max_wait_seconds
                    while time.time() < deadline:
                        result = self.client.content_generation.tasks.get(task_id=task_id)
                        status = str(self._read_obj(result, "status") or "").lower()
                        if status in {"succeeded", "success", "completed", "done"}:
                            content_obj = self._read_obj(result, "content")
                            video_url = (
                                self._read_obj(content_obj, "video_url")
                                or self._read_obj(content_obj, "file_url")
                            )
                            if not video_url:
                                raise RuntimeError("Ark video task succeeded but no video URL returned")
                            self._download_to_file(url=video_url, output_path=output_path)
                            usage_obj = self._read_obj(result, "usage")
                            completion_tokens = self._safe_int(self._read_obj(usage_obj, "completion_tokens"))
                            input_tokens = estimate_text_tokens_from_text(prompt_text)
                            self.usage_manager.record_success(
                                provider="ark",
                                capability="video",
                                model=model,
                                input_tokens=input_tokens,
                                output_tokens=completion_tokens,
                            )
                            self.video_model = model
                            self.last_video_task_details = {
                                "task_id": task_id,
                                "model": model,
                                "content_mode": self._infer_video_content_mode(image_payloads=image_payloads),
                                "duration": self._read_obj(result, "duration") or duration_seconds,
                                "ratio": self._read_obj(result, "ratio") or ratio,
                                "resolution": self._read_obj(result, "resolution") or resolution,
                                "video_url": video_url,
                                "last_frame_url": self._read_obj(content_obj, "last_frame_url"),
                                "completion_tokens": completion_tokens,
                                "draft": bool(self._read_obj(result, "draft") or False),
                                "generate_audio": bool(generate_audio) if generate_audio is not None else False,
                            }
                            return output_path

                        if status in {"failed", "cancelled", "canceled"}:
                            error_obj = self._read_obj(result, "error")
                            error_msg = self._read_obj(error_obj, "message") or "unknown error"
                            raise RuntimeError(f"Ark video task failed: {error_msg}")

                        time.sleep(poll_interval_seconds)

                    raise TimeoutError("Ark video generation timed out")
                except Exception as exc:
                    last_error = exc
                    if self._looks_like_invalid_video_prompt(exc):
                        continue
                    self.usage_manager.record_failure(
                        provider="ark",
                        capability="video",
                        model=model,
                        error_message=str(exc),
                        cost_value=1.0,
                        quota_like=self._looks_like_quota_error(exc),
                    )
                    if not self._looks_like_retryable_model_unavailable(exc):
                        break
            else:
                continue
            if last_error is not None and not self._looks_like_retryable_model_unavailable(last_error):
                break

        if last_error is not None:
            raise RuntimeError(f"Ark video generation failed: {last_error}") from last_error
        raise RuntimeError("Ark video generation failed with unknown error")

    def _write_image_response(self, output_path: Path, response: object) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data_items = self._read_obj(response, "data") or []
        if not data_items:
            raise RuntimeError("Ark image response has no data items")

        item = data_items[0]
        b64_payload = self._read_obj(item, "b64_json")
        image_url = self._read_obj(item, "url")

        if b64_payload:
            output_path.write_bytes(base64.b64decode(b64_payload))
            return
        if image_url:
            self._download_to_file(url=image_url, output_path=output_path)
            return
        raise RuntimeError("Ark image response has no b64_json or URL payload")

    def _download_to_file(self, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        output_path.write_bytes(response.content)

    def _normalize_image_size(self, width: int, height: int) -> tuple[int, int]:
        min_pixels = 3_686_400
        w = max(1, int(width))
        h = max(1, int(height))
        if w * h >= min_pixels:
            return w, h

        scale = (min_pixels / float(w * h)) ** 0.5
        scaled_w = int(w * scale + 0.9999)
        scaled_h = int(h * scale + 0.9999)
        align = 64
        normalized_w = ((scaled_w + align - 1) // align) * align
        normalized_h = ((scaled_h + align - 1) // align) * align
        return normalized_w, normalized_h

    def _candidate_models(self, primary: str, fallbacks: Iterable[str]) -> list[str]:
        result: list[str] = []
        for model in [primary, *fallbacks]:
            value = str(model).strip()
            if value and value not in result:
                result.append(value)
        return result

    def _read_obj(self, obj: object, key: str):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _looks_like_model_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "model",
            "not found",
            "invalid model",
            "unsupported",
            "endpoint",
            "resource not found",
        )
        return any(marker in text for marker in markers)

    def _looks_like_quota_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "accountoverdueerror",
            "quota",
            "insufficient balance",
            "insufficient credit",
            "resource exhausted",
            "rate limit",
            "too many requests",
            "over limit",
            "余额",
            "欠费",
            "额度",
        )
        return any(marker in text for marker in markers)

    def _looks_like_retryable_model_unavailable(self, exc: Exception) -> bool:
        return self._looks_like_model_error(exc) or self._looks_like_quota_error(exc)

    def _looks_like_invalid_video_prompt(self, exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "invalid content.text",
            "content.text",
            "invalid parameter",
            "parameters specified in the request are not valid",
        )
        return any(marker in text for marker in markers)

    def _build_video_prompt_candidates(self, prompt: str) -> list[str]:
        base = " ".join(str(prompt or "").replace("\r", " ").replace("\n", " ").split())
        candidates: list[str] = []
        for item in (base, self._sanitize_video_prompt(base)):
            value = str(item or "").strip()
            if value and value not in candidates:
                candidates.append(value)
        return candidates

    def _sanitize_video_prompt(self, prompt: str) -> str:
        replacements = {
            "“": "\"",
            "”": "\"",
            "‘": "'",
            "’": "'",
            "—": "-",
            "–": "-",
        }
        text = str(prompt or "")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = "".join(ch for ch in text if ch == "\t" or ord(ch) >= 32)
        text = " ".join(text.split())
        if len(text) <= 600:
            return text
        truncated = text[:600].rsplit(" ", 1)[0].strip()
        return truncated or text[:600].strip()

    def _build_video_content(self, *, prompt: str, image_payloads: list[dict[str, object]]) -> list[dict[str, object]]:
        content: list[dict[str, object]] = []
        normalized_prompt = str(prompt or "").strip()
        if normalized_prompt:
            content.append({"type": "text", "text": normalized_prompt})
        content.extend(image_payloads)
        if not content:
            raise ValueError("Video generation requires text or image content")
        return content

    def _build_video_image_payloads(
        self,
        *,
        image_paths: Iterable[Path] | None,
        image_roles: Iterable[str] | None,
    ) -> list[dict[str, object]]:
        paths = [Path(item) for item in (image_paths or []) if str(item).strip()]
        if not paths:
            return []

        roles = [str(item).strip() for item in (image_roles or []) if str(item).strip()]
        if not roles:
            if len(paths) == 1:
                roles = ["first_frame"]
            elif len(paths) == 2:
                roles = ["first_frame", "last_frame"]
            else:
                roles = ["reference"] * len(paths)

        if len(roles) < len(paths):
            roles.extend([roles[-1] if roles else "reference"] * (len(paths) - len(roles)))

        payloads: list[dict[str, object]] = []
        for path, role in zip(paths, roles):
            payloads.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._path_to_data_url(path)},
                    "role": role or "reference",
                }
            )
        return payloads

    def _path_to_data_url(self, path: Path) -> str:
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        mime_type = self._guess_image_mime(path)
        return f"data:{mime_type};base64,{payload}"

    def _guess_image_mime(self, path: Path) -> str:
        suffix = path.suffix.lower()
        mapping = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mapping.get(suffix, "image/png")

    def _infer_video_content_mode(self, *, image_payloads: list[dict[str, object]]) -> str:
        if not image_payloads:
            return "text_to_video"
        roles = [str(item.get("role", "")).strip().lower() for item in image_payloads]
        if roles == ["first_frame"]:
            return "image_to_video_first_frame"
        if roles[:2] == ["first_frame", "last_frame"] and len(roles) == 2:
            return "image_to_video_first_last_frame"
        return "image_to_video_reference"

    def _safe_int(self, value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _read_text_response(self, response: object) -> str:
        choices = self._read_obj(response, "choices") or []
        if not choices:
            return ""

        message = self._read_obj(choices[0], "message")
        content = self._read_obj(message, "content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    text = self._read_obj(item, "text")
                    if text:
                        parts.append(str(text))
            return "\n".join(part for part in parts if part).strip()
        return str(content or "").strip()
