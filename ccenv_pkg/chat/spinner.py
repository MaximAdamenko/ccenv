"""Braille spinner for terminal waiting periods. Zero ccenv dependencies."""

from __future__ import annotations

import sys
import threading


class Spinner:
    """Animated TTY spinner. All public methods are no-ops when stdout is not a TTY."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _INTERVAL = 0.08  # seconds per frame

    def __init__(self) -> None:
        self._label = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tty = sys.stdout.isatty()

    def start(self, label: str = "") -> None:
        if not self._tty:
            return
        self._label = label
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._tty:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _run(self) -> None:
        frames = self.FRAMES
        n = len(frames)
        i = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r{frames[i % n]} {self._label}")
            sys.stdout.flush()
            self._stop.wait(self._INTERVAL)
            i += 1
