from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
import re
import shutil
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4
import wave

import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from audio_merge import export_mp3, mix_audio_files, save_wav
from deapi_service import (
    DEFAULT_DEAPI_GUIDANCE_SCALE,
    DEFAULT_DEAPI_INFERENCE_STEPS,
    DEFAULT_DEAPI_MUSIC_FORMAT,
    DEFAULT_DEAPI_MUSIC_MODEL,
    DEFAULT_DEAPI_SEED,
    DeapiError,
    generate_music_file as generate_deapi_music_file,
    get_balance as get_deapi_balance,
    get_music_models as get_deapi_music_models,
)
from musicgen_service import (
    DEFAULT_DURATION_SECONDS,
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    generate_music_file as generate_musicgen_file,
    load_music_model,
)


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MUSIC_MODEL_NAME = "facebook/musicgen-small"
BARK_MODEL_NAME = "suno/bark-small"
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 20
MAX_NEW_TOKENS = 1026
DEFAULT_MUSIC_GAIN_DB = -9.0
DEFAULT_SPEECH_GAIN_DB = 4.0
DEFAULT_LANGUAGE = "pt-PT"
DEFAULT_VOCAL_STYLE = "speech"
DEFAULT_MUSIC_PROVIDER = "local"
DEAPI_MIN_DURATION_SECONDS = 10
DEAPI_MAX_DURATION_SECONDS = 600
DEFAULT_BARK_VOICE_PRESETS = {
    "pt": "v2/pt_speaker_3",
    "en": "v2/en_speaker_6",
}
DEFAULT_PIPER_VOICE = "pt_PT-tug\u00E3o-medium"
PIPER_VOICE_ALIASES = {
    "pt_PT-tugao-medium": DEFAULT_PIPER_VOICE,
}
PIPER_VOICE_PATTERN = re.compile(
    r"^(?P<lang_family>[^-]+)_(?P<lang_region>[^-]+)-(?P<voice_name>[^-]+)-(?P<voice_quality>.+)$"
)
PIPER_LANGUAGE_DEFAULTS = {
    "pt": DEFAULT_PIPER_VOICE,
    "pt-pt": DEFAULT_PIPER_VOICE,
    "pt_pt": DEFAULT_PIPER_VOICE,
    "pt-br": "pt_BR-faber-medium",
    "pt_br": "pt_BR-faber-medium",
    "en": "en_US-lessac-medium",
    "en-us": "en_US-lessac-medium",
    "en_us": "en_US-lessac-medium",
}
PIPER_BASE_DIR = Path.home() / "AppData" / "Local" / "music_speech_service"
PIPER_VOICES_DIR = PIPER_BASE_DIR / "piper_voices"
PIPER_ESPEAK_DIR = PIPER_BASE_DIR / "piper_espeak_data"

app = FastAPI(title="Music and Speech Service")
xtts_model = None
xtts_speakers = None
bark_processor = None
bark_model = None
piper_voices = {}
device = "cuda" if torch.cuda.is_available() else "cpu"
generation_lock = Lock()


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Music prompt")
    duration_seconds: int = Field(
        8,
        ge=MIN_DURATION_SECONDS,
        le=DEAPI_MAX_DURATION_SECONDS,
        description="Approximate audio duration in seconds",
    )
    music_provider: str = Field(
        default=DEFAULT_MUSIC_PROVIDER,
        pattern="^(local|deapi)$",
        description="Music generation provider: local MusicGen or deAPI.",
    )
    deapi_model: str | None = Field(
        default=None,
        description="Optional deAPI model slug. If omitted, DEAPI_MUSIC_MODEL is used.",
    )
    deapi_lyrics: str = Field(
        default="[Instrumental]",
        min_length=1,
        description="Lyrics sent to deAPI. Use [Instrumental] for instrumental tracks.",
    )
    deapi_inference_steps: int = Field(
        default=DEFAULT_DEAPI_INFERENCE_STEPS,
        ge=1,
        le=100,
        description="deAPI music diffusion steps.",
    )
    deapi_guidance_scale: float = Field(
        default=DEFAULT_DEAPI_GUIDANCE_SCALE,
        ge=0,
        le=20,
        description="deAPI classifier-free guidance scale.",
    )
    deapi_seed: int = Field(default=DEFAULT_DEAPI_SEED, description="deAPI seed. Use -1 for random.")
    deapi_format: str = Field(
        default=DEFAULT_DEAPI_MUSIC_FORMAT,
        min_length=2,
        max_length=8,
        description="deAPI output format, for example wav, flac or mp3.",
    )
    deapi_bpm: int | None = Field(default=None, ge=30, le=300, description="Optional deAPI BPM.")
    deapi_keyscale: str | None = Field(
        default=None,
        description="Optional deAPI musical key, for example C major or F# minor.",
    )
    deapi_timesignature: int | None = Field(
        default=None,
        description="Optional deAPI time signature: 2, 3, 4 or 6.",
    )
    deapi_vocal_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        description="Optional deAPI vocal language code.",
    )


