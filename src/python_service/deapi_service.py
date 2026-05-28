from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests


DEAPI_BASE_URL = os.getenv("DEAPI_BASE_URL", "https://api.deapi.ai").rstrip("/")
DEAPI_API_KEY_ENV = "DEAPI_API_KEY"
DEFAULT_DEAPI_MUSIC_MODEL = os.getenv("DEAPI_MUSIC_MODEL", "AceStep_1_5_Turbo")
DEFAULT_DEAPI_MUSIC_FORMAT = os.getenv("DEAPI_MUSIC_FORMAT", "wav")
DEFAULT_DEAPI_INFERENCE_STEPS = int(os.getenv("DEAPI_INFERENCE_STEPS", "8"))
DEFAULT_DEAPI_GUIDANCE_SCALE = float(os.getenv("DEAPI_GUIDANCE_SCALE", "1"))
DEFAULT_DEAPI_SEED = int(os.getenv("DEAPI_SEED", "-1"))
DEAPI_POLL_INTERVAL_SECONDS = float(os.getenv("DEAPI_POLL_INTERVAL_SECONDS", "3"))
DEAPI_TIMEOUT_SECONDS = int(os.getenv("DEAPI_TIMEOUT_SECONDS", "300"))

CONTENT_TYPE_EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/ogg": ".ogg",
}


class DeapiError(RuntimeError):
    """Raised when deAPI cannot complete a music generation request."""


def get_api_key() -> str:
    api_key = os.getenv(DEAPI_API_KEY_ENV, "").strip()
    if not api_key:
        raise DeapiError(
            "DEAPI_API_KEY is not configured. Create a key at "
            "https://app.deapi.ai/settings/api-keys and set it before using music_provider='deapi'."
        )

    return api_key


def auth_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_api_key()}",
    }


def request_json(method: str, path: str, **kwargs) -> dict:
    response = requests.request(
        method,
        f"{DEAPI_BASE_URL}{path}",
        headers=auth_headers(),
        timeout=60,
        **kwargs,
    )

    if response.status_code >= 400:
        raise DeapiError(f"deAPI request failed ({response.status_code}): {response.text}")

    try:
        return response.json()
    except ValueError as exc:
        raise DeapiError("deAPI returned a non-JSON response.") from exc


def extract_data(payload: dict) -> dict:
    data = payload.get("data", {})
    return data if isinstance(data, dict) else {}


def submit_music_job(
    *,
    caption: str,
    lyrics: str,
    duration_seconds: int,
    model: str | None,
    inference_steps: int,
    guidance_scale: float,
    seed: int,
    audio_format: str,
    bpm: int | None = None,
    keyscale: str | None = None,
    timesignature: int | None = None,
    vocal_language: str | None = None,
) -> str:
    fields: dict[str, str] = {
        "caption": caption,
        "model": model or DEFAULT_DEAPI_MUSIC_MODEL,
        "lyrics": lyrics,
        "duration": str(duration_seconds),
        "inference_steps": str(inference_steps),
        "guidance_scale": str(guidance_scale),
        "seed": str(seed),
        "format": audio_format,
    }

    optional_fields = {
        "bpm": bpm,
        "keyscale": keyscale,
        "timesignature": timesignature,
        "vocal_language": vocal_language,
    }
    for key, value in optional_fields.items():
        if value is not None and str(value).strip():
            fields[key] = str(value)

    multipart_fields = [(key, (None, value)) for key, value in fields.items()]
    payload = request_json("POST", "/api/v2/audio/music", files=multipart_fields)
    request_id = extract_data(payload).get("request_id")

    if not request_id:
        raise DeapiError("deAPI did not return a request_id.")

    return str(request_id)


def get_job_result(request_id: str) -> dict:
    payload = request_json("GET", f"/api/v2/jobs/{request_id}")
    return extract_data(payload)


def resolve_result_url(job_data: dict) -> str | None:
    for key in ("result_url", "result"):
        value = job_data.get(key)
        if isinstance(value, str) and value:
            return value

    alt_formats = job_data.get("results_alt_formats")
    if isinstance(alt_formats, dict):
        for value in alt_formats.values():
            if isinstance(value, str) and value:
                return value

    return None


def wait_for_result_url(request_id: str) -> str:
    deadline = time.monotonic() + DEAPI_TIMEOUT_SECONDS
    last_status = "unknown"

    while time.monotonic() < deadline:
        job_data = get_job_result(request_id)
        last_status = str(job_data.get("status", last_status)).lower()
        result_url = resolve_result_url(job_data)

        if result_url and last_status in {"done", "completed", "succeeded", "success"}:
            return result_url

        if result_url and last_status not in {"pending", "processing", "queued", "running"}:
            return result_url

        if last_status in {"failed", "error", "cancelled", "canceled"}:
            raise DeapiError(f"deAPI job {request_id} failed with status '{last_status}'.")

        time.sleep(DEAPI_POLL_INTERVAL_SECONDS)

    raise DeapiError(
        f"Timed out waiting for deAPI job {request_id} after {DEAPI_TIMEOUT_SECONDS} seconds "
        f"(last status: {last_status})."
    )


def suffix_from_url_or_content_type(result_url: str, content_type: str, fallback_format: str) -> str:
    url_suffix = Path(urlparse(result_url).path).suffix.lower()
    if url_suffix:
        return url_suffix

    content_type_base = content_type.split(";", maxsplit=1)[0].strip().lower()
    if content_type_base in CONTENT_TYPE_EXTENSIONS:
        return CONTENT_TYPE_EXTENSIONS[content_type_base]

    clean_format = fallback_format.strip().lower().lstrip(".")
    return f".{clean_format or DEFAULT_DEAPI_MUSIC_FORMAT}"


def download_result(result_url: str, output_dir: Path, requested_format: str) -> str:
    response = requests.get(result_url, stream=True, timeout=120)
    if response.status_code >= 400:
        raise DeapiError(f"Unable to download deAPI audio ({response.status_code}).")

    suffix = suffix_from_url_or_content_type(
        result_url,
        response.headers.get("Content-Type", ""),
        requested_format,
    )
    file_name = f"{uuid4().hex}{suffix}"
    file_path = output_dir / file_name

    with open(file_path, "wb") as audio_file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                audio_file.write(chunk)

    return file_name


def generate_music_file(
    *,
    caption: str,
    lyrics: str,
    duration_seconds: int,
    output_dir: Path,
    model: str | None = None,
    inference_steps: int = DEFAULT_DEAPI_INFERENCE_STEPS,
    guidance_scale: float = DEFAULT_DEAPI_GUIDANCE_SCALE,
    seed: int = DEFAULT_DEAPI_SEED,
    audio_format: str = DEFAULT_DEAPI_MUSIC_FORMAT,
    bpm: int | None = None,
    keyscale: str | None = None,
    timesignature: int | None = None,
    vocal_language: str | None = None,
) -> tuple[str, str]:
    request_id = submit_music_job(
        caption=caption,
        lyrics=lyrics,
        duration_seconds=duration_seconds,
        model=model,
        inference_steps=inference_steps,
        guidance_scale=guidance_scale,
        seed=seed,
        audio_format=audio_format,
        bpm=bpm,
        keyscale=keyscale,
        timesignature=timesignature,
        vocal_language=vocal_language,
    )
    result_url = wait_for_result_url(request_id)
    file_name = download_result(result_url, output_dir, audio_format)
    return file_name, request_id


def get_music_models() -> dict:
    return request_json("GET", "/api/v2/models?filter[inference_types]=txt2music")


def get_balance() -> dict:
    return request_json("GET", "/api/v2/account/balance")
