"""
Vital signs signal processing (camera rPPG / PPG-like signals)
=============================================================
This module turns raw RGB time series into approximate vital signs.

Important: Camera-based vitals are inherently noisy and NOT a medical device.
We implement practical signal-processing (filtering + peak/PSD estimation)
to replace placeholder/random outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

try:
    from scipy.signal import butter, filtfilt, find_peaks, welch
    SCIPY_AVAILABLE = True
except Exception:
    SCIPY_AVAILABLE = False


def _as_np(x) -> np.ndarray:
    arr = np.array(x, dtype=float).reshape(-1)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    return arr


def _estimate_fps(timestamps_ms: Optional[np.ndarray], default_fps: float) -> float:
    if timestamps_ms is None or len(timestamps_ms) < 2:
        return float(default_fps)
    dt = (timestamps_ms[-1] - timestamps_ms[0]) / 1000.0
    if dt <= 0:
        return float(default_fps)
    return float((len(timestamps_ms) - 1) / dt)


def _detrend(x: np.ndarray) -> np.ndarray:
    if len(x) < 3:
        return x.copy()
    t = np.arange(len(x), dtype=float)
    A = np.vstack([t, np.ones_like(t)]).T
    m, c = np.linalg.lstsq(A, x, rcond=None)[0]
    return x - (m * t + c)


def _bandpass(x: np.ndarray, fs: float, lo_hz: float, hi_hz: float, order: int = 3) -> np.ndarray:
    if not SCIPY_AVAILABLE or len(x) < 8:
        return x.copy()
    nyq = 0.5 * fs
    lo = max(0.001, lo_hz / nyq)
    hi = min(0.999, hi_hz / nyq)
    if hi <= lo:
        return x.copy()
    b, a = butter(order, [lo, hi], btype="band")
    return filtfilt(b, a, x)


def _robust_z(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) or 1.0
    return (x - med) / (1.4826 * mad)


def _signal_quality(x: np.ndarray) -> float:
    """
    Rough quality score [0..1] based on dynamic range & stability.
    """
    if len(x) < 20:
        return 0.0
    xr = _robust_z(x)
    dyn = np.clip(np.std(xr) / 2.0, 0.0, 1.0)          # more variation helps up to a point
    spikes = np.mean(np.abs(xr) > 6.0)                 # fewer spikes is better
    q = dyn * (1.0 - np.clip(spikes * 5.0, 0.0, 1.0))
    return float(np.clip(q, 0.0, 1.0))


def estimate_heart_rate_bpm(ppg: np.ndarray, fs: float) -> Tuple[Optional[int], Dict]:
    """
    Estimate HR using bandpass + peak detection, with Welch-PSD fallback.
    """
    meta: Dict = {}
    if len(ppg) < int(fs * 3):
        return None, {"reason": "insufficient_samples"}

    x = _detrend(ppg)
    x = _bandpass(x, fs, lo_hz=0.7, hi_hz=4.0)  # 42..240 bpm

    meta["quality"] = _signal_quality(x)

    hr = None
    if SCIPY_AVAILABLE:
        min_dist = int(round(fs * 0.35))  # ~170 bpm max
        peaks, props = find_peaks(x, distance=max(1, min_dist), prominence=np.std(x) * 0.4)
        if len(peaks) >= 3:
            ibi = np.diff(peaks) / fs
            ibi = ibi[(ibi > 0.3) & (ibi < 2.0)]
            if len(ibi) >= 2:
                hr = int(round(60.0 / float(np.median(ibi))))
                meta["method"] = "peaks"
                meta["n_peaks"] = int(len(peaks))

    if hr is None and SCIPY_AVAILABLE:
        f, Pxx = welch(x, fs=fs, nperseg=min(len(x), int(fs * 6)))
        mask = (f >= 0.7) & (f <= 4.0)
        if np.any(mask):
            f0 = float(f[mask][np.argmax(Pxx[mask])])
            hr = int(round(f0 * 60.0))
            meta["method"] = "welch"
            meta["peak_hz"] = f0

    if hr is None:
        return None, {**meta, "reason": "unable_to_estimate"}

    hr = int(np.clip(hr, 40, 180))
    return hr, meta


def estimate_resp_rate_bpm(ppg: np.ndarray, fs: float) -> Tuple[Optional[int], Dict]:
    """
    Estimate respiratory rate from amplitude envelope (low-frequency content).
    """
    meta: Dict = {}
    if len(ppg) < int(fs * 8):
        return None, {"reason": "insufficient_samples"}

    x = _detrend(ppg)
    # Envelope proxy
    env = np.abs(x)
    env = _bandpass(env, fs, lo_hz=0.1, hi_hz=0.5)  # 6..30 breaths/min
    meta["quality"] = _signal_quality(env)

    rr = None
    if SCIPY_AVAILABLE:
        f, Pxx = welch(env, fs=fs, nperseg=min(len(env), int(fs * 10)))
        mask = (f >= 0.1) & (f <= 0.5)
        if np.any(mask):
            f0 = float(f[mask][np.argmax(Pxx[mask])])
            rr = int(round(f0 * 60.0))
            meta["method"] = "welch"
            meta["peak_hz"] = f0

    if rr is None:
        return None, {**meta, "reason": "unable_to_estimate"}

    rr = int(np.clip(rr, 8, 30))
    return rr, meta


def estimate_spo2_percent(red: np.ndarray, green: np.ndarray) -> Tuple[Optional[int], Dict]:
    """
    Very rough SpO2 estimate using AC/DC ratio proxy.
    """
    if len(red) < 60 or len(green) < 60:
        return None, {"reason": "insufficient_samples"}

    r = _detrend(red[-120:])
    g = _detrend(green[-120:])
    dc_r, dc_g = float(np.mean(red[-120:])), float(np.mean(green[-120:]))
    ac_r, ac_g = float(np.std(r)), float(np.std(g))
    if dc_r <= 0 or dc_g <= 0 or ac_g <= 0:
        return None, {"reason": "invalid_signal"}

    ratio = (ac_r / dc_r) / (ac_g / dc_g)
    spo2 = int(round(110 - 25 * ratio))
    spo2 = int(np.clip(spo2, 85, 100))
    return spo2, {"method": "acdc_ratio", "ratio": float(ratio)}


def estimate_bp_mmHg(hr_bpm: Optional[int], ppg: np.ndarray) -> Tuple[Optional[int], Optional[int], Dict]:
    """
    BP estimation from camera is not clinically reliable.
    We produce a heuristic output to keep UI consistent.
    """
    if hr_bpm is None or len(ppg) < 60:
        return None, None, {"reason": "insufficient_inputs"}

    v = float(np.std(_detrend(ppg[-180:])))
    sys = 118 + (hr_bpm - 75) * 0.35 + v * 0.8
    dia = 78 + (hr_bpm - 75) * 0.18 + v * 0.4

    sys_i = int(np.clip(round(sys), 90, 180))
    dia_i = int(np.clip(round(dia), 55, 115))
    if sys_i <= dia_i + 15:
        sys_i = dia_i + 20
    return sys_i, dia_i, {"method": "heuristic", "variability": float(v)}


@dataclass
class VitalSignsResult:
    heart_rate_bpm: Optional[int]
    respiratory_rate_bpm: Optional[int]
    spo2_percent: Optional[int]
    systolic_mmHg: Optional[int]
    diastolic_mmHg: Optional[int]
    signal_quality: float
    meta: Dict


def analyze_rgb_signals(
    red_signal,
    green_signal,
    blue_signal=None,
    fps: float = 30.0,
    timestamps_ms=None,
) -> VitalSignsResult:
    red = _as_np(red_signal)
    green = _as_np(green_signal) if green_signal is not None else np.array([], dtype=float)
    blue = _as_np(blue_signal) if blue_signal is not None else np.array([], dtype=float)
    ts = _as_np(timestamps_ms) if timestamps_ms is not None else None

    fs = _estimate_fps(ts, fps)
    fs = float(np.clip(fs, 10.0, 60.0))

    # Prefer green channel as stronger rPPG in many cases; fall back to red.
    ppg = green if len(green) >= len(red) else red

    hr, hr_meta = estimate_heart_rate_bpm(ppg, fs)
    rr, rr_meta = estimate_resp_rate_bpm(ppg, fs)
    spo2, spo2_meta = estimate_spo2_percent(red, green) if len(green) else (None, {"reason": "no_green"})
    sys, dia, bp_meta = estimate_bp_mmHg(hr, ppg)

    q = float(np.clip(np.mean([_signal_quality(ppg), hr_meta.get("quality", 0.0), rr_meta.get("quality", 0.0)]), 0.0, 1.0))

    meta = {
        "fs_hz": fs,
        "hr": hr_meta,
        "rr": rr_meta,
        "spo2": spo2_meta,
        "bp": bp_meta,
        "scipy_available": SCIPY_AVAILABLE,
    }

    return VitalSignsResult(
        heart_rate_bpm=hr,
        respiratory_rate_bpm=rr,
        spo2_percent=spo2,
        systolic_mmHg=sys,
        diastolic_mmHg=dia,
        signal_quality=q,
        meta=meta,
    )