class GenerateSpeechMixRequest(BaseModel):
    music_prompt: str = Field(..., min_length=1, description="Prompt for MusicGen")
    lyrics: str = Field(..., min_length=1, description="Text to synthesize over the music")
    vocal_style: str = Field(
        default=DEFAULT_VOCAL_STYLE,
        pattern="^(speech|chant)$",
        description="Voice delivery style: speech or chant.",
    )
    duration_seconds: int = Field(
        DEFAULT_DURATION_SECONDS,
        ge=MIN_DURATION_SECONDS,
        le=DEAPI_MAX_DURATION_SECONDS,
        description="Approximate instrumental duration in seconds",
    )
    music_provider: str = Field(
        default=DEFAULT_MUSIC_PROVIDER,
        pattern="^(local|deapi)$",
        description="Music generation provider: local MusicGen or deAPI.",
    )
    deapi_model: str | None = Field(
        default=None,
        description="Optional deAPI model slug. If omitted, DEAPI_MUSIC_MODEL is used.",
    )
    deapi_inference_steps: int = Field(
        default=DEFAULT_DEAPI_INFERENCE_STEPS,
        ge=1,
        le=100,
        description="deAPI music diffusion steps.",
    )
    deapi_guidance_scale: float = Field(
        default=DEFAULT_DEAPI_GUIDANCE_SCALE,
        ge=0,
        le=20,
        description="deAPI classifier-free guidance scale.",
    )
    deapi_seed: int = Field(default=DEFAULT_DEAPI_SEED, description="deAPI seed. Use -1 for random.")
    deapi_format: str = Field(
        default=DEFAULT_DEAPI_MUSIC_FORMAT,
        min_length=2,
        max_length=8,
        description="deAPI output format, for example wav, flac or mp3.",
    )
    deapi_bpm: int | None = Field(default=None, ge=30, le=300, description="Optional deAPI BPM.")
    deapi_keyscale: str | None = Field(
        default=None,
        description="Optional deAPI musical key, for example C major or F# minor.",
    )
    deapi_timesignature: int | None = Field(
        default=None,
        description="Optional deAPI time signature: 2, 3, 4 or 6.",
    )
    deapi_vocal_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        description="Optional deAPI vocal language code.",
    )
    speech_engine: str = Field(
        default="piper",
        pattern="^(xtts|bark|piper)$",
        description="Speech engine to use: xtts, bark or piper",
    )
    vocal_delivery: str = Field(
        default="rhythmic",
        pattern="^(spoken|rhythmic|singing)$",
        description="Vocal delivery style. Bark handles rhythmic/singing better than Piper.",
    )
    language: str = Field(
        default=DEFAULT_LANGUAGE,
        min_length=2,
        max_length=10,
        description="Speech language code, for example pt-PT, pt-BR or en-US",
    )
    speaker_name: str | None = Field(
        default=None,
        description="Optional built-in speaker name for XTTS or voice preset for Bark",
    )
    speaker_wav_path: str | None = Field(
        default=None,
        description="Optional path to a local WAV file used for XTTS voice cloning",
    )
    music_gain_db: float = Field(
        default=DEFAULT_MUSIC_GAIN_DB,
        ge=-30.0,
        le=12.0,
        description="Gain applied to the instrumental before mixing",
    )
    speech_gain_db: float = Field(
        default=DEFAULT_SPEECH_GAIN_DB,
        ge=-12.0,
        le=18.0,
        description="Gain applied to the speech before mixing",
    )
    piper_voice: str | None = Field(
        default=None,
        description="Optional Piper voice code. If omitted, a default voice is chosen from language.",
    )
    piper_speaker_id: int | None = Field(
        default=None,
        ge=0,
        description="Optional speaker id for multi-speaker Piper voices",
    )
    piper_length_scale: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Piper speaking length scale. Higher is slower.",
    )
    piper_noise_scale: float = Field(
        default=0.667,
        ge=0.1,
        le=2.0,
        description="Piper noise scale. Lower is usually more stable.",
    )
    piper_noise_w_scale: float = Field(
        default=0.8,
        ge=0.1,
        le=2.0,
        description="Piper speaking variation scale.",
    )


