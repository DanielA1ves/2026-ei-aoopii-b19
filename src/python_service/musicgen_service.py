from __future__ import annotations

from pathlib import Path
import re

import torch

from audio_merge import save_wav


MUSIC_MODEL_NAME = "facebook/musicgen-small"
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 20
DEFAULT_DURATION_SECONDS = 8
MUSICGEN_TOKENS_PER_SECOND = 50

music_processor = None
music_model = None
device = "cuda" if torch.cuda.is_available() else "cpu"


PORTUGUESE_PROMPT_TERMS = {
    "musica": "music",
    "música": "music",
    "ritmo": "beat",
    "batida": "beat",
    "baixo": "bass",
    "bateria": "drums",
    "piano": "piano",
    "guitarra": "guitar",
    "violino": "violin",
    "pesado": "heavy",
    "forte": "powerful",
    "suave": "smooth",
    "calmo": "calm",
    "calma": "calm",
    "triste": "sad",
    "alegre": "upbeat",
    "rapido": "fast",
    "rápido": "fast",
    "rapida": "fast",
    "rápida": "fast",
    "lento": "slow",
    "lenta": "slow",
    "escuro": "dark",
    "escura": "dark",
    "cinematografico": "cinematic",
    "cinematográfico": "cinematic",
    "ambiente": "ambient",
    "eletronico": "electronic",
    "eletrónico": "electronic",
    "instrumental": "instrumental",
    "voz": "vocals",
    "sem voz": "no vocals",
}


def load_music_model() -> None:
    global music_processor, music_model

    if music_model is None:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        music_processor = AutoProcessor.from_pretrained(MUSIC_MODEL_NAME)
        music_model = MusicgenForConditionalGeneration.from_pretrained(MUSIC_MODEL_NAME)
        music_model.to(device)
        music_model.eval()


def looks_like_portuguese_prompt(prompt: str) -> bool:
    normalized_prompt = prompt.casefold()
    return any(
        re.search(rf"\b{re.escape(term)}\b", normalized_prompt)
        for term in PORTUGUESE_PROMPT_TERMS
    )


def build_musicgen_prompt(prompt: str, *, vocals: bool = False) -> str:
    clean_prompt = " ".join(prompt.split())

    if not looks_like_portuguese_prompt(clean_prompt):
        if vocals:
            return f"{clean_prompt}, instrumental backing track, space for vocals"
        return clean_prompt

    translated_terms = []
    normalized_prompt = clean_prompt.casefold()
    has_no_vocals = re.search(r"\bsem\s+voz\b", normalized_prompt) is not None
    for portuguese_term, english_term in PORTUGUESE_PROMPT_TERMS.items():
        if portuguese_term == "voz" and has_no_vocals:
            continue

        if re.search(rf"\b{re.escape(portuguese_term)}\b", normalized_prompt):
            translated_terms.append(english_term)

    unique_terms = list(dict.fromkeys(translated_terms))
    if not unique_terms:
        return clean_prompt

    vocal_context = "instrumental backing track, space for vocals" if vocals else "instrumental music, no vocals"
    return f"{vocal_context}, {', '.join(unique_terms)}. Original user description: {clean_prompt}"


def duration_to_musicgen_tokens(duration_seconds: int) -> int:
    return int(duration_seconds * MUSICGEN_TOKENS_PER_SECOND)


def generate_music_file(
    prompt: str,
    duration_seconds: int,
    file_path: Path,
    *,
    vocals: bool = False,
) -> int:
    load_music_model()

    musicgen_prompt = build_musicgen_prompt(prompt, vocals=vocals)
    max_new_tokens = duration_to_musicgen_tokens(duration_seconds)
    inputs = music_processor(text=[musicgen_prompt], padding=True, return_tensors="pt").to(device)

    with torch.no_grad():
        audio_values = music_model.generate(**inputs, max_new_tokens=max_new_tokens)

    audio = audio_values[0, 0].cpu().numpy()
    sampling_rate = music_model.config.audio_encoder.sampling_rate
    save_wav(file_path, sampling_rate, audio)
    return sampling_rate
