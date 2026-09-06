"""Write settings back to config.yaml — section-scoped, comment-preserving.

The settings dialog used to persist by ~15 global regex substitutions over the
raw file ("rate: \\d+" → first match anywhere), each new setting hand-rolling
its own pattern. A yaml round-trip would be simpler but destroys the file's
comments, which is why the surgery existed. This module keeps the good part
(comments and layout survive) and fixes the bad parts:

  • every rewrite is scoped to its TOP-LEVEL SECTION, so `rate:` under `tts:`
    can never clobber a `rate:` somewhere else;
  • a key missing from an older config is inserted at its section's end;
  • a missing section is appended whole;
  • inline comments on a rewritten line are preserved.

    set_values({"tts": {"mute": True, "rate": 180}, "ui": {"theme": "dark"}})
"""
from __future__ import annotations

import os
import re

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def _literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    return f'"{value}"'


def _section_span(lines: "list[str]", section: str) -> "tuple[int, int] | None":
    """(start, end) of the section's body: after `section:` up to the next
    top-level key. None if the section doesn't exist."""
    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(section)}\s*:\s*(#.*)?$", ln):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^[A-Za-z_][\w-]*\s*:", lines[j]):   # next top-level key
            end = j
            break
    return start, end


def set_values(updates: "dict[str, dict]", path: str = CONFIG_PATH) -> bool:
    """Apply {section: {key: value}} to the yaml file in place.

    Returns False (and writes nothing) if the file doesn't exist — a missing
    config.yaml is a setup problem the dialog reports, not one to mask by
    creating a comment-less file."""
    if not os.path.exists(path):
        return False
    with open(path, "r") as f:
        lines = f.read().splitlines()

    for section, kv in updates.items():
        if section == "":
            # top-level scalars (theme:, confirmation_level:, …)
            for key, value in kv.items():
                pat = re.compile(rf"^({re.escape(key)}\s*:\s*)([^#]*?)(\s*#.*)?$")
                for i, ln in enumerate(lines):
                    m = pat.match(ln)
                    if m:
                        lines[i] = m.group(1) + _literal(value) + (m.group(3) or "")
                        break
                else:
                    lines.append(f"{key}: {_literal(value)}")
            continue
        span = _section_span(lines, section)
        if span is None:
            lines.append(f"{section}:")
            for key, value in kv.items():
                lines.append(f"  {key}: {_literal(value)}")
            continue
        start, end = span
        for key, value in kv.items():
            pat = re.compile(rf"^(\s+{re.escape(key)}\s*:\s*)([^#]*?)(\s*#.*)?$")
            for i in range(start, end):
                m = pat.match(lines[i])
                if m:
                    lines[i] = m.group(1) + _literal(value) + (m.group(3) or "")
                    break
            else:
                # insert before the section's trailing blank lines
                at = end
                while at > start and not lines[at - 1].strip():
                    at -= 1
                lines.insert(at, f"  {key}: {_literal(value)}")
                end += 1
        # spans of later sections may have shifted; recompute nothing — each
        # section is located fresh from the current lines on its own turn.

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return True
