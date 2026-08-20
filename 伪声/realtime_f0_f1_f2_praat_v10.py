"""
Realtime F0 / F1 / F2 monitor using Praat/Parselmouth.
v10:
- Uses Praat's Burg formant estimator through praat-parselmouth instead of my simple LPC.
- Manual capture only: Space starts/stops drawing.
- Hard gate: frames below --gate-db are ignored.
- Hover graph to read F0/F1/F2 at that point.
- R clears the graph.

Install:
    pip install numpy sounddevice praat-parselmouth

Run:
    python realtime_f0_f1_f2_praat_v10.py

Useful:
    python realtime_f0_f1_f2_praat_v10.py --list-devices
    python realtime_f0_f1_f2_praat_v10.py --device 1
    python realtime_f0_f1_f2_praat_v10.py --gate-db -32
    python realtime_f0_f1_f2_praat_v10.py --maximum-formant 5000
    python realtime_f0_f1_f2_praat_v10.py --window-ms 90 --update-ms 40

Notes:
- This is closer to Praat than the previous hand-written LPC versions.
- F1/F2 are still not magic. Sustained vowels are much more reliable than full sentences.
"""

from __future__ import annotations

import argparse
import math
import queue
import sys
import time
from collections import deque
from typing import Optional, Sequence

import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import ttk

try:
    import parselmouth
except Exception as e:
    parselmouth = None
    PARSELMOUTH_IMPORT_ERROR = e
else:
    PARSELMOUTH_IMPORT_ERROR = None


def db_from_rms(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(x * x) + 1e-12))
    return 20.0 * math.log10(rms + 1e-12)


def hz_text(x: Optional[float]) -> str:
    return "--" if x is None or not np.isfinite(x) else f"{x:.0f}"


def clean_value(x) -> Optional[float]:
    try:
        x = float(x)
    except Exception:
        return None
    if not np.isfinite(x) or x <= 0:
        return None
    return x


def praat_estimate(
    frame: np.ndarray,
    fs: int,
    pitch_floor: float,
    pitch_ceiling: float,
    max_number_of_formants: float,
    maximum_formant: float,
    formant_window_s: float,
    pre_emphasis_from: float,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float], str]:
    """Return f0/f1/f2/f3 using Praat via Parselmouth."""
    if parselmouth is None:
        return None, None, None, None, "Parselmouth import failed"

    x = frame.astype(np.float64)
    x -= np.mean(x)
    peak = np.max(np.abs(x)) + 1e-12
    # Avoid pathological tiny signals, but do not normalize silence into voice.
    if peak > 0:
        x = x / max(1.0, peak)

    try:
        snd = parselmouth.Sound(x, sampling_frequency=fs)
        mid = snd.xmin + snd.duration / 2.0

        pitch = snd.to_pitch(
            time_step=None,
            pitch_floor=pitch_floor,
            pitch_ceiling=pitch_ceiling,
        )
        f0 = clean_value(pitch.get_value_at_time(mid))

        formant = snd.to_formant_burg(
            time_step=None,
            max_number_of_formants=max_number_of_formants,
            maximum_formant=maximum_formant,
            window_length=formant_window_s,
            pre_emphasis_from=pre_emphasis_from,
        )
        f1 = clean_value(formant.get_value_at_time(1, mid))
        f2 = clean_value(formant.get_value_at_time(2, mid))
        f3 = clean_value(formant.get_value_at_time(3, mid))
        return f0, f1, f2, f3, "ok"
    except Exception as e:
        return None, None, None, None, f"Praat error: {e}"