class DependencyUnavailableError(RuntimeError):
    """Raised when an optional speech dependency is not available."""


@contextmanager
def trusted_torch_load():
    original_torch_load = torch.load

    def patched_torch_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_torch_load(*args, **kwargs)

    torch.load = patched_torch_load
    try:
        yield
    finally:
        torch.load = original_torch_load


def patch_xtts_transformers_compat() -> None:
    from TTS.tts.layers.xtts.gpt_inference import GPT2InferenceModel
    from transformers import GenerationConfig, GenerationMixin

    for attribute_name, attribute_value in GenerationMixin.__dict__.items():
        if attribute_name.startswith("__"):
            continue

        if not hasattr(GPT2InferenceModel, attribute_name):
            setattr(GPT2InferenceModel, attribute_name, attribute_value)

    if getattr(GPT2InferenceModel, "generation_config", None) is None:
        GPT2InferenceModel.generation_config = None


def load_xtts_speakers() -> list[str]:
    global xtts_speakers

    if xtts_speakers is not None:
        return xtts_speakers

    speaker_file = (
        Path.home()
        / "AppData"
        / "Local"
        / "tts"
        / "tts_models--multilingual--multi-dataset--xtts_v2"
        / "speakers_xtts.pth"
    )

    if not speaker_file.exists():
        xtts_speakers = []
        return xtts_speakers

    with trusted_torch_load():
        raw_speakers = torch.load(str(speaker_file), map_location="cpu")

    if isinstance(raw_speakers, dict):
        xtts_speakers = list(raw_speakers.keys())
    else:
        xtts_speakers = []

    return xtts_speakers


def load_xtts_model():
    global xtts_model

    if xtts_model is None:
        try:
            from TTS.api import TTS
        except ImportError as exc:
            raise DependencyUnavailableError(
                "XTTS is not available. Install 'TTS' in a Python 3.10 or 3.11 environment."
            ) from exc

        patch_xtts_transformers_compat()
        with trusted_torch_load():
            xtts_model = TTS(
                "tts_models/multilingual/multi-dataset/xtts_v2",
                gpu=torch.cuda.is_available(),
            )

        gpt_inference = xtts_model.synthesizer.tts_model.gpt.gpt_inference
        if getattr(gpt_inference, "generation_config", None) is None:
            from transformers import GenerationConfig

            gpt_inference.generation_config = GenerationConfig.from_model_config(
                gpt_inference.config
            )

    return xtts_model


def load_bark_model() -> None:
    global bark_processor, bark_model

    if bark_model is None:
        try:
            from transformers import AutoProcessor, BarkModel
        except ImportError as exc:
            raise DependencyUnavailableError(
                "Bark is not available in the installed transformers version."
            ) from exc

        bark_processor = AutoProcessor.from_pretrained(BARK_MODEL_NAME)
        bark_model = BarkModel.from_pretrained(BARK_MODEL_NAME)
        bark_model.to(device)
        bark_model.eval()


