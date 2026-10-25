#!/usr/bin/env python3
"""Render the two cuts of the Competition 01 banner at twice their size:
banner.html to docs/img/banner.png (the README's strip, 1200 by 420) and linkedin.html to
docs/img/banner_linkedin.png (LinkedIn's link-preview size, 1200 by 627).

Fonts and images are inlined as data URIs first, because a page opened from a file
cannot load them by path. Needs Pillow and a headless Chromium: pass its path as the
first argument, or set CHROME.
"""
import base64
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
IMG = HERE.parent / "img"


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def chip_png():
    # the finished layout with its black margin cut away, so the die meets the frame
    im = Image.open(IMG / "ref_5_finish.webp").convert("RGB")
    im = im.crop(im.point(lambda v: 255 if v > 24 else 0).getbbox())
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def wafer_svg():
    # the wafer mark alone, cut from the dark wordmark so the two never drift apart
    svg = (IMG / "chipbase_dark.svg").read_text()
    group = re.search(r'<g transform="translate\(4 4\)">.*?\n  </g>', svg, re.S).group(0)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72">{group}</svg>'


def main():
    chrome = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CHROME")
    if not chrome:
        sys.exit("usage: render.py <path to headless chromium>  (or set CHROME)")
    slots = {
        "INTER": data_uri(HERE / "fonts/inter-var-latin.woff2", "font/woff2"),
        "MONO": data_uri(HERE / "fonts/jetbrains-mono-var-latin.woff2", "font/woff2"),
        "CHIP": chip_png(),
        "WAFER": "data:image/svg+xml;base64," + base64.b64encode(wafer_svg().encode()).decode(),
    }
    for source, target, size in (("banner.html", "banner.png", "1200,420"),
                                 ("linkedin.html", "banner_linkedin.png", "1200,627")):
        page = (HERE / source).read_text()
        for key, value in slots.items():
            page = page.replace("{{" + key + "}}", value)
        out = IMG / target
        with tempfile.TemporaryDirectory() as tmp:
            filled = Path(tmp) / source
            filled.write_text(page)
            subprocess.run([chrome, "--headless", "--no-sandbox", "--hide-scrollbars",
                            f"--window-size={size}", "--force-device-scale-factor=2",
                            "--virtual-time-budget=3000", f"--screenshot={out}",
                            filled.as_uri()], check=True, capture_output=True)
        print(out)


if __name__ == "__main__":
    main()