class HistoryCanvas(tk.Canvas):
    def __init__(self, master, width: int = 800, height: int = 370, **kwargs):
        super().__init__(master, width=width, height=height, bg="#101010", highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.pad_left = 58
        self.pad_right = 18
        self.pad_top = 18
        self.pad_bottom = 28
        self.history: list[tuple[float, Optional[float], Optional[float], Optional[float], float]] = []
        self.hover_idx: Optional[int] = None
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)

    def _x(self, idx: int, n: int) -> float:
        if n <= 1:
            return self.pad_left
        usable = self.width - self.pad_left - self.pad_right
        return self.pad_left + usable * idx / (n - 1)

    def _idx_from_x(self, x: float) -> Optional[int]:
        n = len(self.history)
        if n == 0:
            return None
        usable = self.width - self.pad_left - self.pad_right
        ratio = (x - self.pad_left) / usable
        idx = round(ratio * (n - 1))
        if 0 <= idx < n:
            return idx
        return None

    def _y(self, hz: float, ymin: float = 0.0, ymax: float = 3000.0) -> float:
        usable = self.height - self.pad_top - self.pad_bottom
        hz = max(ymin, min(ymax, hz))
        return self.pad_top + usable * (1.0 - (hz - ymin) / (ymax - ymin))

    def draw(self, history: Sequence[tuple[float, Optional[float], Optional[float], Optional[float], float]], keep_hover: bool = True):
        self.history = list(history)
        self.delete("all")

        for hz in [0, 500, 1000, 1500, 2000, 2500, 3000]:
            y = self._y(hz)
            self.create_line(self.pad_left, y, self.width - self.pad_right, y, fill="#2c2c2c")
            self.create_text(8, y, text=f"{hz}", fill="#bbbbbb", anchor="w", font=("Arial", 9))

        self.create_text(self.pad_left, self.height - 8, text="manual captured frames", fill="#bbbbbb", anchor="w", font=("Arial", 9))
        self.create_text(self.width - self.pad_right, self.height - 8, text="latest", fill="#bbbbbb", anchor="e", font=("Arial", 9))

        def draw_series(col: int, color: str, label: str):
            pts: list[tuple[float, float]] = []
            n = len(self.history)
            for i, item in enumerate(self.history):
                hz = item[col]
                if hz is None:
                    if len(pts) >= 2:
                        self._polyline(pts, color)
                    pts = []
                    continue
                pts.append((self._x(i, n), self._y(hz)))
            if len(pts) >= 2:
                self._polyline(pts, color)

            for i in range(len(self.history) - 1, -1, -1):
                hz = self.history[i][col]
                if hz is not None:
                    x, y = self._x(i, len(self.history)), self._y(hz)
                    self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline="")
                    self.create_text(x - 8, y - 8, text=label, fill=color, anchor="e", font=("Arial", 9, "bold"))
                    break

        draw_series(1, "#41c7ff", "F0")
        draw_series(2, "#40e060", "F1")
        draw_series(3, "#e64a4a", "F2")

        if keep_hover and self.hover_idx is not None and 0 <= self.hover_idx < len(self.history):
            self._draw_hover(self.hover_idx)

    def _polyline(self, pts: Sequence[tuple[float, float]], color: str):
        flat: list[float] = []
        for x, y in pts:
            flat.extend([x, y])
        self.create_line(*flat, fill=color, width=2, smooth=True)

    def _draw_hover(self, idx: int):
        if not self.history:
            return
        n = len(self.history)
        x = self._x(idx, n)
        self.create_line(x, self.pad_top, x, self.height - self.pad_bottom, fill="#aaaaaa", dash=(3, 3), tags="hover")
        t, f0, f1, f2, level = self.history[idx]
        latest_t = self.history[-1][0]
        ago = latest_t - t
        text = f"-{ago:.2f}s   F0 {hz_text(f0)} Hz   F1 {hz_text(f1)} Hz   F2 {hz_text(f2)} Hz   {level:.1f} dB"

        box_w = 360
        box_h = 28
        bx = min(max(x + 10, self.pad_left), self.width - self.pad_right - box_w)
        by = self.pad_top + 8
        self.create_rectangle(bx, by, bx + box_w, by + box_h, fill="#202020", outline="#666666", tags="hover")
        self.create_text(bx + 10, by + box_h / 2, text=text, fill="#eeeeee", anchor="w", font=("Arial", 10), tags="hover")

        for col, color in [(1, "#41c7ff"), (2, "#40e060"), (3, "#e64a4a")]:
            hz = self.history[idx][col]
            if hz is not None:
                y = self._y(hz)
                self.create_oval(x - 4, y - 4, x + 4, y + 4, outline=color, width=2, tags="hover")

    def on_motion(self, event):
        idx = self._idx_from_x(event.x)
        if idx != self.hover_idx:
            self.hover_idx = idx
            self.draw(self.history, keep_hover=True)

    def on_leave(self, event):
        self.hover_idx = None
        self.draw(self.history, keep_hover=False)


