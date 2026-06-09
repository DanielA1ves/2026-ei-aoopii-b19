from __future__ import annotations

import logging
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
PROMPT_REFINER_ENABLED = os.getenv("PROMPT_REFINER_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PROMPT_REFINER_MODEL_NAME = os.getenv(
    "PROMPT_REFINER_MODEL_NAME",
    "Qwen/Qwen2.5-0.5B-Instruct",
)
PROMPT_REFINER_MAX_NEW_TOKENS = int(
    os.getenv("PROMPT_REFINER_MAX_NEW_TOKENS", "120")
)

music_processor = None
music_model = None
prompt_refiner_tokenizer = None
prompt_refiner_model = None
prompt_refiner_load_failed = False
device = "cuda" if torch.cuda.is_available() else "cpu"
logger = logging.getLogger(__name__)


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


def load_prompt_refiner_model() -> bool:
    global prompt_refiner_tokenizer, prompt_refiner_model
    global prompt_refiner_load_failed

    if not PROMPT_REFINER_ENABLED:
        return False
    if prompt_refiner_model is not None:
        return True
    if prompt_refiner_load_failed:
        return False

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        prompt_refiner_tokenizer = AutoTokenizer.from_pretrained(
            PROMPT_REFINER_MODEL_NAME
        )
        prompt_refiner_model = AutoModelForCausalLM.from_pretrained(
            PROMPT_REFINER_MODEL_NAME
        )
        prompt_refiner_model.to(device)
        prompt_refiner_model.eval()
        return True
    except Exception:
        prompt_refiner_load_failed = True
        logger.exception(
            "Could not load prompt refiner %s; using the original prompt.",
            PROMPT_REFINER_MODEL_NAME,
        )
        return False


def clean_refined_prompt(text: str) -> str:
    clean_text = " ".join(text.strip().split())
    clean_text = re.sub(
        r"^(refined|improved|music)\s+prompt\s*:\s*",
        "",
        clean_text,
        flags=re.IGNORECASE,
    )
    return clean_text.strip(" \"'")


def refine_music_prompt(prompt: str, *, vocals: bool = False) -> str:
    clean_prompt = " ".join(prompt.split())
    if not clean_prompt or not load_prompt_refiner_model():
        return clean_prompt

    arrangement_instruction = (
        "Leave space in the arrangement for separately generated lead vocals."
        if vocals
        else "Respect whether the user requested vocals or an instrumental."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite the request as a precise English prompt for a "
                "text-to-music model with limited prompt adherence. Treat every "
                "instrument, genre, mood, era, tempo, and vocal choice explicitly "
                "requested by the user as mandatory. Never remove, replace, or "
                "weaken a mandatory element. If the user names an instrument, begin "
                "with that instrument, not with the genre or mood. Describe the main "
                "instrument as prominent, clearly audible, and present throughout "
                "the track. Mention it a second time naturally as the lead or "
                "defining element. Translate all Portuguese musical terms to English. "
                "Never add vocals, singers, choirs, or lyrics unless the user asks "
                "for them explicitly. "
                "Keep accompaniment subtle so it does not compete with requested "
                "instruments. Add only a few compatible performance or production "
                "details. Never add artist names, lyrics, explanations, headings, "
                "alternatives, or quotation marks. Return one direct prompt of no "
                "more than 55 words."
            ),
        },
        {
            "role": "user",
            "content": (
                "Preserve every explicitly requested element. Put mandatory elements "
                "before optional details.\n"
                "User request: jazz triste e lento com saxofone e bateria suave"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Prominent tenor saxophone, clearly audible as the lead instrument "
                "throughout a slow melancholic jazz track. Expressive saxophone "
                "melody with quiet brushed drums and subtle upright bass, intimate "
                "warm studio production, instrumental only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Preserve every explicitly requested element. Put mandatory elements "
                "before optional details.\n"
                "User request: rock energético com guitarra elétrica e bateria pesada"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Prominent distorted electric guitar, clearly audible as the lead "
                "instrument throughout an energetic rock track. Driving guitar riffs "
                "with heavy acoustic drums, powerful rhythm, punchy live production, "
                "instrumental only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{arrangement_instruction}\n"
                "Preserve every explicitly requested element. Put the mandatory "
                "elements before optional details.\n"
                f"User request: {clean_prompt}"
            ),
        },
    ]

    try:
        model_inputs = prompt_refiner_tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            generated_ids = prompt_refiner_model.generate(
                **model_inputs,
                max_new_tokens=PROMPT_REFINER_MAX_NEW_TOKENS,
                do_sample=False,
                pad_token_id=prompt_refiner_tokenizer.eos_token_id,
            )

        prompt_token_count = model_inputs["input_ids"].shape[-1]
        new_tokens = generated_ids[0, prompt_token_count:]
        refined_prompt = clean_refined_prompt(
            prompt_refiner_tokenizer.decode(new_tokens, skip_special_tokens=True)
        )
        return refined_prompt or clean_prompt
    except Exception:
        logger.exception("Prompt refinement failed; using the original prompt.")
        return clean_prompt


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
    if not clean_prompt:
        return clean_prompt

    refined_prompt = refine_music_prompt(clean_prompt, vocals=vocals)
    final_prompt = (
        translate_portuguese_music_prompt(clean_prompt)
        if looks_like_portuguese_prompt(clean_prompt)
        and refined_prompt == clean_prompt
        else refined_prompt
    )

    if not final_prompt:
        return clean_prompt

    vocal_context = (
        "instrumental backing track, space for vocals"
        if vocals
        else "instrumental music, no vocals"
    )
    return f"{final_prompt}, {vocal_context}"


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
