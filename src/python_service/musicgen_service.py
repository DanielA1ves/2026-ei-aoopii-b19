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
    ("coro de igreja", "church choir"),
    ("coral de igreja", "church choir"),
    ("coro gospel", "gospel choir"),
    ("coral gospel", "gospel choir"),
    ("musica gospel", "gospel music"),
    ("musica de terror", "horror music"),
    ("terror cinematografico", "cinematic horror"),
    ("piano classico", "classical piano"),
    ("jazz suave", "smooth jazz"),
    ("jazz com saxofone", "saxophone jazz"),
    ("trap escuro", "dark trap"),
    ("batida trap", "trap beat"),
    ("samba alegre", "upbeat samba"),
    ("percussao brasileira", "Brazilian percussion"),
    ("fado portugues", "Portuguese fado"),
    ("guitarra portuguesa", "Portuguese guitar"),
    ("rock dos anos 80", "80s rock"),
    ("rock anos 80", "80s rock"),
    ("hip hop calmo", "calm hip hop"),
    ("lo fi", "lo-fi"),
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
    "saxofone": "saxophone",
    "cordas": "strings",
    "orquestra": "orchestra",
    "orquestral": "orchestral",
    "percussao": "percussion",
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
    "suaves": "smooth",
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
    "tenso": "tense",
    "tensa": "tense",
    "tensos": "tense",
    "tensas": "tense",
    "ambiente": "ambient",
    "terror": "horror",
    "suspense": "suspense",
    "eletronico": "electronic",
    "eletronica": "electronic",
    "sintetizador": "synthesizer",
    "sintetizadores": "synthesizers",
    "brilhante": "bright",
    "brilhantes": "bright",
    "nostalgico": "nostalgic",
    "nostalgica": "nostalgic",
    "energia": "energetic",
    "trap": "trap",
    "samba": "samba",
    "fado": "fado",
    "jazz": "jazz",
    "rock": "rock",
    "metal": "metal",
    "classico": "classical",
    "classica": "classical",
    "noite": "night",
    "concerto": "concert",
    "vivo": "live",
    "instrumental": "instrumental",
    "voz": "vocals",
    "vozes": "vocals",
    "coro": "choir",
    "coral": "choir",
    "igreja": "church",
    "gospel": "gospel",
    "orgao": "organ",
    "religioso": "religious",
    "religiosa": "religious",
    "sagrado": "sacred",
    "sagrada": "sacred",
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
    "a",
    "o",
    "os",
    "as",
    "um",
    "uma",
}

VOCAL_MUSIC_TERMS = {
    "choir",
    "choral",
    "chorus",
    "vocal",
    "vocals",
    "voice",
    "voices",
    "singer",
    "singers",
    "singing",
    "fado",
    "coro",
    "coral",
    "voz",
    "vozes",
}

PROMPT_EXPANSIONS = [
    (
        {"church choir", "gospel choir", "choir church", "coro igreja", "coral igreja"},
        [
            "church choir",
            "gospel choir",
            "mixed SATB choir",
            "many human voices singing in close harmony",
            "sacred choral music",
            "cathedral reverb",
            "pipe organ accompaniment",
            "reverent and solemn mood",
            "slow hymn-like progression",
        ],
    ),
    (
        {"gospel music", "gospel"},
        [
            "gospel music",
            "soulful choir vocals",
            "church harmonies",
            "warm organ",
            "hand claps",
            "uplifting spiritual mood",
        ],
    ),
    (
        {"organ", "pipe organ", "orgao"},
        [
            "pipe organ",
            "large church acoustic",
            "cathedral reverb",
            "sustained chords",
        ],
    ),
    (
        {
            "heavy metal",
            "metal heavy",
            "guitar metal",
            "guitarra metal",
            "electric guitar heavy",
            "heavy electric guitar",
        },
        [
            "heavy metal",
            "distorted electric guitar riffs",
            "powerful rhythm guitars",
            "fast acoustic drums",
            "aggressive rock tone",
        ],
    ),
    (
        {"dark trap", "trap dark", "trap beat", "batida trap"},
        [
            "dark trap beat",
            "deep 808 bass",
            "crisp hi-hats",
            "sparse minor-key melody",
            "modern hip hop production",
        ],
    ),
    (
        {"classical piano", "sad piano", "piano sad", "piano classical"},
        [
            "solo piano",
            "expressive classical piano",
            "slow tempo",
            "melancholic minor-key harmony",
            "natural room reverb",
        ],
    ),
    (
        {"ambient music", "ambient calm", "calm ambient"},
        [
            "ambient soundscape",
            "soft evolving synthesizer pads",
            "slow atmospheric texture",
            "wide spacious reverb",
            "minimal percussion",
        ],
    ),
    (
        {"smooth jazz", "saxophone jazz", "jazz saxophone"},
        [
            "smooth jazz",
            "tenor saxophone lead",
            "walking bass",
            "brushed drums",
            "warm late-night lounge sound",
        ],
    ),
    (
        {"upbeat samba", "samba", "Brazilian percussion"},
        [
            "Brazilian samba rhythm",
            "pandeiro and surdo percussion",
            "cavaquinho groove",
            "upbeat festive feel",
            "syncopated acoustic percussion",
        ],
    ),
    (
        {"Portuguese fado", "fado"},
        [
            "Portuguese fado",
            "Portuguese guitar accompaniment",
            "mournful vocal melody",
            "intimate traditional performance",
            "melancholic saudade mood",
        ],
    ),
    (
        {"horror music", "cinematic horror", "horror cinematic"},
        [
            "cinematic horror score",
            "tense string section",
            "dissonant orchestral drones",
            "dark suspenseful atmosphere",
            "slow unsettling build",
        ],
    ),
    (
        {"80s rock", "rock 80s"},
        [
            "80s rock",
            "electric guitar power chords",
            "live drum kit",
            "anthemic chorus energy",
            "bright vintage rock production",
        ],
    ),
]


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


