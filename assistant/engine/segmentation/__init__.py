"""Segmentation — one command in, a list of (action, time, tag) items out.

    FastSeg (deterministic) -> LLMSeg (OFF by default) -> ACCEPT

`old_seg` is still the stage the engine runs; FastSeg/LLMSeg are proven on their
own dataset first and promoted deliberately. See ARCHITECTURE.md.
"""
from assistant.engine.segmentation import old_seg     # noqa: F401
