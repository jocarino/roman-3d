"""Fetch the two self-hosted fonts as woff2, latin subset only."""

import pathlib
import re
import subprocess
import sys

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

SPECS = [
    ("silkscreen-400", "https://fonts.googleapis.com/css2?family=Silkscreen&display=swap"),
    ("silkscreen-700", "https://fonts.googleapis.com/css2?family=Silkscreen:wght@700&display=swap"),
    ("plexmono-400", "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&display=swap"),
    (
        "plexmono-600",
        "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@600&display=swap",
    ),
]


def fetch(url: str) -> str:
    return subprocess.run(
        ["curl", "-sL", "--max-time", "30", "-A", UA, url], capture_output=True, text=True
    ).stdout


for name, url in SPECS:
    css = fetch(url)
    blocks = css.split("@font-face")
    latin = [b for b in blocks if "U+0000-00FF" in b] or blocks[1:]
    urls = re.findall(r"url\((https://[^)]+\.woff2)\)", latin[-1])
    if not urls:
        print(f"MISS {name}")
        continue
    target = OUT / f"{name}.woff2"
    subprocess.run(["curl", "-sL", "--max-time", "30", "-o", str(target), urls[0]], check=True)
    print(f"{name:16s} {target.stat().st_size:7,} bytes  <- {urls[0]}")
