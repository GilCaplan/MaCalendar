"""Render explorer.html in a real browser and screenshot every view.

Why this exists: the explorer was rebuilt twice without anyone LOOKING at the
result, and both times it shipped broken in a way no amount of source-reading
catches — the four view tabs all drew the same diagram, because the tab only
swapped a menu strip. Reading the HTML cannot see that. A screenshot can.

    python3 -m scripts.shoot_explorer            # every view, full page
    python3 -m scripts.shoot_explorer --dark     # the theme Gil actually uses
    python3 -m scripts.shoot_explorer --open X   # also open component X's panel

Run it with the SYSTEM `python3`, not `.venv/bin/python` — playwright is
installed in the system interpreter only, and the venv run dies on the import
with a message that reads like the browser is missing rather than the package.

Then LOOK at the PNGs in the output directory before claiming a page is done.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "DOCUMENTATION" / "artifacts" / "explorer.html"
VIEWS = ["system", "engine", "loop", "eval"]


async def run(out: pathlib.Path, dark: bool, open_ids: list[str]) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright not installed — pip install playwright && playwright install chromium")
        return 2

    out.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 1600, "height": 1100},
            device_scale_factor=2,
            color_scheme="dark" if dark else "light",
        )
        await page.goto(SRC.as_uri())
        await page.wait_for_timeout(1000)

        suffix = "_dark" if dark else ""
        for view in VIEWS:
            tab = page.locator(f"[data-view={view}]")
            if not await tab.count():
                print(f"!! no tab for view {view!r}")
                continue
            await tab.first.click()
            await page.wait_for_timeout(600)
            path = out / f"view_{view}{suffix}.png"
            await page.screenshot(path=str(path), full_page=True)

            # Fingerprint ONLY the drawing area, so "the tab changed the menu
            # but not the diagram" is caught mechanically rather than by eye.
            canvas = page.locator(".stage, .canvas, [data-canvas], main").first
            shot = await canvas.screenshot() if await canvas.count() else await page.screenshot()
            digests[view] = hashlib.sha256(shot).hexdigest()[:12]
            print(f"{view:8s} -> {path.name}  canvas:{digests[view]}")

        for cid in open_ids:
            # explorer.html marks its openable groups with data-panel; the other
            # two attributes are kept for the older pages. A component lives on
            # exactly one view, and the loop above leaves the LAST view showing —
            # so hunt for the tab that makes this one visible before clicking it,
            # or the click times out on a hidden <g> and reports nothing useful.
            sel = f"[data-panel='{cid}'], [data-open='{cid}'], [data-id='{cid}']"
            target = page.locator(sel).first
            if not await target.count():
                print(f"!! no component {cid!r}")
                continue
            for view in VIEWS:
                if await target.is_visible():
                    break
                await page.locator(f"[data-view={view}]").first.click()
                await page.wait_for_timeout(300)
            if not await target.is_visible():
                print(f"!! {cid!r} is on no view")
                continue
            # A real mouse click lands in the middle of the group's box, which
            # for a fill="none" frame is a hole — the svg swallows it. The page
            # listens on the svg and walks up to [data-panel], so a bubbling
            # synthetic click is both faithful to the handler and hole-proof.
            await target.evaluate(
                "el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))")
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"open_{cid}{suffix}.png"), full_page=True)
            print(f"opened {cid}")

        await browser.close()

    # every view must draw something DIFFERENT — identical canvases mean the
    # tabs are decorative, which is exactly the bug this script was written for
    collisions = [v for v in digests if list(digests.values()).count(digests[v]) > 1]
    if collisions:
        print(f"\nFAIL: these views draw an identical canvas: {sorted(collisions)}")
        print("A view tab must switch the DIAGRAM, not just a menu.")
        return 1
    print(f"\nok — {len(digests)} views, each drawing its own canvas")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "DOCUMENTATION" / "artifacts" / "_shots"))
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--open", nargs="*", default=[], dest="open_ids")
    args = ap.parse_args()
    return asyncio.run(run(pathlib.Path(args.out), args.dark, args.open_ids))


if __name__ == "__main__":
    sys.exit(main())
