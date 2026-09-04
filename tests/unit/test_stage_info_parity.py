"""The iOS chain-info copy must match the host's STAGE_INFO.

The Mac review panel reads `assistant.trace.STAGE_INFO` directly; the iOS
`ThinkingView` carries a hand-mirrored Swift copy (`EngineChain.scaffold` in
VocabularyView.swift), because Swift can't import Python. This pins the two
together, so editing a step's explanation on one side but not the other fails
the build — the same drift guard `test_artifact_claims` gives the published
pages and `test_panel_agreement` gives the chain itself.
"""
from __future__ import annotations

import pathlib
import re

import pytest

import assistant.trace as trace

IOS = (pathlib.Path(__file__).resolve().parents[2]
       / "MACalendar-iOS" / "MACalendar-iOS" / "Views" / "VocabularyView.swift")


def _norm(s: str) -> str:
    """Collapse whitespace so a body wrapped across Swift source lines still
    matches the single-line Python string."""
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.skipif(not IOS.exists(), reason="iOS sources not present")
def test_ios_chain_info_matches_the_host():
    swift = _norm(IOS.read_text(encoding="utf-8"))
    for label, (heading, body) in trace.STAGE_INFO[trace.BRAIN_VERSION].items():
        assert _norm(label) in swift, (
            f"iOS scaffold (EngineChain.scaffold) is missing chain slot {label!r}")
        assert _norm(heading) in swift, (
            f"iOS scaffold is missing the heading {heading!r} for slot {label!r}")
        assert _norm(body) in swift, (
            f"iOS scaffold's in-depth copy for {label!r} has drifted from "
            "trace.STAGE_INFO — update EngineChain.scaffold in VocabularyView.swift")
