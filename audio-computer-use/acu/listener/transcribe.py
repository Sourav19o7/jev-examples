"""Whisper via MLX. The model is loaded once; a per-utterance load costs ~50s."""

import mlx_whisper
import numpy as np

DEFAULT_MODEL = "mlx-community/whisper-small.en-mlx"


class Transcriber:
    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        self._warm = False

    def warm_up(self) -> None:
        """Pay the load cost before the first real command, not during it."""
        if not self._warm:
            self.transcribe(np.zeros(16000, dtype=np.float32))
            self._warm = True

    def transcribe(self, samples: np.ndarray) -> str:
        result = mlx_whisper.transcribe(
            samples, path_or_hf_repo=self._model, language="en",
            condition_on_previous_text=False,
        )
        self._warm = True
        return result["text"].strip()