def ensure_piper_espeak_dir(package_espeak_dir: Path) -> Path:
    if not (PIPER_ESPEAK_DIR / "phontab").exists():
        PIPER_ESPEAK_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package_espeak_dir, PIPER_ESPEAK_DIR, dirs_exist_ok=True)

    return PIPER_ESPEAK_DIR


def normalize_language_code(language: str | None) -> str:
    language_code = (language or DEFAULT_LANGUAGE).strip()
    if not language_code:
        return DEFAULT_LANGUAGE

    return language_code.replace("_", "-")


def resolve_xtts_language(language: str) -> str:
    language_code = normalize_language_code(language).lower()
    if language_code.startswith("pt"):
        return "pt"

    if language_code.startswith("en"):
        return "en"

    return language_code.split("-", maxsplit=1)[0]


def resolve_piper_voice(language: str, requested_voice: str | None) -> str:
    if requested_voice and requested_voice.strip():
        return PIPER_VOICE_ALIASES.get(requested_voice.strip(), requested_voice.strip())

    language_code = normalize_language_code(language).lower()
    return PIPER_LANGUAGE_DEFAULTS.get(
        language_code,
        PIPER_LANGUAGE_DEFAULTS.get(language_code.split("-", maxsplit=1)[0], DEFAULT_PIPER_VOICE),
    )


def resolve_bark_voice_preset(language: str, requested_speaker: str | None) -> str | None:
    if requested_speaker and requested_speaker.strip():
        return requested_speaker.strip()

    language_code = resolve_xtts_language(language)
    return DEFAULT_BARK_VOICE_PRESETS.get(language_code)


def build_piper_voice_urls(voice_code: str) -> tuple[str, str]:
    voice_match = PIPER_VOICE_PATTERN.match(voice_code)
    if not voice_match:
        raise ValueError(
            "Invalid Piper voice code. Expected format like 'pt_PT-tugao-medium' or "
            "'en_US-lessac-medium'."
        )

    lang_family = voice_match.group("lang_family")
    lang_code = f"{lang_family}_{voice_match.group('lang_region')}"
    voice_name = voice_match.group("voice_name")
    voice_quality = voice_match.group("voice_quality")

    encoded_voice_name = quote(voice_name, safe="")
    encoded_voice_code = quote(voice_code, safe="-_.")
    base_url = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        f"{lang_family}/{lang_code}/{encoded_voice_name}/{voice_quality}/{encoded_voice_code}"
    )
    return f"{base_url}.onnx?download=true", f"{base_url}.onnx.json?download=true"


def download_file_if_missing(file_path: Path, source_url: str) -> None:
    if file_path.exists() and file_path.stat().st_size > 0:
        return

    with urlopen(source_url) as response:
        with open(file_path, "wb") as destination_file:
            shutil.copyfileobj(response, destination_file)


def download_piper_voice_files(voice_code: str, download_dir: Path) -> None:
    try:
        model_url, config_url = build_piper_voice_urls(voice_code)
        download_file_if_missing(download_dir / f"{voice_code}.onnx", model_url)
        download_file_if_missing(download_dir / f"{voice_code}.onnx.json", config_url)
    except ValueError:
        raise
    except (HTTPError, URLError) as exc:
        raise ValueError(
            f"Unable to download Piper voice '{voice_code}'. "
            "Try one of: pt_PT-tug\u00E3o-medium, pt_BR-faber-medium, en_US-lessac-medium."
        ) from exc


