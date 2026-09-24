import numpy as np
from acu.listener.segmenter import Segmenter, FRAME_SAMPLES


def frame(value: float = 0.0) -> np.ndarray:
    return np.full(FRAME_SAMPLES, value, dtype=np.float32)


def test_silence_alone_produces_no_utterance():
    seg = Segmenter(silence_timeout_frames=2)
    assert seg.push(frame(), is_speech=False) is None
    assert seg.push(frame(), is_speech=False) is None


def test_speech_then_silence_emits_utterance():
    seg = Segmenter(silence_timeout_frames=2)
    assert seg.push(frame(0.5), is_speech=True) is None
    assert seg.push(frame(), is_speech=False) is None
    out = seg.push(frame(), is_speech=False)
    assert out is not None
    assert len(out) == FRAME_SAMPLES * 3


def test_speech_running_to_end_is_recovered_by_flush():
    seg = Segmenter(silence_timeout_frames=2)
    seg.push(frame(0.5), is_speech=True)
    seg.push(frame(0.5), is_speech=True)
    out = seg.flush()
    assert out is not None
    assert len(out) == FRAME_SAMPLES * 2


def test_flush_with_no_speech_returns_none():
    assert Segmenter().flush() is None


def test_segmenter_resets_between_utterances():
    seg = Segmenter(silence_timeout_frames=1)
    seg.push(frame(0.5), is_speech=True)
    first = seg.push(frame(), is_speech=False)
    assert first is not None
    seg.push(frame(0.5), is_speech=True)
    second = seg.push(frame(), is_speech=False)
    assert second is not None
    assert len(second) == FRAME_SAMPLES * 2
