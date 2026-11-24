"""Original procedural accents for style studies, not recording-quality guarantees."""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter

PALETTE = {
    "tap": (0.12, 210, 0.030),
    "paper": (0.55, 0, 0.035),
    "brush": (0.68, 0, 0.025),
    "pencil": (0.48, 0, 0.024),
    "marker": (0.35, 0, 0.027),
    "wipe": (0.70, 0, 0.027),
    "print": (0.26, 94, 0.025),
}


def material_sound(kind: str, rate: int, seed: int) -> np.ndarray | None:
    if kind not in PALETTE:
        return None
    duration, tone, gain = PALETTE[kind]
    count = round(duration * rate)
    if count <= 0:
        return np.zeros(0, dtype=np.float32)
    rng = np.random.default_rng(seed)
    noise = rng.uniform(-1.0, 1.0, size=count)
    cutoff = 0.06 if kind in ("brush", "wipe") else 0.32
    low = lfilter([cutoff], [1.0, -(1.0 - cutoff)], noise)
    slow = lfilter([0.025], [1.0, -(1.0 - 0.025)], low)
    band = low - slow
    t = np.arange(count, dtype=np.float64) / rate
    envelope = np.sin(np.pi * t / duration) ** 2
    if kind == "tap":
        value = (np.sin(t * math.tau * tone) + band * 0.12) * np.exp(-t * 48.0)
    elif kind == "print":
        value = (np.sin(t * math.tau * tone) * 0.5 + band) * np.exp(-t * 18.0)
    elif kind == "pencil":
        value = band * envelope * (0.4 + 0.6 * np.sin(t * math.tau * 29.0) ** 2)
    elif kind == "marker":
        value = band * envelope + 0.03 * np.sin(t * math.tau * 730.0) * envelope
    elif kind == "paper":
        value = band * envelope * (0.5 + 0.5 * np.sin(t * math.tau * 11.0) ** 2)
    else:
        value = band * envelope
    return (value * gain).astype(np.float32)
