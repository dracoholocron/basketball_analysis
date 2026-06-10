"""
AudioExcitement — crowd-noise / excitement envelope from a video's audio track.

Used to rank highlights: loud sustained crowd reactions (cheers, shouts) are the
best proxy for "exciting moment". Combined with CV events to filter the highlight
flood. Dependency-light: ffmpeg (already required) + wave + numpy.

Degrades gracefully: if the video has no audio or ffmpeg fails, `at()` returns 0.0
so the highlight ranking falls back to event-type relevance.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import wave

import numpy as np

logger = logging.getLogger(__name__)


class AudioExcitement:
    def __init__(self, times: np.ndarray, intensity: np.ndarray):
        self._t = times
        self._i = intensity

    @property
    def available(self) -> bool:
        return self._t.size > 0

    @classmethod
    def from_video(cls, video_path: str, win_s: float = 0.5, hop_s: float = 0.25) -> "AudioExcitement":
        try:
            wav_path = os.path.join(tempfile.mkdtemp(prefix="excite_"), "audio.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", "16000", "-vn", wav_path],
                capture_output=True, timeout=300, check=True,
            )
            with wave.open(wav_path, "rb") as w:
                sr = w.getframerate()
                n = w.getnframes()
                raw = w.readframes(n)
            os.remove(wav_path)
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if x.size < sr:  # < 1s of audio → treat as unavailable
                return cls(np.array([]), np.array([]))

            win = max(1, int(win_s * sr))
            hop = max(1, int(hop_s * sr))
            n_frames = 1 + (len(x) - win) // hop if len(x) >= win else 0
            if n_frames <= 0:
                return cls(np.array([]), np.array([]))
            rms = np.empty(n_frames, dtype=np.float32)
            for k in range(n_frames):
                seg = x[k * hop: k * hop + win]
                rms[k] = float(np.sqrt(np.mean(seg * seg)) if seg.size else 0.0)
            times = np.arange(n_frames, dtype=np.float32) * hop_s

            # Normalize to a robust 0..1 excitement: how far above the baseline
            # (median) each window is, in MAD units, squashed to [0,1].
            med = float(np.median(rms))
            mad = float(np.median(np.abs(rms - med))) + 1e-6
            z = (rms - med) / (1.4826 * mad)
            intensity = np.clip(z / 6.0, 0.0, 1.0)  # ~6 MAD → full excitement
            logger.info(
                "AudioExcitement: %d windows, mean intensity %.3f, peak %.3f",
                n_frames, float(intensity.mean()), float(intensity.max()),
            )
            return cls(times, intensity)
        except Exception as exc:
            logger.warning("AudioExcitement unavailable (%s) — ranking by event type only", exc)
            return cls(np.array([]), np.array([]))

    def at(self, t: float, window: float = 2.0) -> float:
        """Max excitement intensity within ±window seconds of time t."""
        if not self.available:
            return 0.0
        mask = (self._t >= t - window) & (self._t <= t + window)
        if not mask.any():
            return 0.0
        return float(self._i[mask].max())

    def peaks(self, min_intensity: float = 0.5, min_gap_s: float = 5.0) -> list[tuple[float, float]]:
        """Return [(time_s, intensity)] of strong crowd reactions, debounced."""
        if not self.available:
            return []
        out: list[tuple[float, float]] = []
        last = -1e9
        for t, inten in zip(self._t, self._i):
            if inten >= min_intensity and (t - last) >= min_gap_s:
                out.append((float(t), float(inten)))
                last = float(t)
        return out
