from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.core.config import Settings, get_settings


@dataclass(slots=True)
class ArkVideoOptions:
    duration_seconds: int = 5
    ratio: str = "16:9"
    resolution: str = "720p"
    poll_interval_seconds: int = 8
    max_wait_seconds: int = 600


class ArkRuntimeClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.ark_api_key:
            raise RuntimeError("ARK_API_KEY is missing.")

        try:
            from volcenginesdkarkruntime import Ark
        except ImportError as exc:
            raise RuntimeError(
                "Missing Ark SDK dependency. Install with: pip install 'volcengine-python-sdk[ark]'"
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": self.settings.ark_api_key}
        if self.settings.ark_base_url:
            client_kwargs["base_url"] = self.settings.ark_base_url
        self.client = Ark(**client_kwargs)

    def generate_text(
        self,
        *,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=model or self.settings.ark_text_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = self._read_text_response(response)
        if not content:
            raise RuntimeError("Ark text generation returned empty content.")
        return content

    def generate_video_to_file(
        self,
        *,
        prompt: str,
        output_path: Path,
        model: str | None = None,
        options: ArkVideoOptions | None = None,
    ) -> Path:
        resolved_options = options or ArkVideoOptions()
        task = self.client.content_generation.tasks.create(
            model=model or self.settings.ark_video_model,
            content=[{"type": "text", "text": prompt}],
            ratio=resolved_options.ratio,
            resolution=resolved_options.resolution,
            duration=resolved_options.duration_seconds,
            watermark=False,
        )
        task_id = self._read_obj(task, "id")
        if not task_id:
            raise RuntimeError("Ark video generation returned empty task id.")

        remaining_polls = max(1, resolved_options.max_wait_seconds // resolved_options.poll_interval_seconds)
        for _ in range(remaining_polls):
            result = self.client.content_generation.tasks.get(task_id=task_id)
            status = str(self._read_obj(result, "status") or "").lower()
            if status in {"succeeded", "success", "completed", "done"}:
                content_obj = self._read_obj(result, "content")
                video_url = self._read_obj(content_obj, "video_url") or self._read_obj(content_obj, "file_url")
                if not video_url:
                    raise RuntimeError("Ark video task succeeded but no video URL returned.")
                self._download_to_file(url=str(video_url), output_path=output_path)
                return output_path
            if status in {"failed", "cancelled", "canceled"}:
                error_obj = self._read_obj(result, "error")
                error_message = self._read_obj(error_obj, "message") or "unknown error"
                raise RuntimeError(f"Ark video task failed: {error_message}")

        raise TimeoutError("Ark video generation timed out.")

    def generate_image_to_file(
        self,
        *,
        prompt: str,
        output_path: Path,
        model: str | None = None,
        size: str = "1024x1024",
    ) -> Path:
        response = self.client.images.generate(
            model=model or self.settings.ark_image_model,
            prompt=prompt,
            size=size,
            response_format="b64_json",
        )
        self._write_image_response(output_path=output_path, response=response)
        return output_path

    @staticmethod
    def _download_to_file(*, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        response = httpx.get(url, timeout=120.0, follow_redirects=True)
        response.raise_for_status()
        output_path.write_bytes(response.content)

    def _write_image_response(self, *, output_path: Path, response: object) -> None:
        import base64

        output_path.parent.mkdir(parents=True, exist_ok=True)
        data_items = self._read_obj(response, "data") or []
        if not data_items:
            raise RuntimeError("Ark image response has no data items.")

        item = data_items[0]
        b64_payload = self._read_obj(item, "b64_json")
        image_url = self._read_obj(item, "url")

        if b64_payload:
            output_path.write_bytes(base64.b64decode(b64_payload))
            return
        if image_url:
            self._download_to_file(url=str(image_url), output_path=output_path)
            return
        raise RuntimeError("Ark image response has no b64_json or URL payload.")

    @staticmethod
    def _read_obj(obj: object, key: str):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

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


def build_ark_runtime_client(settings: Settings | None = None) -> ArkRuntimeClient:
    return ArkRuntimeClient(settings or get_settings())
