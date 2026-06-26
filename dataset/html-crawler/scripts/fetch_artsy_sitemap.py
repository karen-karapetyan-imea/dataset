#!/usr/bin/env python3
"""Fetch Artsy URLs from sitemap indexes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    if "--source" not in sys.argv:
        sys.argv[1:1] = ["--source", "artsy"]
    from scripts.fetch_marketplace_sitemap import main

    main()
