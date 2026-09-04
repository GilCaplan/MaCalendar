"""The review panel is downstream of the pipeline's shape — enforced.

The thinking panel (and the iOS timeline) render a command's chain of thought
by keying off the trace's stage names and the brain version. If the engine's
pipeline is revamped — a stage added, renamed, or removed — the panel must be
updated to match, or it will draw the old system's chain for the new one.

This is the guard that makes "update the panel too" a build failure rather
than a thing someone remembers. It ties three things together:

  1. every stage the engine can emit → the panel knows how to draw it,
  2. the brain version → a CHAINS spec describing its chain of thought,
  3. that spec → only real, panel-drawable stages.

When one of these goes red, the message names what to update. See CLAUDE.md,
"The review panel is downstream of the pipeline".
"""

from __future__ import annotations

import pathlib

import pytest

import assistant.trace as trace

ICONS_DIR = (pathlib.Path(__file__).resolve().parents[2]
             / "assistant" / "calendar_ui" / "icons")

# The stage constants the engine (and the old brain) can put on a trace.
ENGINE_TRACE_STAGES = {
    trace.STT, trace.VOCAB, trace.RULE, trace.MEMORY, trace.LLM,
    trace.VALIDATE, trace.EXECUTE, trace.VERIFY, trace.DONE, trace.ERROR,
}


def _panel_icon_map() -> dict:
    from assistant.calendar_ui.thinking_panel import _STAGE_ICONS
    return _STAGE_ICONS


def test_the_panel_can_draw_every_stage_the_engine_emits():
    """A new pipeline stage without a panel icon draws as a blank/fallback —
    the exact silent-drift this guards. Add the stage to
    thinking_panel._STAGE_ICONS (and ship its icon) when you add it here."""
    icons = _panel_icon_map()
    missing = sorted(s for s in ENGINE_TRACE_STAGES if s not in icons)
    assert not missing, (
        f"the engine can emit stages {missing} that thinking_panel._STAGE_ICONS "
        "does not know how to draw — add them (and their icon files) so the "
        "review panel renders the new chain of thought")


def test_every_panel_icon_file_exists():
    """A mapped icon whose file was never added renders nothing."""
    if not ICONS_DIR.exists():
        pytest.skip("icons dir not present")
    icons = _panel_icon_map()
    for stage, name in icons.items():
        assert (ICONS_DIR / f"{name}.svg").exists(), (
            f"panel maps stage {stage!r} to icon {name!r} but "
            f"{name}.svg is missing from calendar_ui/icons")


def test_the_brain_version_has_a_chain_spec():
    """Bumping BRAIN_VERSION without describing the new chain leaves the panel
    with no spec to render the revamp by."""
    assert trace.BRAIN_VERSION in trace.CHAINS, (
        f"BRAIN_VERSION is {trace.BRAIN_VERSION!r} but trace.CHAINS has no "
        "entry for it — add the ordered (stage, label) chain that the review "
        "panel and the explorer diagram should show for this design")


def test_the_chain_spec_uses_only_drawable_stages():
    """A label in CHAINS pointing at a stage the panel cannot draw would show
    a gap in the rendered chain."""
    icons = _panel_icon_map()
    for version, spec in trace.CHAINS.items():
        for stage, label in spec:
            assert stage in ENGINE_TRACE_STAGES, (
                f"CHAINS[{version!r}] references stage {stage!r}, which is not a "
                "trace stage the engine emits")
            assert stage in icons, (
                f"CHAINS[{version!r}] references stage {stage!r}, which the panel "
                "has no icon for")


def test_every_chain_slot_has_in_depth_info():
    """The panel's ⓘ button reads trace.STAGE_INFO[version][label]. A chain slot
    without an entry is a step the panel renders but cannot explain — add its
    (heading, body) to STAGE_INFO, at the depth of the explorer page."""
    for version, spec in trace.CHAINS.items():
        info = trace.STAGE_INFO.get(version, {})
        for _stage, label in spec:
            assert label in info, (
                f"CHAINS[{version!r}] has a slot {label!r} with no STAGE_INFO "
                "entry — add its (heading, body) so the ⓘ can explain it")
            heading, body = info[label]
            assert heading.strip() and body.strip(), (
                f"STAGE_INFO[{version!r}][{label!r}] has an empty heading or body")