def load_piper_voice(voice_code: str):
    voice_key = voice_code.strip()
    if not voice_key:
        raise ValueError("piper_voice is required when speech_engine is 'piper'")

    if voice_key in piper_voices:
        return piper_voices[voice_key]

    try:
        from piper import PiperVoice
        from piper.phonemize_espeak import ESPEAK_DATA_DIR as PACKAGE_ESPEAK_DATA_DIR
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Piper is not available. Install 'piper-tts' in this environment."
        ) from exc

    PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    download_piper_voice_files(voice_key, PIPER_VOICES_DIR)
    espeak_dir = ensure_piper_espeak_dir(Path(PACKAGE_ESPEAK_DATA_DIR))
    model_path = PIPER_VOICES_DIR / f"{voice_key}.onnx"

    piper_voices[voice_key] = PiperVoice.load(
        model_path=model_path,
        espeak_data_dir=espeak_dir,
    )
    return piper_voices[voice_key]


def build_audio_url(request: Request, file_name: str) -> str:
    return str(request.base_url).rstrip("/") + f"/audio/{file_name}"


def validate_music_provider_duration(music_provider: str, duration_seconds: int) -> None:
    if music_provider == "local" and duration_seconds > MAX_DURATION_SECONDS:
        raise ValueError(
            f"Local MusicGen duration must be between {MIN_DURATION_SECONDS} and "
            f"{MAX_DURATION_SECONDS} seconds. Use music_provider='deapi' for longer tracks."
        )

    if music_provider == "deapi" and duration_seconds < DEAPI_MIN_DURATION_SECONDS:
        raise ValueError(
            f"deAPI music duration must be between {DEAPI_MIN_DURATION_SECONDS} and "
            f"{DEAPI_MAX_DURATION_SECONDS} seconds."
        )


def validate_deapi_timesignature(timesignature: int | None) -> None:
    if timesignature is not None and timesignature not in {2, 3, 4, 6}:
        raise ValueError("deapi_timesignature must be 2, 3, 4 or 6.")


def convert_audio_to_wav(source_path: Path, wav_path: Path) -> None:
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise RuntimeError("pydub is required to convert deAPI audio for mixing.") from exc

    audio = AudioSegment.from_file(str(source_path))
    audio.export(str(wav_path), format="wav")


def generate_deapi_music_bundle(
    data: GenerateRequest | GenerateSpeechMixRequest,
    *,
    prompt: str,
    lyrics: str,
) -> tuple[str, str]:
    validate_deapi_timesignature(data.deapi_timesignature)
    return generate_deapi_music_file(
        caption=prompt,
        lyrics=lyrics,
        duration_seconds=data.duration_seconds,
        output_dir=OUTPUT_DIR,
        model=data.deapi_model or DEFAULT_DEAPI_MUSIC_MODEL,
        inference_steps=data.deapi_inference_steps,
        guidance_scale=data.deapi_guidance_scale,
        seed=data.deapi_seed,
        audio_format=data.deapi_format,
        bpm=data.deapi_bpm,
        keyscale=data.deapi_keyscale,
        timesignature=data.deapi_timesignature,
        vocal_language=data.deapi_vocal_language,
    )


