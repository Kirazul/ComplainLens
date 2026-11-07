"""Download Complaints-on-Twitter 2019 and its severity labels (small public files, ~1 MB).

Idempotent: existing files are kept. Used by the README instructions and by the API container,
which retrains the classical models at build time instead of shipping model weights in git.

Usage:
    uv run python ml/scripts/fetch_complaints2019.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

RAW = Path("data/raw/complaints2019")
FILES = {
    "complaints-data.csv": "https://raw.githubusercontent.com/danielpreotiuc/complaints-social-media/master/complaints-data.csv",
    "complaint_severity_data.csv": "https://archive.org/download/complaint_severity_data/complaint_severity_data.csv",
}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        path = RAW / name
        if path.exists() and path.stat().st_size > 0:
            print(f"kept {path}")
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "complaintlens-research"})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
        print(f"downloaded {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
