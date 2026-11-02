"""Optional live integration tests connecting directly to NSE India servers.

These tests are marked with `@pytest.mark.live` and are skipped by default.
Run explicitly with:
    pytest -m live --run-live
"""

import pytest
from src.downloader import AccessRestrictedError, NSEDownloader
from src.validator import DataValidator


@pytest.mark.live
class TestLiveNSEConnectivity:
    """Optional tests verifying live responses against live NSE endpoints."""

    def test_live_top_gainers_losers(self, test_config):
        """Attempt live download of top-gainers-losers from NSE."""
        downloader = NSEDownloader(config=test_config)
        try:
            result = downloader.download_dataset("top-gainers-losers")
            assert result.status_code == 200
            assert result.success is True
            assert len(result.records) > 0
        except AccessRestrictedError as exc:
            pytest.skip(f"Live access restricted by NSE anti-bot policy: {exc}")

    def test_live_upper_band_hitters(self, test_config):
        """Attempt live download of upper-band-hitters from NSE."""
        downloader = NSEDownloader(config=test_config)
        try:
            result = downloader.download_dataset("upper-band-hitters")
            assert result.status_code == 200
            assert result.success is True
            assert len(result.records) > 0
        except AccessRestrictedError as exc:
            pytest.skip(f"Live access restricted by NSE anti-bot policy: {exc}")

    def test_live_volume_gainers(self, test_config):
        """Attempt live download of volume-gainers from NSE."""
        downloader = NSEDownloader(config=test_config)
        try:
            result = downloader.download_dataset("volume-gainers-spurts")
            assert result.status_code == 200
            assert result.success is True
            assert len(result.records) > 0
        except AccessRestrictedError as exc:
            pytest.skip(f"Live access restricted by NSE anti-bot policy: {exc}")

    def test_live_52_week_high(self, test_config):
        """Attempt live download of 52-week-high from NSE."""
        downloader = NSEDownloader(config=test_config)
        try:
            result = downloader.download_dataset("52-week-high")
            assert result.status_code == 200
            assert result.success is True
            assert len(result.records) > 0
        except AccessRestrictedError as exc:
            pytest.skip(f"Live access restricted by NSE anti-bot policy: {exc}")