class MonitorApp:
    def __init__(
        self,
        fs: int,
        blocksize: int,
        device: Optional[int],
        history_seconds: float,
        gate_db: float,
        update_ms: int,
        window_ms: float,
        pitch_floor: float,
        pitch_ceiling: float,
        max_number_of_formants: float,
        maximum_formant: float,
        formant_window_ms: float,
        pre_emphasis_from: float,
        smooth: int,
    ):
        self.fs = fs
        self.blocksize = blocksize
        self.device = device
        self.gate_db = gate_db
        self.update_ms = update_ms
        self.pitch_floor = pitch_floor
        self.pitch_ceiling = pitch_ceiling
        self.max_number_of_formants = max_number_of_formants
        self.maximum_formant = maximum_formant
        self.formant_window_s = formant_window_ms / 1000.0
        self.pre_emphasis_from = pre_emphasis_from

        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self.ring = np.zeros(max(256, int(window_ms / 1000.0 * fs)), dtype=np.float32)

        self.smooth_f0: deque[float] = deque(maxlen=smooth)
        self.smooth_f1: deque[float] = deque(maxlen=smooth)
        self.smooth_f2: deque[float] = deque(maxlen=smooth)

        self.capturing = False
        self.max_points = max(20, int(history_seconds * 1000 / self.update_ms))
        self.history: deque[tuple[float, Optional[float], Optional[float], Optional[float], float]] = deque(maxlen=self.max_points)

        self.root = tk.Tk()
        self.root.title("Realtime F0 / F1 / F2 — Praat backend v10")
        self.root.geometry("880x640")
        self.root.configure(bg="#181818", padx=16, pady=14)

        self.status = tk.StringVar(value="starting…")
        self.capture_text = tk.StringVar(value="STOPPED — press Space to capture")
        self.f0_text = tk.StringVar(value="F0  -- Hz")
        self.f1_text = tk.StringVar(value="F1  -- Hz")
        self.f2_text = tk.StringVar(value="F2  -- Hz")
        self.db_text = tk.StringVar(value="Level  -- dB")
        self.raw_text = tk.StringVar(value="Praat backend")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TFrame", background="#181818")
        style.configure("TButton", font=("Arial", 10))
        style.configure("Small.TLabel", background="#181818", foreground="#dddddd", font=("Arial", 10))
        style.configure("Capture.TLabel", background="#181818", foreground="#ffd36e", font=("Arial", 12, "bold"))
        style.configure("Big0.TLabel", background="#181818", foreground="#41c7ff", font=("Arial", 30, "bold"))
        style.configure("Big1.TLabel", background="#181818", foreground="#40e060", font=("Arial", 30, "bold"))
        style.configure("Big2.TLabel", background="#181818", foreground="#e64a4a", font=("Arial", 30, "bold"))

        top = ttk.Frame(self.root)
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.status, style="Small.TLabel").pack(anchor="w")
        ttk.Label(top, textvariable=self.capture_text, style="Capture.TLabel").pack(anchor="w")
        ttk.Label(top, text="Space: start/stop capture    R: clear    Hover graph: read values", style="Small.TLabel").pack(anchor="w")

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", pady=(8, 4))
        ttk.Button(controls, text="Start Capture", command=self.start_capture).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Stop Capture", command=self.stop_capture).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Clear", command=self.clear_history).pack(side="left", padx=(0, 8))

        nums = ttk.Frame(self.root)
        nums.pack(fill="x", pady=(12, 8))
        ttk.Label(nums, textvariable=self.f0_text, style="Big0.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 28))
        ttk.Label(nums, textvariable=self.f1_text, style="Big1.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 28))
        ttk.Label(nums, textvariable=self.f2_text, style="Big2.TLabel").grid(row=0, column=2, sticky="w")

        ttk.Label(self.root, textvariable=self.db_text, style="Small.TLabel").pack(anchor="w")
        ttk.Label(self.root, textvariable=self.raw_text, style="Small.TLabel").pack(anchor="w", pady=(0, 10))

        self.canvas = HistoryCanvas(self.root, width=820, height=380)
        self.canvas.pack(fill="both", expand=True)

        self.root.bind("<space>", lambda _e: self.toggle_capture())
        self.root.bind("r", lambda _e: self.clear_history())
        self.root.bind("R", lambda _e: self.clear_history())

        self.stream: Optional[sd.InputStream] = None

    def reset_trackers(self):
        self.smooth_f0.clear()
        self.smooth_f1.clear()
        self.smooth_f2.clear()

    def start_capture(self):
        self.capturing = True
        self.reset_trackers()
        self.capture_text.set("CAPTURING — press Space to stop")

    def stop_capture(self):
        self.capturing = False
        self.capture_text.set("STOPPED — press Space to capture")

    def toggle_capture(self):
        self.stop_capture() if self.capturing else self.start_capture()

    def clear_history(self):
        self.history.clear()
        self.reset_trackers()
        self.canvas.draw(list(self.history))
        self.f0_text.set("F0  -- Hz")
        self.f1_text.set("F1  -- Hz")
        self.f2_text.set("F2  -- Hz")

    def audio_callback(self, indata, frames, time_info, status):
        mono = indata[:, 0].copy()
        try:
            self.q.put_nowait(mono)
        except queue.Full:
            pass

    def start_stream(self):
        if parselmouth is None:
            self.status.set(f"Install first: pip install praat-parselmouth  ({PARSELMOUTH_IMPORT_ERROR})")
            return
        self.stream = sd.InputStream(
            samplerate=self.fs,
            blocksize=self.blocksize,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self.audio_callback,
        )
        self.stream.start()
        dev = sd.query_devices(self.device, "input") if self.device is not None else sd.query_devices(kind="input")
        self.status.set(
            f"Mic: {dev.get('name', 'default')} | Praat Burg | gate {self.gate_db:g} dB | maxFormant {self.maximum_formant:g} Hz"
        )

    def update(self):
        got = False
        while True:
            try:
                chunk = self.q.get_nowait()
            except queue.Empty:
                break
            got = True
            n = len(chunk)
            if n >= len(self.ring):
                self.ring[:] = chunk[-len(self.ring):]
            else:
                self.ring[:-n] = self.ring[n:]
                self.ring[-n:] = chunk

        if got:
            frame = self.ring.copy()
            rms_db = db_from_rms(frame)
            self.db_text.set(f"Level {rms_db:5.1f} dB")

            if rms_db < self.gate_db:
                self.raw_text.set(f"blocked by gate: {rms_db:.1f} < {self.gate_db:g} dB")
                self.root.after(self.update_ms, self.update)
                return

            f0, f1, f2, f3, msg = praat_estimate(
                frame=frame,
                fs=self.fs,
                pitch_floor=self.pitch_floor,
                pitch_ceiling=self.pitch_ceiling,
                max_number_of_formants=self.max_number_of_formants,
                maximum_formant=self.maximum_formant,
                formant_window_s=self.formant_window_s,
                pre_emphasis_from=self.pre_emphasis_from,
            )

            if f0 is not None:
                self.smooth_f0.append(f0)
            if f1 is not None:
                self.smooth_f1.append(f1)
            if f2 is not None:
                self.smooth_f2.append(f2)

            f0s = float(np.median(self.smooth_f0)) if self.smooth_f0 else None
            f1s = float(np.median(self.smooth_f1)) if self.smooth_f1 else None
            f2s = float(np.median(self.smooth_f2)) if self.smooth_f2 else None

            self.f0_text.set(f"F0 {f0s:5.0f} Hz" if f0s is not None else "F0  -- Hz")
            self.f1_text.set(f"F1 {f1s:5.0f} Hz" if f1s is not None else "F1  -- Hz")
            self.f2_text.set(f"F2 {f2s:5.0f} Hz" if f2s is not None else "F2  -- Hz")
            self.raw_text.set(
                f"{msg} | raw: F0 {hz_text(f0)} / F1 {hz_text(f1)} / F2 {hz_text(f2)} / F3 {hz_text(f3)}"
            )

            if self.capturing and (f0s is not None or f1s is not None or f2s is not None):
                self.history.append((time.time(), f0s, f1s, f2s, rms_db))
                self.canvas.draw(list(self.history))

        self.root.after(self.update_ms, self.update)

    def run(self):
        try:
            self.start_stream()
        except Exception as e:
            self.status.set(f"Audio error: {e}")
        self.root.after(self.update_ms, self.update)
        self.root.mainloop()
        if self.stream:
            self.stream.stop()
            self.stream.close()


def list_devices():
    print(sd.query_devices())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--fs", type=int, default=16000)
    parser.add_argument("--blocksize", type=int, default=512)
    parser.add_argument("--history-seconds", type=float, default=10.0)
    parser.add_argument("--gate-db", type=float, default=-32.0)
    parser.add_argument("--update-ms", type=int, default=40)
    parser.add_argument("--window-ms", type=float, default=100.0)
    parser.add_argument("--pitch-floor", type=float, default=70.0)
    parser.add_argument("--pitch-ceiling", type=float, default=750.0)
    parser.add_argument("--max-number-of-formants", type=float, default=5.0)
    parser.add_argument("--maximum-formant", type=float, default=5000.0)
    parser.add_argument("--formant-window-ms", type=float, default=50.0)
    parser.add_argument("--pre-emphasis-from", type=float, default=50.0)
    parser.add_argument("--smooth", type=int, default=3)
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    app = MonitorApp(
        fs=args.fs,
        blocksize=args.blocksize,
        device=args.device,
        history_seconds=args.history_seconds,
        gate_db=args.gate_db,
        update_ms=args.update_ms,
        window_ms=args.window_ms,
        pitch_floor=args.pitch_floor,
        pitch_ceiling=args.pitch_ceiling,
        max_number_of_formants=args.max_number_of_formants,
        maximum_formant=args.maximum_formant,
        formant_window_ms=args.formant_window_ms,
        pre_emphasis_from=args.pre_emphasis_from,
        smooth=max(1, args.smooth),
    )
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
