"""Unit tests for the NSEDownloader module."""

import json
from unittest.mock import MagicMock, patch
import pytest
import requests

from src.downloader import (
    AccessRestrictedError,
    InvalidResponseError,
    NetworkTimeoutError,
    NSEDownloader,
    NSEDownloaderError,
)


def _mock_response(status_code: int = 200, json_data: dict = None, text: str = "", content_type: str = "application/json"):
    """Helper to build mock requests.Response objects."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = {"Content-Type": content_type}
    if json_data is not None:
        resp.json.return_value = json_data
        resp.text = json.dumps(json_data)
    else:
        resp.text = text
        resp.json.side_effect = json.JSONDecodeError("Expecting value", text, 0)

    if 400 <= status_code < 600:
        http_err = requests.HTTPError(f"HTTP Error {status_code}", response=resp)
        resp.raise_for_status.side_effect = http_err
    else:
        resp.raise_for_status.return_value = None

    return resp


class TestNSEDownloader:
    """Test suite for NSEDownloader request handling, retries, and errors."""

    def test_successful_download_upper_band(self, test_config, sample_upper_band_payload):
        """Verify successful download and extraction of upper-band-hitters."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}
        mock_session.get.return_value = _mock_response(200, json_data=sample_upper_band_payload)

        downloader = NSEDownloader(config=test_config, session=mock_session)
        result = downloader.download_dataset("upper-band-hitters")

        assert result.success is True
        assert result.status_code == 200
        assert len(result.records) == 2
        assert result.trading_date == "2026-11-02"
        assert result.records[0]["symbol"] == "ITI"
        mock_session.get.assert_called_once()

    def test_successful_download_top_gainers_losers(
        self, test_config, sample_gainers_payload, sample_loosers_payload
    ):
        """Verify gainers and losers are fetched, tagged with category, and combined."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}

        def mock_get(url, **kwargs):
            if "index=gainers" in url:
                return _mock_response(200, json_data=sample_gainers_payload)
            elif "index=loosers" in url:
                return _mock_response(200, json_data=sample_loosers_payload)
            return _mock_response(404)

        mock_session.get.side_effect = mock_get

        downloader = NSEDownloader(config=test_config, session=mock_session)
        result = downloader.download_dataset("top-gainers-losers")

        assert result.success is True
        assert len(result.records) == 5  # 3 gainers + 2 losers
        categories = [r["category"] for r in result.records]
        assert categories.count("gainer") == 3
        assert categories.count("loser") == 2
        assert result.trading_date == "2026-11-02"

    def test_access_restricted_403_fails_fast_without_retries(self, test_config):
        """Verify HTTP 403 Forbidden raises AccessRestrictedError immediately without retrying."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}
        mock_session.get.return_value = _mock_response(403, text="Access Denied")

        downloader = NSEDownloader(config=test_config, session=mock_session)
        # Configure max_retries = 3 to prove it does NOT retry 3 times
        downloader.max_retries = 3

        result = downloader.download_dataset("upper-band-hitters")
        assert result.success is False
        assert "Access restricted" in result.error_message
        # Crucial check: called exactly once, no repeated retries on 403
        assert mock_session.get.call_count == 1

    def test_access_restricted_401_fails_fast(self, test_config):
        """Verify HTTP 401 Unauthorized raises AccessRestrictedError immediately."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}
        mock_session.get.return_value = _mock_response(401, text="Unauthorized")

        downloader = NSEDownloader(config=test_config, session=mock_session)
        result = downloader.download_dataset("52-week-high")

        assert result.success is False
        assert "Access restricted" in result.error_message
        assert mock_session.get.call_count == 1

    @patch("time.sleep", return_value=None)
    def test_transient_500_retries_and_succeeds(self, mock_sleep, test_config, sample_volume_gainers_payload):
        """Verify transient 500 error is retried and succeeds on subsequent attempt."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}

        # First call fails with 500, second call succeeds with 200
        mock_session.get.side_effect = [
            _mock_response(500, text="Internal Server Error"),
            _mock_response(200, json_data=sample_volume_gainers_payload),
        ]

        downloader = NSEDownloader(config=test_config, session=mock_session)
        result = downloader.download_dataset("volume-gainers-spurts")

        assert result.success is True
        assert len(result.records) == 2
        assert mock_session.get.call_count == 2
        mock_sleep.assert_called_once()

    @patch("time.sleep", return_value=None)
    def test_network_timeout_exhausts_retries(self, mock_sleep, test_config):
        """Verify requests.Timeout is retried up to max_retries and reports failure."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}
        mock_session.get.side_effect = requests.Timeout("Connection timed out")

        downloader = NSEDownloader(config=test_config, session=mock_session)
        downloader.max_retries = 3

        result = downloader.download_dataset("52-week-high")
        assert result.success is False
        assert "Network failure" in result.error_message or "timed out" in result.error_message
        assert mock_session.get.call_count == 3

    def test_unexpected_html_response_rejected(self, test_config):
        """Verify HTML response (such as an anti-bot challenge) is rejected with InvalidResponseError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}
        html_content = "<!DOCTYPE html><html><body>Captcha Challenge</body></html>"
        mock_session.get.return_value = _mock_response(200, text=html_content, content_type="text/html")

        downloader = NSEDownloader(config=test_config, session=mock_session)
        result = downloader.download_dataset("volume-gainers-spurts")

        assert result.success is False
        assert "Expected JSON" in result.error_message

    def test_invalid_json_response_rejected(self, test_config):
        """Verify malformed JSON raises InvalidResponseError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.headers = {}
        mock_session.get.return_value = _mock_response(200, text="{broken: json,")

        downloader = NSEDownloader(config=test_config, session=mock_session)
        result = downloader.download_dataset("52-week-high")

        assert result.success is False
        assert "Failed to decode JSON" in result.error_message

    def test_missing_dataset_configuration(self, test_config):
        """Verify attempting to download an unconfigured dataset reports error cleanly."""
        downloader = NSEDownloader(config=test_config)
        result = downloader.download_dataset("non-existent-dataset")

        assert result.success is False
        assert "Configuration for dataset 'non-existent-dataset' not found" in result.error_message
