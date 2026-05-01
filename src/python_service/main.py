from __future__ import annotations

from contextlib import contextmanager
from math import gcd
from pathlib import Path
from threading import Lock
import re
import shutil
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4
import wave

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from scipy.io.wavfile import read as read_wav
from scipy.io.wavfile import write as write_wav
from scipy.signal import resample_poly
from starlette.concurrency import run_in_threadpool
from transformers import AutoProcessor, MusicgenForConditionalGeneration


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MUSIC_MODEL_NAME = "facebook/musicgen-small"
BARK_MODEL_NAME = "suno/bark-small"
MAX_NEW_TOKENS = 256
DEFAULT_MUSIC_GAIN_DB = -9.0
DEFAULT_SPEECH_GAIN_DB = 4.0
DEFAULT_LANGUAGE = "pt-PT"
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
music_processor = None
music_model = None
bark_processor = None
bark_model = None
xtts_model = None
xtts_speakers = None
piper_voices = {}
device = "cuda" if torch.cuda.is_available() else "cpu"
generation_lock = Lock()


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Music prompt")


class GenerateSpeechMixRequest(BaseModel):
    music_prompt: str = Field(..., min_length=1, description="Prompt for MusicGen")
    lyrics: str = Field(..., min_length=1, description="Text to synthesize over the music")
    speech_engine: str = Field(
        default="piper",
        pattern="^(xtts|bark|piper)$",
        description="Speech engine to use: xtts, bark or piper",
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


def load_music_model() -> None:
    global music_processor, music_model

    if music_model is None:
        music_processor = AutoProcessor.from_pretrained(MUSIC_MODEL_NAME)
        music_model = MusicgenForConditionalGeneration.from_pretrained(MUSIC_MODEL_NAME)
        music_model.to(device)
        music_model.eval()


def load_bark_model() -> None:
    global bark_processor, bark_model

    if bark_model is None:
        try:
            from transformers import BarkModel
        except ImportError as exc:
            raise DependencyUnavailableError(
                "Bark is not available in the installed transformers version."
            ) from exc

        bark_processor = AutoProcessor.from_pretrained(BARK_MODEL_NAME)
        bark_model = BarkModel.from_pretrained(BARK_MODEL_NAME)
        bark_model.to(device)
        bark_model.eval()


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


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio)

    if array.ndim > 1:
        array = array.mean(axis=-1)

    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        scale = max(abs(info.min), info.max)
        return (array.astype(np.float32) / float(scale)).astype(np.float32)

    return array.astype(np.float32)


def apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    return audio * np.float32(10 ** (gain_db / 20.0))


def save_audio(file_path: Path, sampling_rate: int, audio: np.ndarray) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = np.int16(clipped * 32767)
    write_wav(str(file_path), rate=sampling_rate, data=pcm16)


def resample_audio(audio: np.ndarray, original_rate: int, target_rate: int) -> np.ndarray:
    if original_rate == target_rate:
        return audio

    rate_gcd = gcd(original_rate, target_rate)
    up = target_rate // rate_gcd
    down = original_rate // rate_gcd
    return resample_poly(audio, up=up, down=down).astype(np.float32)


def mix_audio_tracks(
    music_audio: np.ndarray,
    music_rate: int,
    speech_audio: np.ndarray,
    speech_rate: int,
    music_gain_db: float,
    speech_gain_db: float,
) -> tuple[np.ndarray, int]:
    music = normalize_audio(music_audio)
    speech = normalize_audio(speech_audio)
    speech = resample_audio(speech, speech_rate, music_rate)

    music = apply_gain(music, music_gain_db)
    speech = apply_gain(speech, speech_gain_db)

    output_length = max(len(music), len(speech))
    if len(music) and len(music) < output_length:
        repeat_count = int(np.ceil(output_length / len(music)))
        music = np.tile(music, repeat_count)[:output_length]

    mixed = np.zeros(output_length, dtype=np.float32)
    mixed[: len(music)] += music
    mixed[: len(speech)] += speech

    peak = np.max(np.abs(mixed)) if mixed.size else 0.0
    if peak > 0.99:
        mixed = mixed / peak

    return mixed.astype(np.float32), music_rate


def build_audio_url(request: Request, file_name: str) -> str:
    return str(request.base_url).rstrip("/") + f"/audio/{file_name}"


def resolve_speaker_file(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    file_path = Path(path_value).expanduser()
    if not file_path.is_absolute():
        file_path = (BASE_DIR / file_path).resolve()

    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Speaker reference file was not found: {file_path}")

    return file_path


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


def generate_music_file(prompt: str, file_path: Path) -> int:
    load_music_model()

    inputs = music_processor(text=[prompt], padding=True, return_tensors="pt").to(device)

    with torch.no_grad():
        audio_values = music_model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)

    audio = audio_values[0, 0].cpu().numpy()
    sampling_rate = music_model.config.audio_encoder.sampling_rate
    save_audio(file_path, sampling_rate, audio)
    return sampling_rate


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


