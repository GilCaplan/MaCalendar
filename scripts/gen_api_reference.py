"""Generate DOCUMENTATION/API_REFERENCE.md from the Flask routes in assistant/api/server.py.

Each endpoint's first docstring line is used as its description, so the doc
cannot drift from the code. Run after adding endpoints:

    python -m scripts.gen_api_reference
"""

from __future__ import annotations

import ast
import os
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assistant", "api", "server.py")
OUT = os.path.join(ROOT, "DOCUMENTATION", "API_REFERENCE.md")


def main() -> None:
    tree = ast.parse(open(SRC, encoding="utf-8").read())
    groups: "OrderedDict[str, list[tuple[str, str, str]]]" = OrderedDict()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ("get", "post", "put", "patch", "delete", "route") and dec.args:
                path = dec.args[0].value if isinstance(dec.args[0], ast.Constant) else "?"
                method = dec.func.attr.upper()
                if method == "ROUTE":
                    for kw in dec.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            method = "/".join(e.value for e in kw.value.elts if isinstance(e, ast.Constant))
                doc = (ast.get_docstring(node) or "").strip().splitlines()
                desc = doc[0] if doc else ""
                group = path.strip("/").split("/")[0] or "root"
                groups.setdefault(group, []).append((method, path, desc))
    lines = ["# API reference", "",
             "Generated from `assistant/api/server.py` by `python -m scripts.gen_api_reference` — do not edit by hand.",
             "All endpoints are served by the Mac at `http://<tailscale-ip>:8080`; the iOS app is the only client. "
             "Path parameters use Flask syntax (`<int:id>`).", ""]
    for group, items in groups.items():
        lines += [f"## /{group}", "", "| Method | Path | What it does |", "|---|---|---|"]
        for m, p, d in sorted(items, key=lambda x: (x[1], x[0])):
            lines.append(f"| `{m}` | `{p}` | {d.replace('|', '\\|')} |")
        lines.append("")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"{sum(len(v) for v in groups.values())} endpoints → {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
