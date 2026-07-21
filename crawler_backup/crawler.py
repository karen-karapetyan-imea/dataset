"""
Crawler orchestration: load URLs, run workers with rate limiter, proxy pool,
block detection, adaptive backoff, exponential retry, JSONL output.
"""
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from adaptive_backoff import AdaptiveBackoff
from block_detector import BlockInfo
from config import CrawlerConfig, load_config
from fetcher import create_session, fetch
from proxy_pool import ProxyPool
from rate_limiter import RateLimiter
from result_structure import Result
from curl_cffi import Session


def hash_url(url: str) -> str:
    """SHA1 hash of URL for filename."""
    return hashlib.sha1(url.encode()).hexdigest()


_thread_local = threading.local()


def _get_session(impersonate: str) -> Session:
    """One Session per worker thread (connection pooling)."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = create_session(impersonate=impersonate)
    return _thread_local.session


def worker(
    url: str,
    config: CrawlerConfig,
    rate_limiter: RateLimiter,
    proxy_pool: ProxyPool,
    adaptive_backoff: AdaptiveBackoff,
    results_path: Path,
    results_lock: threading.Lock,
) -> Result:
    """Fetch one URL with rate limit, proxy, retries, block detection, and JSONL write."""
    adaptive_backoff.wait_if_cooldown()
    rate_limiter.wait()

    filename = hash_url(url) + ".html"
    path = config.output_path / filename
    session = _get_session(config.impersonate)
    proxy_dict = proxy_pool.get_next()

    status_code = 0
    err_msg = ""
    block_info: BlockInfo = BlockInfo(False, "")
    duration_ms = 0
    delay = config.retry_base_delay

    for attempt in range(config.max_retries + 1):
        status_code, err_msg, block_info, duration_ms = fetch(
            session, url, str(path), config, proxy_dict
        )
        adaptive_backoff.notify(block_info.is_block)

        if err_msg == "" and not block_info.is_block:
            break
        if attempt < config.max_retries:
            time.sleep(min(delay, config.retry_max_delay))
            delay *= 2

    timestamp = datetime.now(timezone.utc).isoformat()
    result = Result(
        url=url,
        filename=filename,
        status_code=status_code,
        error=err_msg,
        block_detected=block_info.is_block,
        block_reason=block_info.reason,
        duration_ms=duration_ms,
        timestamp=timestamp,
    )

    # Thread-safe JSONL append
    with results_lock:
        with open(results_path, "a") as f:
            f.write(
                json.dumps(
                    {
                        "url": result.url,
                        "filename": result.filename,
                        "status_code": result.status_code,
                        "error": result.error,
                        "block_detected": result.block_detected,
                        "block_reason": result.block_reason,
                        "duration_ms": result.duration_ms,
                        "timestamp": result.timestamp,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.flush()

    return result


def run_crawl(
    urls: list[str],
    config: CrawlerConfig | None = None,
) -> None:
    """Load config, create output dir and JSONL, run executor, write results."""
    if config is None:
        config = load_config()
    config.output_path.mkdir(parents=True, exist_ok=True)
    results_path = config.results_path
    results_lock = threading.Lock()

    rate_limiter = RateLimiter(
        config.requests_per_second,
        jitter_min=config.jitter_min,
        jitter_max=config.jitter_max,
    )
    proxy_pool = ProxyPool.from_file_or_env(config.proxy_file)
    adaptive_backoff = AdaptiveBackoff(
        window_size=config.block_window_size,
        block_rate_threshold=config.block_rate_threshold,
        cooldown_seconds=config.cooldown_seconds,
        cooldown_duration_seconds=config.cooldown_duration_seconds,
    )

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        future_to_url = {
            executor.submit(
                worker,
                url,
                config,
                rate_limiter,
                proxy_pool,
                adaptive_backoff,
                results_path,
                results_lock,
            ): url
            for url in urls
        }
        for future in as_completed(future_to_url):
            try:
                future.result()
            except Exception:
                url = future_to_url[future]
                with results_lock:
                    with open(results_path, "a") as f:
                        f.write(
                            json.dumps(
                                {
                                    "url": url,
                                    "filename": "",
                                    "status_code": 0,
                                    "error": "worker_exception",
                                    "block_detected": False,
                                    "block_reason": "",
                                    "duration_ms": 0,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        f.flush()
