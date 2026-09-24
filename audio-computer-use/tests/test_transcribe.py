import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from acu.listener.transcribe import Transcriber


@pytest.mark.skipif(not shutil.which("say"), reason="macOS say unavailable")
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg unavailable")
def test_spoken_command_is_transcribed(tmp_path: Path):
    aiff, wav = tmp_path / "s.aiff", tmp_path / "s.wav"
    subprocess.run(["say", "-o", str(aiff), "open chrome"], check=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff),
         "-ar", "16000", "-ac", "1", str(wav)], check=True)

    with wave.open(str(wav)) as handle:
        samples = np.frombuffer(
            handle.readframes(handle.getnframes()), dtype=np.int16
        ).astype(np.float32) / 32768.0

    text = Transcriber().transcribe(samples).lower()
    assert "chrome" in text