def generate_bark_file(
    text: str,
    file_path: Path,
    speaker_name: str | None,
) -> dict[str, str | None]:
    load_bark_model()

    processor_kwargs = {}
    if speaker_name:
        processor_kwargs["voice_preset"] = speaker_name

    inputs = bark_processor(text, **processor_kwargs)
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        audio_values = bark_model.generate(**inputs)

    audio = audio_values.cpu().numpy().squeeze()
    sampling_rate = bark_model.generation_config.sample_rate
    save_audio(file_path, sampling_rate, audio)

    return {
        "speech_engine": "bark",
        "speaker_name": speaker_name,
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
    language: str,
    speech_engine: str,
    file_path: Path,
    speaker_name: str | None,
    speaker_wav_path: str | None,
    piper_voice: str | None,
    piper_speaker_id: int | None,
    piper_length_scale: float,
    piper_noise_scale: float,
    piper_noise_w_scale: float,
) -> dict[str, str | None]:
    if speech_engine == "piper":
        return generate_piper_file(
            text=text,
            file_path=file_path,
            piper_voice_code=resolve_piper_voice(language, piper_voice),
            piper_speaker_id=piper_speaker_id,
            piper_length_scale=piper_length_scale,
            piper_noise_scale=piper_noise_scale,
            piper_noise_w_scale=piper_noise_w_scale,
        )

    if speech_engine == "bark":
        return generate_bark_file(text=text, file_path=file_path, speaker_name=speaker_name)

    return generate_xtts_file(
        text=text,
        language=language,
        file_path=file_path,
        speaker_name=speaker_name,
        speaker_wav_path=speaker_wav_path,
    )


def generate_mix_bundle(data: GenerateSpeechMixRequest) -> dict[str, str | None]:
    music_prompt = data.music_prompt.strip()
    lyrics = data.lyrics.strip()
    bundle_id = uuid4().hex
    music_file_name = f"{bundle_id}-music.wav"
    speech_file_name = f"{bundle_id}-speech.wav"
    mixed_file_name = f"{bundle_id}-mix.wav"

    music_file_path = OUTPUT_DIR / music_file_name
    speech_file_path = OUTPUT_DIR / speech_file_name
    mixed_file_path = OUTPUT_DIR / mixed_file_name

    with generation_lock:
        generate_music_file(music_prompt, music_file_path)
        speech_metadata = generate_speech_file(
            text=lyrics,
            language=data.language,
            speech_engine=data.speech_engine,
            file_path=speech_file_path,
            speaker_name=data.speaker_name,
            speaker_wav_path=data.speaker_wav_path,
            piper_voice=data.piper_voice,
            piper_speaker_id=data.piper_speaker_id,
            piper_length_scale=data.piper_length_scale,
            piper_noise_scale=data.piper_noise_scale,
            piper_noise_w_scale=data.piper_noise_w_scale,
        )

    music_rate, music_audio = read_wav(str(music_file_path))
    speech_rate, speech_audio = read_wav(str(speech_file_path))
    mixed_audio, mixed_rate = mix_audio_tracks(
        music_audio=music_audio,
        music_rate=music_rate,
        speech_audio=speech_audio,
        speech_rate=speech_rate,
        music_gain_db=data.music_gain_db,
        speech_gain_db=data.speech_gain_db,
    )
    save_audio(mixed_file_path, mixed_rate, mixed_audio)

    return {
        "file": mixed_file_name,
        "music_file": music_file_name,
        "speech_file": speech_file_name,
        "speech_engine": speech_metadata["speech_engine"],
        "speaker_name": speech_metadata["speaker_name"],
        "speaker_wav_path": speech_metadata["speaker_wav_path"],
    }


def generate_music_bundle(prompt: str) -> str:
    file_name = f"{uuid4().hex}.wav"
    file_path = OUTPUT_DIR / file_name

    with generation_lock:
        generate_music_file(prompt, file_path)

    return file_name


@app.on_event("startup")
def load_models_on_startup() -> None:
    load_music_model()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
async def generate_music(data: GenerateRequest, request: Request) -> dict[str, str]:
    prompt = data.prompt.strip()

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    try:
        file_name = await run_in_threadpool(generate_music_bundle, prompt)
        return {
            "file": file_name,
            "audio_url": build_audio_url(request, file_name),
        }
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
            "speech_engine": result["speech_engine"],
            "speaker_name": result["speaker_name"],
            "speaker_wav_path": result["speaker_wav_path"],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DependencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Music and speech generation failed: {exc}"
        ) from exc


@app.get("/audio/{file_name}")
async def get_audio(file_name: str) -> FileResponse:
    file_path = OUTPUT_DIR / file_name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="audio/wav", filename=file_name)
