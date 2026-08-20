"""
Analyze an existing audio file with Praat/Parselmouth and plot F0/F1/F2.

Install:
    pip install numpy praat-parselmouth matplotlib

Run:
    python analyze_audio_f0_f1_f2.py your_audio.wav

Useful:
    python analyze_audio_f0_f1_f2.py your_audio.wav --gate-db -35
    python analyze_audio_f0_f1_f2.py your_audio.wav --maximum-formant 5000
    python analyze_audio_f0_f1_f2.py your_audio.wav --csv result.csv --png result.png

Controls in the graph:
- Move mouse over the plot to see F0/F1/F2 at that time.
- Close the window when done.

Notes:
- Best with WAV/FLAC. If MP3/M4A fails, convert it to WAV first.
- For comparing vowels or a short voice sample, use clean dry audio without music.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Optional

import numpy as np
import parselmouth
import matplotlib.pyplot as plt


def db_from_array(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(x * x) + 1e-12))
    return 20.0 * math.log10(rms + 1e-12)


def clean(x) -> Optional[float]:
    try:
        x = float(x)
    except Exception:
        return None
    if not np.isfinite(x) or x <= 0:
        return None
    return x


def median_smooth(values: list[Optional[float]], width: int) -> list[Optional[float]]:
    if width <= 1:
        return values
    out: list[Optional[float]] = []
    half = width // 2
    for i in range(len(values)):
        chunk = [v for v in values[max(0, i - half): min(len(values), i + half + 1)] if v is not None]
        out.append(float(np.median(chunk)) if chunk else None)
    return out


def analyze(
    audio_path: Path,
    time_step: float,
    gate_db: float,
    pitch_floor: float,
    pitch_ceiling: float,
    max_number_of_formants: float,
    maximum_formant: float,
    formant_window: float,
    pre_emphasis_from: float,
    smooth: int,
):
    snd = parselmouth.Sound(str(audio_path))

    pitch = snd.to_pitch(
        time_step=time_step,
        pitch_floor=pitch_floor,
        pitch_ceiling=pitch_ceiling,
    )

    formant = snd.to_formant_burg(
        time_step=time_step,
        max_number_of_formants=max_number_of_formants,
        maximum_formant=maximum_formant,
        window_length=formant_window,
        pre_emphasis_from=pre_emphasis_from,
    )

    xs = snd.xs()
    ys = snd.values[0] if snd.values.ndim == 2 else snd.values
    sample_rate = int(round(snd.sampling_frequency))

    times = np.arange(snd.xmin, snd.xmax, time_step)
    rows = []

    f0s: list[Optional[float]] = []
    f1s: list[Optional[float]] = []
    f2s: list[Optional[float]] = []
    levels: list[float] = []

    half_window = max(1, int(0.02 * sample_rate))

    for t in times:
        center = int(round((t - snd.xmin) * sample_rate))
        a = max(0, center - half_window)
        b = min(len(ys), center + half_window)
        level = db_from_array(ys[a:b]) if b > a else -120.0
        levels.append(level)

        if level < gate_db:
            f0s.append(None)
            f1s.append(None)
            f2s.append(None)
            continue

        f0 = clean(pitch.get_value_at_time(float(t)))
        f1 = clean(formant.get_value_at_time(1, float(t)))
        f2 = clean(formant.get_value_at_time(2, float(t)))

        f0s.append(f0)
        f1s.append(f1)
        f2s.append(f2)

    f0s = median_smooth(f0s, smooth)
    f1s = median_smooth(f1s, smooth)
    f2s = median_smooth(f2s, smooth)

    for t, f0, f1, f2, level in zip(times, f0s, f1s, f2s, levels):
        rows.append({
            "time_s": float(t),
            "f0_hz": "" if f0 is None else round(f0, 2),
            "f1_hz": "" if f1 is None else round(f1, 2),
            "f2_hz": "" if f2 is None else round(f2, 2),
            "level_db": round(level, 2),
        })

    return np.array(times), f0s, f1s, f2s, levels, rows


def save_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["time_s", "f0_hz", "f1_hz", "f2_hz", "level_db"])
        writer.writeheader()
        writer.writerows(rows)


def as_array(values: list[Optional[float]]) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in values], dtype=float)


def plot_interactive(times, f0s, f1s, f2s, levels, title: str, png_path: Optional[Path]):
    f0 = as_array(f0s)
    f1 = as_array(f1s)
    f2 = as_array(f2s)

    fig, ax = plt.subplots(figsize=(11, 5.8))
    line0, = ax.plot(times, f0, label="F0")
    line1, = ax.plot(times, f1, label="F1")
    line2, = ax.plot(times, f2, label="F2")

    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Hz")
    ax.set_ylim(0, 3000)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")

    vline = ax.axvline(times[0], linestyle="--", alpha=0.5)
    note = ax.annotate(
        "",
        xy=(0, 0),
        xytext=(12, 12),
        textcoords="offset points",
        bbox=dict(boxstyle="round", fc="w", alpha=0.85),
    )
    note.set_visible(False)

    def fmt(v):
        return "--" if v is None or not np.isfinite(v) else f"{v:.0f}"

    def on_move(event):
        if event.inaxes != ax or event.xdata is None:
            note.set_visible(False)
            fig.canvas.draw_idle()
            return
        idx = int(np.argmin(np.abs(times - event.xdata)))
        t = times[idx]
        vals = [f0[idx], f1[idx], f2[idx]]
        valid_vals = [v for v in vals if np.isfinite(v)]
        y = max(valid_vals) if valid_vals else 0
        text = (
            f"{t:.2f}s\n"
            f"F0 {fmt(f0[idx])} Hz\n"
            f"F1 {fmt(f1[idx])} Hz\n"
            f"F2 {fmt(f2[idx])} Hz\n"
            f"{levels[idx]:.1f} dB"
        )
        vline.set_xdata([t, t])
        note.xy = (t, y)
        note.set_text(text)
        note.set_visible(True)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)

    if png_path:
        fig.savefig(png_path, dpi=160, bbox_inches="tight")

    plt.show()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--png", type=Path, default=None)
    parser.add_argument("--time-step-ms", type=float, default=10.0)
    parser.add_argument("--gate-db", type=float, default=-32.0)
    parser.add_argument("--pitch-floor", type=float, default=70.0)
    parser.add_argument("--pitch-ceiling", type=float, default=750.0)
    parser.add_argument("--max-number-of-formants", type=float, default=5.0)
    parser.add_argument("--maximum-formant", type=float, default=5000.0)
    parser.add_argument("--formant-window-ms", type=float, default=50.0)
    parser.add_argument("--pre-emphasis-from", type=float, default=50.0)
    parser.add_argument("--smooth", type=int, default=3)
    args = parser.parse_args()

    if not args.audio.exists():
        raise FileNotFoundError(args.audio)

    times, f0s, f1s, f2s, levels, rows = analyze(
        audio_path=args.audio,
        time_step=args.time_step_ms / 1000.0,
        gate_db=args.gate_db,
        pitch_floor=args.pitch_floor,
        pitch_ceiling=args.pitch_ceiling,
        max_number_of_formants=args.max_number_of_formants,
        maximum_formant=args.maximum_formant,
        formant_window=args.formant_window_ms / 1000.0,
        pre_emphasis_from=args.pre_emphasis_from,
        smooth=max(1, args.smooth),
    )

    csv_path = args.csv or args.audio.with_suffix(".f0_f1_f2.csv")
    save_csv(csv_path, rows)
    print(f"CSV saved: {csv_path}")

    png_path = args.png
    if png_path:
        print(f"PNG will be saved: {png_path}")

    plot_interactive(times, f0s, f1s, f2s, levels, title=args.audio.name, png_path=png_path)


if __name__ == "__main__":
    main()
