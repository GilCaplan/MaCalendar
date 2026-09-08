"""FastSeg — the deterministic half. cut -> assign time -> tag, ~10ms, no model."""
from assistant.engine.segmentation.fastseg import invariant   # noqa: F401
from assistant.engine.segmentation.fastseg.fastseg import fastseg  # noqa: F401
