from pathlib import Path
from uuid import uuid4

import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from scipy.io.wavfile import write as write_wav
from pydantic import BaseModel, Field
from transformers import AutoProcessor, MusicgenForConditionalGeneration


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_NAME = "facebook/musicgen-small"
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 20
TOKENS_PER_SECOND = 100

app = FastAPI(title="MusicGen Service")
processor = None
model = None
device = "cuda" if torch.cuda.is_available() else "cpu"


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Music prompt")
    duration_seconds: int = Field(
        8,
        ge=MIN_DURATION_SECONDS,
        le=MAX_DURATION_SECONDS,
        description="Approximate audio duration in seconds",
    )


@app.on_event("startup")
def load_model() -> None:
    global processor, model

    if model is None:
        processor = AutoProcessor.from_pretrained(MODEL_NAME)
        model = MusicgenForConditionalGeneration.from_pretrained(MODEL_NAME)
        model.to(device)
        model.eval()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
async def generate_music(data: GenerateRequest, request: Request) -> dict[str, str]:
    prompt = data.prompt.strip()

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    if processor is None or model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")

    try:
        inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)

        with torch.no_grad():
            audio_values = model.generate(
                **inputs,
                max_new_tokens=data.duration_seconds * TOKENS_PER_SECOND,
            )

        audio = audio_values[0, 0].cpu().numpy()
        sampling_rate = model.config.audio_encoder.sampling_rate

        file_name = f"{uuid4().hex}.wav"
        file_path = OUTPUT_DIR / file_name

        write_wav(str(file_path), rate=sampling_rate, data=audio)

        return {
            "file": file_name,
            "audio_url": str(request.base_url).rstrip("/") + f"/audio/{file_name}",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Music generation failed: {exc}"
        ) from exc


@app.get("/audio/{file_name}")
async def get_audio(file_name: str) -> FileResponse:
    file_path = OUTPUT_DIR / file_name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="audio/wav", filename=file_name)
