from __future__ import annotations

import os
from pathlib import Path
import re
import unicodedata

import torch

from audio_merge import save_wav


MUSIC_MODEL_NAME = os.getenv("MUSIC_MODEL_NAME", "facebook/musicgen-small")
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 20
DEFAULT_DURATION_SECONDS = 8
MUSICGEN_TOKENS_PER_SECOND = 50
MUSICGEN_GUIDANCE_SCALE = float(os.getenv("MUSICGEN_GUIDANCE_SCALE", "3.0"))
MUSICGEN_TEMPERATURE = float(os.getenv("MUSICGEN_TEMPERATURE", "1.0"))
MUSICGEN_TOP_K = int(os.getenv("MUSICGEN_TOP_K", "250"))
MUSICGEN_DURATION_PADDING_TOKENS = int(os.getenv("MUSICGEN_DURATION_PADDING_TOKENS", "5"))

music_processor = None
music_model = None
device = "cuda" if torch.cuda.is_available() else "cpu"


PORTUGUESE_PHRASE_REPLACEMENTS = [
    ("sem voz", "no vocals"),
    ("com voz", "with vocals"),
    ("musica ambiente", "ambient music"),
    ("baixo forte", "powerful bass"),
    ("bateria rapida", "fast drums"),
    ("bateria pesada", "heavy drums"),
    ("guitarra eletrica", "electric guitar"),
    ("guitarras eletricas", "electric guitars"),
    ("concerto ao vivo", "live concert"),
    ("ao vivo", "live"),
    ("anos 80", "80s"),
    ("anos oitenta", "80s"),
    ("sintetizadores brilhantes", "bright synthesizers"),
    ("baixo marcado", "driving bass"),
    ("baixo groovy", "groovy bass"),
]

PORTUGUESE_PROMPT_TERMS = {
    "musica": "music",
    "ritmo": "beat",
    "batida": "beat",
    "baixo": "bass",
    "bateria": "drums",
    "piano": "piano",
    "guitarra": "guitar",
    "violino": "violin",
    "distorcido": "distorted",
    "distorcida": "distorted",
    "distorcidos": "distorted",
    "distorcidas": "distorted",
    "pesado": "heavy",
    "pesada": "heavy",
    "pesados": "heavy",
    "pesadas": "heavy",
    "forte": "powerful",
    "marcado": "driving",
    "marcada": "driving",
    "suave": "smooth",
    "calmo": "calm",
    "calma": "calm",
    "triste": "sad",
    "alegre": "upbeat",
    "rapido": "fast",
    "rapida": "fast",
    "lento": "slow",
    "lenta": "slow",
    "escuro": "dark",
    "escura": "dark",
    "escuros": "dark",
    "escuras": "dark",
    "cinematografico": "cinematic",
    "cinematografica": "cinematic",
    "ambiente": "ambient",
    "eletronico": "electronic",
    "eletronica": "electronic",
    "sintetizador": "synthesizer",
    "sintetizadores": "synthesizers",
    "brilhante": "bright",
    "brilhantes": "bright",
    "nostalgico": "nostalgic",
    "nostalgica": "nostalgic",
    "energia": "energetic",
    "concerto": "concert",
    "vivo": "live",
    "instrumental": "instrumental",
    "voz": "vocals",
}

PORTUGUESE_CONNECTORS = {
    "com",
    "de",
    "e",
    "do",
    "da",
    "dos",
    "das",
    "para",
    "um",
    "uma",
}


def normalize_prompt_text(prompt: str) -> str:
    decomposed = unicodedata.normalize("NFKD", prompt.casefold())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def load_music_model() -> None:
    global music_processor, music_model

    if music_model is None:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        music_processor = AutoProcessor.from_pretrained(MUSIC_MODEL_NAME)
        music_model = MusicgenForConditionalGeneration.from_pretrained(MUSIC_MODEL_NAME)
        music_model.to(device)
        music_model.eval()


def looks_like_portuguese_prompt(prompt: str) -> bool:
    normalized_prompt = normalize_prompt_text(prompt)
    return any(
        re.search(rf"\b{re.escape(term)}\b", normalized_prompt)
        for term in PORTUGUESE_PROMPT_TERMS
    ) or any(
        re.search(rf"\b{re.escape(term)}\b", normalized_prompt)
        for term, _ in PORTUGUESE_PHRASE_REPLACEMENTS
    )


def translate_portuguese_music_prompt(prompt: str) -> str:
    normalized_prompt = normalize_prompt_text(prompt)

    for portuguese_phrase, english_phrase in PORTUGUESE_PHRASE_REPLACEMENTS:
        normalized_prompt = re.sub(
            rf"\b{re.escape(portuguese_phrase)}\b",
            english_phrase,
            normalized_prompt,
        )

    words = re.findall(r"[\w-]+", normalized_prompt)
    translated_words = [
        PORTUGUESE_PROMPT_TERMS.get(word, word)
        for word in words
        if word not in PORTUGUESE_CONNECTORS
    ]

    return " ".join(dict.fromkeys(translated_words))


def build_musicgen_prompt(prompt: str, *, vocals: bool = False) -> str:
    clean_prompt = " ".join(prompt.split())

    if not looks_like_portuguese_prompt(clean_prompt):
        if vocals:
            return f"{clean_prompt}, instrumental backing track, space for vocals"
        return clean_prompt

    translated_prompt = translate_portuguese_music_prompt(clean_prompt)
    if not translated_prompt:
        return clean_prompt

    vocal_context = (
        "instrumental backing track, space for vocals"
        if vocals
        else "instrumental music, no vocals"
    )
    return f"{translated_prompt}, {vocal_context}"


def duration_to_musicgen_tokens(duration_seconds: int) -> int:
    return int(duration_seconds * MUSICGEN_TOKENS_PER_SECOND) + MUSICGEN_DURATION_PADDING_TOKENS


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
        audio_values = music_model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            guidance_scale=MUSICGEN_GUIDANCE_SCALE,
            temperature=MUSICGEN_TEMPERATURE,
            top_k=MUSICGEN_TOP_K,
        )

    audio = audio_values[0, 0].cpu().numpy()
    sampling_rate = music_model.config.audio_encoder.sampling_rate
    save_wav(file_path, sampling_rate, audio)
    return sampling_rate
