"""Microphone in, decisions out."""

import asyncio

import sounddevice as sd
import torch
from silero_vad import VADIterator, load_silero_vad

from acu.actuator import chrome
from acu.listener.segmenter import FRAME_SAMPLES, SAMPLE_RATE, Segmenter
from acu.listener.transcribe import DEFAULT_MODEL, Transcriber
from acu.listener.wake import strip_wake_word
from acu.policy import Decision
from acu.report import console
from acu.session import handle

AFFIRMATIVE = {"yes", "yeah", "yep", "yup", "sure", "confirm", "ok", "okay", "do it"}

# A confirmation is a word or two; stop waiting rather than block the loop.
CONFIRM_FRAME_BUDGET = int(6 * SAMPLE_RATE / FRAME_SAMPLES)


def is_affirmative(answer: str) -> bool:
    return answer.strip().lower().rstrip(".!?,") in AFFIRMATIVE


class Listener:
    def __init__(self, transcriber: Transcriber, vad, dry_run: bool):
        self._transcriber = transcriber
        self._vad = vad
        self._dry_run = dry_run
        self._speaking = False

    def _read_utterance(self, stream, budget: int | None = None):
        """Collect frames until the segmenter closes one, or the budget runs out."""
        segmenter = Segmenter()
        frames = 0
        while budget is None or frames < budget:
            block, _overflowed = stream.read(FRAME_SAMPLES)
            frame = block[:, 0].copy()
            frames += 1

            event = self._vad(torch.from_numpy(frame), return_seconds=True)
            if event:
                if "start" in event:
                    self._speaking = True
                if "end" in event:
                    self._speaking = False

            utterance = segmenter.push(frame, is_speech=self._speaking)
            if utterance is not None:
                return utterance
        return segmenter.flush()

    def confirm_by_voice(self, stream):
        def _confirm(decision: Decision) -> bool:
            console.print(f"  [yellow]{decision.verb}?[/yellow] say yes or no")
            utterance = self._read_utterance(stream, CONFIRM_FRAME_BUDGET)
            if utterance is None:
                console.print("  [dim]no answer — skipped[/dim]")
                return False
            answer = self._transcriber.transcribe(utterance)
            console.print(f"  [dim]heard: {answer}[/dim]")
            return is_affirmative(answer)

        return _confirm

    def run(self, wake_word: str) -> None:
        recent: list[str] = []
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=FRAME_SAMPLES,
        ) as stream:
            confirm = self.confirm_by_voice(stream)
            while True:
                utterance = self._read_utterance(stream)
                if utterance is None:
                    continue

                text = self._transcriber.transcribe(utterance)
                if not text:
                    continue

                command = strip_wake_word(text, wake_word)
                if command is None:
                    console.print(f"[dim]ignored: {text}[/dim]")
                    continue

                screen = chrome.read_context()
                asyncio.run(
                    handle(command, recent, screen, self._dry_run, confirm)
                )


def listen(wake_word: str, dry_run: bool, model: str) -> int:
    transcriber = Transcriber(DEFAULT_MODEL)
    with console.status("Loading the speech model…"):
        transcriber.warm_up()

    vad = VADIterator(
        load_silero_vad(), sampling_rate=SAMPLE_RATE, min_silence_duration_ms=400
    )

    console.print(
        f'Listening. Say "[bold]{wake_word}[/bold], open chrome". Ctrl-C to stop.'
    )

    try:
        Listener(transcriber, vad, dry_run).run(wake_word)
    except KeyboardInterrupt:
        console.print("\nStopped.")
    return 0
