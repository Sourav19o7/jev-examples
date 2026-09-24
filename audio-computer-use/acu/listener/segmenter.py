"""Group frames into utterances. No audio device here, so this stays testable."""

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


class Segmenter:
    def __init__(self, silence_timeout_frames: int = 16):
        self._silence_timeout = silence_timeout_frames
        self._frames: list[np.ndarray] = []
        self._silent_run = 0

    def push(self, frame: np.ndarray, is_speech: bool) -> np.ndarray | None:
        if is_speech:
            self._frames.append(frame)
            self._silent_run = 0
            return None

        if not self._frames:
            return None

        self._frames.append(frame)
        self._silent_run += 1
        if self._silent_run >= self._silence_timeout:
            return self._take()
        return None

    def flush(self) -> np.ndarray | None:
        """Silero emits a start without an end when speech runs to the buffer's
        edge, so the final utterance is only recoverable this way."""
        return self._take() if self._frames else None

    def _take(self) -> np.ndarray:
        utterance = np.concatenate(self._frames)
        self._frames = []
        self._silent_run = 0
        return utterance
