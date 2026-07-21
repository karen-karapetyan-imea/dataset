#!/usr/bin/env python3
"""Entry point: load config and URLs, run stealth crawler."""
import argparse
from pathlib import Path

from config import load_config
from crawler import run_crawl


def main() -> None:
    parser = argparse.ArgumentParser(description="Stealth HTML crawler (curl_cffi + proxy pool + block detection)")
    parser.add_argument("--urls", default=None, help="URL list file (one URL per line)")
    parser.add_argument("--output-dir", default=None, help="Output directory for HTML files")
    parser.add_argument("--results", default=None, help="JSONL results file path")
    parser.add_argument("--proxy-file", default=None, help="Proxy list file (host:port:user:pass per line)")
    parser.add_argument("--workers", type=int, default=None, help="Max worker threads (cap 64)")
    parser.add_argument("--rps", type=float, default=None, help="Target requests per second")
    args = parser.parse_args()

    config = load_config(
        urls_file=args.urls,
        output_dir=args.output_dir,
        results_file=args.results,
        proxy_file=args.proxy_file,
        max_workers=args.workers,
        requests_per_second=args.rps,
    )

    urls_path = Path(config.urls_file)
    if not urls_path.exists():
        print(f"Error: {config.urls_file} not found")
        return

    with open(urls_path) as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("Error: no URLs in file")
        return

    print(f"Crawling {len(urls)} URLs (workers={config.max_workers}, rps={config.requests_per_second})")
    if config.proxy_file:
        print(f"Proxy file: {config.proxy_file}")
    run_crawl(urls, config)
    print("Crawl finished")


if __name__ == "__main__":
    main()
