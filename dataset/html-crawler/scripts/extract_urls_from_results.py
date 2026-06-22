#!/usr/bin/env python3
"""Extract URL lists from a crawl results JSONL file."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build URL lists from results.jsonl")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("state"))
    parser.add_argument("--status", type=int, default=200, help="Status code to keep")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    by_domain: dict[str, set[str]] = {}
    status_counts: Counter[int] = Counter()

    with args.results.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            status = int(row.get("status_code") or 0)
            status_counts[status] += 1
            if status != args.status:
                continue
            url = str(row.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            domain = url.split("/")[2]
            by_domain.setdefault(domain, set()).add(url)

    for domain, urls in sorted(by_domain.items()):
        slug = domain.replace("www.", "").split(".")[0]
        out = args.output_dir / f"urls_{slug}.txt"
        out.write_text("\n".join(sorted(urls)) + "\n", encoding="utf-8")
        print(f"wrote {len(urls):>8} urls -> {out}")

    failed = args.output_dir / "urls_non_200.txt"
    failed_urls: set[str] = set()
    with args.results.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if int(row.get("status_code") or 0) == args.status:
                continue
            url = str(row.get("url") or "").strip()
            if url:
                failed_urls.add(url)
    failed.write_text("\n".join(sorted(failed_urls)) + "\n", encoding="utf-8")
    print(f"wrote {len(failed_urls):>8} urls -> {failed}")
    print("status counts:", dict(status_counts.most_common(10)))


if __name__ == "__main__":
    main()