def resolve_speaker_file(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    file_path = Path(path_value).expanduser()
    if not file_path.is_absolute():
        file_path = (BASE_DIR / file_path).resolve()

    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Speaker reference file was not found: {file_path}")

    return file_path


def prepare_bark_text(text: str, vocal_style: str) -> str:
    cleaned_lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    cleaned_lines = [line for line in cleaned_lines if line]

    if not cleaned_lines:
        fallback_text = re.sub(r"\s+", " ", text).strip()
        return fallback_text

    if vocal_style == "speech":
        return " ".join(cleaned_lines)

    return "\n".join(cleaned_lines)


def resolve_xtts_speaker(model_instance, requested_speaker: str | None) -> str | None:
    raw_speakers = getattr(model_instance, "speakers", None) or []

    if isinstance(raw_speakers, dict):
        speakers = list(raw_speakers.keys())
    else:
        speakers = list(raw_speakers)

    if not speakers:
        speakers = load_xtts_speakers()

    if requested_speaker:
        if requested_speaker not in speakers:
            raise ValueError(
                f"Unknown XTTS speaker '{requested_speaker}'. Available speakers: {', '.join(speakers)}"
            )
        return requested_speaker
    return None


def generate_xtts_file(
    text: str,
    language: str,
    file_path: Path,
    speaker_name: str | None,
    speaker_wav_path: str | None,
) -> dict[str, str | None]:
    xtts = load_xtts_model()
    speaker_file = resolve_speaker_file(speaker_wav_path)
    kwargs = {
        "text": text,
        "language": resolve_xtts_language(language),
        "file_path": str(file_path),
        "split_sentences": True,
    }

    if speaker_file is not None:
        kwargs["speaker_wav"] = [str(speaker_file)]
        resolved_speaker = None
    else:
        resolved_speaker = resolve_xtts_speaker(xtts, speaker_name)
        if resolved_speaker is None:
            raise ValueError(
                "XTTS without speaker_wav_path is unreliable in this setup. "
                "Provide speaker_wav_path for a clean Portuguese reference voice, "
                "or set speaker_name explicitly if you still want to test a built-in XTTS speaker."
            )
        kwargs["speaker"] = resolved_speaker

    xtts.tts_to_file(**kwargs)
    return {
        "speech_engine": "xtts",
        "speaker_name": resolved_speaker,
        "speaker_wav_path": str(speaker_file) if speaker_file else None,
    }


def split_lyrics_into_bars(text: str, max_words_per_bar: int = 5) -> list[str]:
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []

    phrases = [
        phrase.strip()
        for phrase in re.split(r"[,;:.!?/|]+", normalized_text)
        if phrase.strip()
    ]

    bars = []
    for phrase in phrases:
        words = phrase.split()
        for index in range(0, len(words), max_words_per_bar):
            bar = " ".join(words[index : index + max_words_per_bar]).strip()
            if bar:
                bars.append(bar)

    return bars or [normalized_text]


def prepare_vocal_text(text: str, speech_engine: str, vocal_delivery: str) -> str:
    clean_text = " ".join(text.split())
    if vocal_delivery == "spoken":
        return clean_text

    bars = split_lyrics_into_bars(clean_text)
    if speech_engine == "bark":
        style_prompt = "[singing]" if vocal_delivery == "singing" else "[rhythmic rap vocals]"
        return f"{style_prompt}\n" + "\n".join(bars)

    return ". ".join(bars) + "."


def generate_bark_file(
    text: str,
    language: str,
    file_path: Path,
    speaker_name: str | None,
    vocal_style: str,
) -> dict[str, str | None]:
    load_bark_model()

    processor_kwargs = {}
    resolved_speaker_name = resolve_bark_voice_preset(language, speaker_name)
    if resolved_speaker_name:
        processor_kwargs["voice_preset"] = resolved_speaker_name

    prepared_text = prepare_bark_text(text, vocal_style)
    inputs = bark_processor(prepared_text, **processor_kwargs)
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        audio_values = bark_model.generate(**inputs)

    audio = audio_values.cpu().numpy().squeeze()
    sampling_rate = bark_model.generation_config.sample_rate
    save_wav(file_path, sampling_rate, audio)

    return {
        "speech_engine": "bark",
        "speaker_name": resolved_speaker_name,
        "speaker_wav_path": None,
    }


def generate_piper_file(
    text: str,
    file_path: Path,
    piper_voice_code: str,
    piper_speaker_id: int | None,
    piper_length_scale: float,
    piper_noise_scale: float,
    piper_noise_w_scale: float,
) -> dict[str, str | None]:
    from piper import SynthesisConfig

    voice = load_piper_voice(piper_voice_code)
    synthesis_config = SynthesisConfig(
        speaker_id=piper_speaker_id,
        length_scale=piper_length_scale,
        noise_scale=piper_noise_scale,
        noise_w_scale=piper_noise_w_scale,
        normalize_audio=True,
        volume=1.0,
    )

    with wave.open(str(file_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=synthesis_config)

    return {
        "speech_engine": "piper",
        "speaker_name": piper_voice_code,
        "speaker_wav_path": None,
    }


def generate_speech_file(
    text: str,
    vocal_style: str,
    language: str,
    speech_engine: str,
    vocal_delivery: str,
    file_path: Path,
    speaker_name: str | None,
    speaker_wav_path: str | None,
    piper_voice: str | None,
    piper_speaker_id: int | None,
    piper_length_scale: float,
    piper_noise_scale: float,
    piper_noise_w_scale: float,
) -> dict[str, str | None]:
    if vocal_style == "chant" and speech_engine != "bark":
        raise ValueError(
            "vocal_style='chant' is currently only supported with speech_engine='bark'. "
            "Use Bark for lyric-style delivery, or keep vocal_style='speech' with Piper/XTTS."
        )

    prepared_text = prepare_vocal_text(text, speech_engine, vocal_delivery)

    if speech_engine == "piper":
        return generate_piper_file(
            text=prepared_text,
            file_path=file_path,
            piper_voice_code=resolve_piper_voice(language, piper_voice),
            piper_speaker_id=piper_speaker_id,
            piper_length_scale=piper_length_scale,
            piper_noise_scale=piper_noise_scale,
            piper_noise_w_scale=piper_noise_w_scale,
        )

    if speech_engine == "bark":
        return generate_bark_file(
            text=prepared_text,
            language=language,
            file_path=file_path,
            speaker_name=speaker_name,
            vocal_style=vocal_style,
        )

    return generate_xtts_file(
        text=prepared_text,
        language=language,
        file_path=file_path,
        speaker_name=speaker_name,
        speaker_wav_path=speaker_wav_path,
    )


def generate_mix_bundle(data: GenerateSpeechMixRequest) -> dict[str, str | None]:
    music_prompt = data.music_prompt.strip()
    lyrics = data.lyrics.strip()
    validate_music_provider_duration(data.music_provider, data.duration_seconds)

    bundle_id = uuid4().hex
    music_file_name = f"{bundle_id}-music.wav"
    vocal_file_name = f"{bundle_id}-vocal.wav"
    mixed_wav_file_name = f"{bundle_id}-mix.wav"
    final_file_name = f"{bundle_id}.mp3"

    music_file_path = OUTPUT_DIR / music_file_name
    vocal_file_path = OUTPUT_DIR / vocal_file_name
    mixed_wav_file_path = OUTPUT_DIR / mixed_wav_file_name
    final_file_path = OUTPUT_DIR / final_file_name

    with generation_lock:
        deapi_request_id = None
        deapi_source_file_name = None

        if data.music_provider == "deapi":
            deapi_source_file_name, deapi_request_id = generate_deapi_music_bundle(
                data,
                prompt=music_prompt,
                lyrics="[Instrumental]",
            )
            deapi_source_file_path = OUTPUT_DIR / deapi_source_file_name
            if deapi_source_file_path.suffix.lower() == ".wav":
                shutil.copyfile(deapi_source_file_path, music_file_path)
            else:
                convert_audio_to_wav(deapi_source_file_path, music_file_path)
        else:
            generate_musicgen_file(
                music_prompt,
                data.duration_seconds,
                music_file_path,
                vocals=True,
            )

        speech_metadata = generate_speech_file(
            text=lyrics,
            vocal_style=data.vocal_style,
            language=data.language,
            speech_engine=data.speech_engine,
            vocal_delivery=data.vocal_delivery,
            file_path=vocal_file_path,
            speaker_name=data.speaker_name,
            speaker_wav_path=data.speaker_wav_path,
            piper_voice=data.piper_voice,
            piper_speaker_id=data.piper_speaker_id,
            piper_length_scale=data.piper_length_scale,
            piper_noise_scale=data.piper_noise_scale,
            piper_noise_w_scale=data.piper_noise_w_scale,
        )

    mix_audio_files(
        music_file_path=music_file_path,
        vocal_file_path=vocal_file_path,
        output_wav_path=mixed_wav_file_path,
        music_gain_db=data.music_gain_db,
        vocal_gain_db=data.speech_gain_db,
    )
    export_mp3(mixed_wav_file_path, final_file_path)

    return {
        "file": final_file_name,
        "music_file": music_file_name,
        "speech_file": vocal_file_name,
        "mixed_wav_file": mixed_wav_file_name,
        "speech_engine": speech_metadata["speech_engine"],
        "speaker_name": speech_metadata["speaker_name"],
        "speaker_wav_path": speech_metadata["speaker_wav_path"],
        "music_provider": data.music_provider,
        "deapi_request_id": deapi_request_id,
        "deapi_source_file": deapi_source_file_name,
    }


def generate_music_bundle(data: GenerateRequest) -> dict[str, str | None]:
    prompt = data.prompt.strip()
    validate_music_provider_duration(data.music_provider, data.duration_seconds)

    with generation_lock:
        if data.music_provider == "deapi":
            file_name, deapi_request_id = generate_deapi_music_bundle(
                data,
                prompt=prompt,
                lyrics=data.deapi_lyrics.strip() or "[Instrumental]",
            )
            return {
                "file": file_name,
                "music_provider": "deapi",
                "deapi_request_id": deapi_request_id,
            }

        file_name = f"{uuid4().hex}.wav"
        file_path = OUTPUT_DIR / file_name
        generate_musicgen_file(prompt, data.duration_seconds, file_path)

    return {
        "file": file_name,
        "music_provider": "local",
        "deapi_request_id": None,
    }


@app.on_event("startup")
def load_models_on_startup() -> None:
    load_music_model()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
async def generate_music(data: GenerateRequest, request: Request) -> dict[str, str | None]:
    prompt = data.prompt.strip()

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    try:
        result = await run_in_threadpool(
            generate_music_bundle,
            data,
        )
        return {
            "file": result["file"],
            "audio_url": build_audio_url(request, result["file"]),
            "music_provider": result["music_provider"],
            "deapi_request_id": result["deapi_request_id"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DeapiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Music generation failed: {exc}"
        ) from exc


@app.post("/generate-with-speech")
async def generate_with_speech(
    data: GenerateSpeechMixRequest, request: Request
) -> dict[str, str | None]:
    music_prompt = data.music_prompt.strip()
    lyrics = data.lyrics.strip()

    if not music_prompt:
        raise HTTPException(status_code=400, detail="music_prompt is required")

    if not lyrics:
        raise HTTPException(status_code=400, detail="lyrics is required")

    try:
        result = await run_in_threadpool(generate_mix_bundle, data)
        return {
            "file": result["file"],
            "audio_url": build_audio_url(request, result["file"]),
            "music_file": result["music_file"],
            "music_url": build_audio_url(request, result["music_file"]),
            "speech_file": result["speech_file"],
            "speech_url": build_audio_url(request, result["speech_file"]),
            "mixed_wav_file": result["mixed_wav_file"],
            "mixed_wav_url": build_audio_url(request, result["mixed_wav_file"]),
            "speech_engine": result["speech_engine"],
            "speaker_name": result["speaker_name"],
            "speaker_wav_path": result["speaker_wav_path"],
            "music_provider": result["music_provider"],
            "deapi_request_id": result["deapi_request_id"],
            "deapi_source_file": result["deapi_source_file"],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DeapiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DependencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Music and speech generation failed: {exc}"
        ) from exc


@app.get("/deapi/models")
async def deapi_models() -> dict:
    try:
        return await run_in_threadpool(get_deapi_music_models)
    except DeapiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/deapi/balance")
async def deapi_balance() -> dict:
    try:
        return await run_in_threadpool(get_deapi_balance)
    except DeapiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/audio/{file_name}")
async def get_audio(file_name: str) -> FileResponse:
    file_path = OUTPUT_DIR / file_name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
    }
    media_type = media_types.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(file_path, media_type=media_type, filename=file_name)
