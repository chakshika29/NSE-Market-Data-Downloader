"""NSE Market Data Downloader module.

Handles robust data acquisition from NSE endpoints with session management,
exponential backoff on transient errors, fast failure on access restrictions,
and isolation between datasets.
"""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time
from typing import Any, Optional
import requests
from requests.adapters import HTTPAdapter


class NSEDownloaderError(Exception):
    """Base exception for all NSE downloader operations."""


class AccessRestrictedError(NSEDownloaderError):
    """Raised when NSE denies access (HTTP 401/403) or presents bot challenge."""


class NetworkTimeoutError(NSEDownloaderError):
    """Raised when requests timeout repeatedly."""


class InvalidResponseError(NSEDownloaderError):
    """Raised when endpoint returns unexpected non-JSON or HTML data."""


class DatasetEmptyError(NSEDownloaderError):
    """Raised when an endpoint returns no records."""


@dataclass
class DownloadResult:
    """Encapsulates the raw payload and metadata downloaded for a dataset."""
    dataset_id: str
    success: bool
    payload: Optional[Any] = None
    records: Optional[list[dict]] = None
    trading_date: Optional[str] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    duration_seconds: float = 0.0


class NSEDownloader:
    """Client for downloading market datasets from permitted NSE sources."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    def __init__(
        self,
        config: dict,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize downloader with configuration and optional injected session."""
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        net_cfg = config.get("network", {})
        self.timeout = net_cfg.get("timeout_seconds", 12)
        self.max_retries = net_cfg.get("max_retries", 3)
        self.backoff_factor = net_cfg.get("backoff_factor", 1.5)
        self.status_forcelist = set(net_cfg.get("status_forcelist", [500, 502, 503, 504]))

        # Initialize or reuse HTTP session
        self.session = session or requests.Session()
        custom_ua = net_cfg.get("user_agent")
        headers = dict(self.DEFAULT_HEADERS)
        if custom_ua:
            headers["User-Agent"] = custom_ua
        self.session.headers.update(headers)

    def fetch_url(self, url: str) -> requests.Response:
        """Fetch URL with exponential backoff for transient errors only.

        Fails immediately without retries on HTTP 401/403 access-denied responses.
        """
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.debug("Requesting URL: %s (attempt %d/%d)", url, attempt, self.max_retries)
                response = self.session.get(url, timeout=self.timeout)

                # Fast fail on access restrictions - DO NOT RETRY
                if response.status_code in (401, 403):
                    msg = (
                        f"Access restricted by NSE server (HTTP {response.status_code}) for URL: {url}. "
                        "NSE anti-bot or access policies restrict automated access without authorization."
                    )
                    self.logger.error(msg)
                    raise AccessRestrictedError(msg)

                # Transient server errors: retry with backoff
                if response.status_code in self.status_forcelist:
                    self.logger.warning(
                        "Received transient HTTP %d for %s (attempt %d/%d).",
                        response.status_code,
                        url,
                        attempt,
                        self.max_retries,
                    )
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                        time.sleep(sleep_time)
                        continue
                    response.raise_for_status()

                # Raise for any other 4xx/5xx errors
                response.raise_for_status()
                return response

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exception = exc
                self.logger.warning(
                    "Network error on attempt %d/%d for %s: %s",
                    attempt,
                    self.max_retries,
                    url,
                    exc,
                )
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                else:
                    raise NetworkTimeoutError(f"Network failure after {self.max_retries} attempts: {exc}") from exc

            except requests.HTTPError as exc:
                raise NSEDownloaderError(f"HTTP error for {url}: {exc}") from exc

        raise NSEDownloaderError(f"Failed to fetch {url} after {self.max_retries} retries: {last_exception}")

    def fetch_json(self, url: str) -> tuple[Any, int]:
        """Fetch and parse JSON from the given URL."""
        response = self.fetch_url(url)
        content_type = response.headers.get("Content-Type", "")

        # Check for HTML redirect/challenge disguised as 200
        text_snippet = response.text[:200].strip().lower()
        if text_snippet.startswith("<!doctype html") or "<html" in text_snippet:
            raise InvalidResponseError(
                f"Expected JSON from {url}, but received HTML content (likely bot verification page)."
            )

        try:
            data = response.json()
            return data, response.status_code
        except json.JSONDecodeError as exc:
            raise InvalidResponseError(f"Failed to decode JSON from {url}: {exc}") from exc

    def download_dataset(self, dataset_id: str) -> DownloadResult:
        """Download a dataset independently using its specific configuration."""
        dataset_cfg = self.config.get("datasets", {}).get(dataset_id)
        if not dataset_cfg:
            return DownloadResult(
                dataset_id=dataset_id,
                success=False,
                error_message=f"Configuration for dataset '{dataset_id}' not found.",
            )

        start_time = time.time()
        self.logger.info("[%s] Starting download...", dataset_id)

        try:
            if dataset_id == "top-gainers-losers":
                result = self._download_top_gainers_losers(dataset_cfg)
            else:
                result = self._download_single_endpoint_dataset(dataset_id, dataset_cfg)

            duration = round(time.time() - start_time, 2)
            result.duration_seconds = duration

            if result.success:
                rec_count = len(result.records) if result.records else 0
                self.logger.info(
                    "[%s] Successfully downloaded %d records in %.2fs (Trading Date: %s)",
                    dataset_id,
                    rec_count,
                    duration,
                    result.trading_date or "Unknown",
                )
            else:
                self.logger.error(
                    "[%s] Download failed in %.2fs: %s",
                    dataset_id,
                    duration,
                    result.error_message,
                )

            return result

        except Exception as exc:
            duration = round(time.time() - start_time, 2)
            self.logger.error("[%s] Unexpected exception: %s", dataset_id, exc)
            return DownloadResult(
                dataset_id=dataset_id,
                success=False,
                error_message=str(exc),
                duration_seconds=duration,
            )

    def _download_top_gainers_losers(self, dataset_cfg: dict) -> DownloadResult:
        """Retrieve both gainers and losers, tag records, and combine them."""
        endpoints = dataset_cfg.get("endpoints", {})
        gainers_url = endpoints.get("gainers")
        losers_url = endpoints.get("loosers")

        if not gainers_url or not losers_url:
            return DownloadResult(
                dataset_id="top-gainers-losers",
                success=False,
                error_message="Endpoints for gainers or losers missing in configuration.",
            )

        combined_records: list[dict] = []
        trading_date: Optional[str] = None
        status_code = 200

        # 1. Fetch Gainers
        try:
            gainers_payload, status_code = self.fetch_json(gainers_url)
            g_records, g_date = self._extract_variation_records(gainers_payload, dataset_cfg, category="gainer")
            combined_records.extend(g_records)
            if g_date:
                trading_date = g_date
            self.logger.info("[top-gainers-losers] Fetched %d gainer records.", len(g_records))
        except Exception as exc:
            self.logger.warning("[top-gainers-losers] Failed to fetch gainers: %s", exc)

        # 2. Fetch Losers
        try:
            losers_payload, status_code = self.fetch_json(losers_url)
            l_records, l_date = self._extract_variation_records(losers_payload, dataset_cfg, category="loser")
            combined_records.extend(l_records)
            if not trading_date and l_date:
                trading_date = l_date
            self.logger.info("[top-gainers-losers] Fetched %d loser records.", len(l_records))
        except Exception as exc:
            self.logger.warning("[top-gainers-losers] Failed to fetch losers: %s", exc)

        if not combined_records:
            return DownloadResult(
                dataset_id="top-gainers-losers",
                success=False,
                status_code=status_code,
                error_message="No records retrieved for both gainers and losers.",
            )

        return DownloadResult(
            dataset_id="top-gainers-losers",
            success=True,
            records=combined_records,
            trading_date=trading_date,
            status_code=status_code,
        )

    def _extract_variation_records(
        self, payload: Any, dataset_cfg: dict, category: str
    ) -> tuple[list[dict], Optional[str]]:
        """Extract records from live-analysis-variations payload and attach category."""
        from src.validator import DataValidator

        records: list[dict] = []
        trading_date = None

        if isinstance(payload, dict):
            section = dataset_cfg.get("section", "allSec")
            sec_dict = payload.get(section)
            if not isinstance(sec_dict, dict):
                # Try fallback sections
                for fb in dataset_cfg.get("fallback_sections", ["NIFTY", "FOSec"]):
                    if fb in payload and isinstance(payload[fb], dict):
                        sec_dict = payload[fb]
                        break

            if isinstance(sec_dict, dict):
                raw_data = sec_dict.get("data", [])
                raw_date = sec_dict.get("timestamp")
                if raw_date:
                    trading_date = DataValidator.parse_trading_date(raw_date)

                for item in raw_data:
                    if isinstance(item, dict):
                        record = dict(item)
                        record["category"] = category
                        records.append(record)

        return records, trading_date

    def _download_single_endpoint_dataset(self, dataset_id: str, dataset_cfg: dict) -> DownloadResult:
        """Download dataset that uses a single primary endpoint."""
        from src.validator import DataValidator

        primary_url = dataset_cfg.get("endpoints", {}).get("primary")
        if not primary_url:
            return DownloadResult(
                dataset_id=dataset_id,
                success=False,
                error_message=f"Primary endpoint missing for {dataset_id}.",
            )

        payload, status_code = self.fetch_json(primary_url)

        # Extract data list using data_path
        data_path = dataset_cfg.get("data_path", [])
        curr = payload
        for step in data_path:
            if isinstance(curr, dict) and step in curr:
                curr = curr[step]
            else:
                curr = []
                break

        records = curr if isinstance(curr, list) else []

        # Extract timestamp
        validator = DataValidator(dataset_cfg, self.logger)
        trading_date = validator.extract_trading_date_from_payload(payload)

        return DownloadResult(
            dataset_id=dataset_id,
            success=True,
            payload=payload,
            records=records,
            trading_date=trading_date,
            status_code=status_code,
        )