def prompt_requests_vocal_music(prompt: str) -> bool:
    normalized_prompt = normalize_prompt_text(prompt)
    words = set(re.findall(r"[\w-]+", normalized_prompt))
    return any(term in normalized_prompt for term in VOCAL_MUSIC_TERMS) or bool(
        words & VOCAL_MUSIC_TERMS
    )


def ordered_unique(parts: list[str]) -> list[str]:
    seen = set()
    unique_parts = []
    for part in parts:
        clean_part = " ".join(part.split()).strip()
        key = clean_part.casefold()
        if clean_part and key not in seen:
            seen.add(key)
            unique_parts.append(clean_part)
    return unique_parts


def expand_music_prompt(translated_prompt: str, original_prompt: str) -> str:
    normalized_original = normalize_prompt_text(original_prompt)
    normalized_translated = normalize_prompt_text(translated_prompt)
    prompt_parts = [translated_prompt]

    for triggers, expansion_parts in PROMPT_EXPANSIONS:
        if any(
            normalize_prompt_text(trigger) in normalized_original
            or normalize_prompt_text(trigger) in normalized_translated
            for trigger in triggers
        ):
            prompt_parts.extend(expansion_parts)

    return ", ".join(ordered_unique(prompt_parts))


def build_engineered_music_prompt(prompt: str, *, vocals: bool = False) -> str:
    clean_prompt = " ".join(prompt.split())
    if not clean_prompt:
        return clean_prompt

    is_portuguese_prompt = looks_like_portuguese_prompt(clean_prompt)
    translated_prompt = (
        translate_portuguese_music_prompt(clean_prompt)
        if is_portuguese_prompt
        else clean_prompt
    )

    if not translated_prompt:
        return clean_prompt

    engineered_prompt = expand_music_prompt(translated_prompt, clean_prompt)
    was_expanded = engineered_prompt != translated_prompt

    if not is_portuguese_prompt and not was_expanded:
        if vocals:
            return f"{clean_prompt}, instrumental backing track, space for vocals"
        return clean_prompt

    requests_vocal_music = prompt_requests_vocal_music(
        f"{clean_prompt} {engineered_prompt}"
    )

    if vocals:
        vocal_context = (
            "background arrangement, clear space for lead vocals"
            if requests_vocal_music
            else "instrumental backing track, space for vocals"
        )
    else:
        if requests_vocal_music:
            vocal_context = "prominent human vocals and harmonies"
        else:
            vocal_context = ""

    return ", ".join(ordered_unique([engineered_prompt, vocal_context]))


def build_musicgen_prompt(prompt: str, *, vocals: bool = False) -> str:
    return build_engineered_music_prompt(prompt, vocals=vocals)


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
    inputs = music_processor(
        text=[musicgen_prompt],
        padding=True,
        return_tensors="pt",
    ).to(device)

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
