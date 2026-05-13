from __future__ import annotations

from math import gcd
from pathlib import Path

import numpy as np
from scipy.io.wavfile import read as read_wav
from scipy.io.wavfile import write as write_wav
from scipy.signal import resample_poly


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


def save_wav(file_path: Path, sampling_rate: int, audio: np.ndarray) -> None:
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


def mix_audio_arrays(
    music_audio: np.ndarray,
    music_rate: int,
    vocal_audio: np.ndarray,
    vocal_rate: int,
    music_gain_db: float,
    vocal_gain_db: float,
) -> tuple[np.ndarray, int]:
    music = normalize_audio(music_audio)
    vocal = normalize_audio(vocal_audio)
    vocal = resample_audio(vocal, vocal_rate, music_rate)

    music = apply_gain(music, music_gain_db)
    vocal = apply_gain(vocal, vocal_gain_db)

    output_length = max(len(music), len(vocal))
    if len(music) and len(music) < output_length:
        repeat_count = int(np.ceil(output_length / len(music)))
        music = np.tile(music, repeat_count)[:output_length]

    mixed = np.zeros(output_length, dtype=np.float32)
    mixed[: len(music)] += music
    mixed[: len(vocal)] += vocal

    peak = np.max(np.abs(mixed)) if mixed.size else 0.0
    if peak > 0.99:
        mixed = mixed / peak

    return mixed.astype(np.float32), music_rate


def mix_audio_files(
    music_file_path: Path,
    vocal_file_path: Path,
    output_wav_path: Path,
    music_gain_db: float,
    vocal_gain_db: float,
) -> int:
    music_rate, music_audio = read_wav(str(music_file_path))
    vocal_rate, vocal_audio = read_wav(str(vocal_file_path))
    mixed_audio, mixed_rate = mix_audio_arrays(
        music_audio=music_audio,
        music_rate=music_rate,
        vocal_audio=vocal_audio,
        vocal_rate=vocal_rate,
        music_gain_db=music_gain_db,
        vocal_gain_db=vocal_gain_db,
    )
    save_wav(output_wav_path, mixed_rate, mixed_audio)
    return mixed_rate


def export_mp3(wav_file_path: Path, mp3_file_path: Path) -> None:
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise RuntimeError("pydub is required to export the final song as MP3.") from exc

    audio = AudioSegment.from_wav(str(wav_file_path))
    audio.export(str(mp3_file_path), format="mp3")
