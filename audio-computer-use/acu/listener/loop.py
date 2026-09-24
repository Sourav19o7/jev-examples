"""Microphone in, decisions out."""

import asyncio

import sounddevice as sd
import torch
from silero_vad import VADIterator, load_silero_vad

from acu.actuator import chrome
from acu.listener.segmenter import FRAME_SAMPLES, SAMPLE_RATE, Segmenter
from acu.listener.transcribe import DEFAULT_MODEL, Transcriber
from acu.listener.wake import strip_wake_word
from acu.report import console
from acu.session import handle


def listen(wake_word: str, dry_run: bool, model: str) -> int:
    transcriber = Transcriber(DEFAULT_MODEL)
    with console.status("Loading the speech model…"):
        transcriber.warm_up()

    vad_model = load_silero_vad()
    vad = VADIterator(vad_model, sampling_rate=SAMPLE_RATE, min_silence_duration_ms=400)
    segmenter = Segmenter()
    recent: list[str] = []

    console.print(
        f'Listening. Say "[bold]{wake_word}[/bold], open chrome". Ctrl-C to stop.'
    )

    speaking = False
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=FRAME_SAMPLES
        ) as stream:
            while True:
                block, _ = stream.read(FRAME_SAMPLES)
                frame = block[:, 0].copy()

                event = vad(torch.from_numpy(frame), return_seconds=True)
                if event:
                    if "start" in event:
                        speaking = True
                    if "end" in event:
                        speaking = False

                utterance = segmenter.push(frame, is_speech=speaking)
                if utterance is None:
                    continue

                text = transcriber.transcribe(utterance)
                if not text:
                    continue

                command = strip_wake_word(text, wake_word)
                if command is None:
                    console.print(f"[dim]ignored: {text}[/dim]")
                    continue

                screen = chrome.read_context()
                asyncio.run(handle(command, recent, screen, dry_run))
    except KeyboardInterrupt:
        console.print("\nStopped.")
    return 0
