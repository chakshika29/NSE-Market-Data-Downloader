"""Unit tests for the DataValidator module."""

import pytest
from src.validator import DataValidator, ValidationResult


class TestDataValidator:
    """Test suite for DataValidator schema, duplicate handling, and dates."""

    def test_valid_payload_passes(self, test_config, sample_52_week_high_payload):
        """Verify valid payload passes validation with correct record count and date."""
        cfg = test_config["datasets"]["52-week-high"]
        validator = DataValidator(cfg)

        result = validator.validate(sample_52_week_high_payload)

        assert result.is_valid is True
        assert result.record_count == 2
        assert len(result.errors) == 0
        assert result.trading_date == "2026-11-02"

    def test_none_and_invalid_type_payload_rejected(self, test_config):
        """Verify None or invalid type payloads fail validation."""
        cfg = test_config["datasets"]["upper-band-hitters"]
        validator = DataValidator(cfg)

        res_none = validator.validate(None)
        assert res_none.is_valid is False
        assert "Payload is None" in res_none.errors[0]

        res_str = validator.validate("just a string")
        assert res_str.is_valid is False
        assert "Expected dict or list" in res_str.errors[0]

    def test_empty_records_rejected(self, test_config):
        """Verify empty records fail validation."""
        cfg = test_config["datasets"]["volume-gainers-spurts"]
        validator = DataValidator(cfg)

        empty_payload = {"timestamp": "02-Nov-2026 16:00:00", "data": []}
        result = validator.validate(empty_payload)

        assert result.is_valid is False
        assert "0 records" in result.errors[0]

    def test_missing_required_fields_rejected(self, test_config):
        """Verify records missing required fields fail validation."""
        cfg = test_config["datasets"]["top-gainers-losers"]
        validator = DataValidator(cfg)

        # Missing 'ltp' and 'category'
        bad_payload = {
            "records": [
                {"symbol": "RELIANCE", "series": "EQ"},
            ],
            "timestamp": "02-Nov-2026 16:00:00",
        }
        result = validator.validate(bad_payload)

        assert result.is_valid is False
        assert any("missing required fields" in err for err in result.errors)

    def test_preserves_legitimate_distinct_records_same_symbol(self, test_config):
        """Requirement: Do not remove legitimate distinct market records merely because their symbols match.

        For Top Gainers / Losers: preserve both gainer and loser records even if symbol matches.
        """
        cfg = test_config["datasets"]["top-gainers-losers"]
        validator = DataValidator(cfg)

        # A symbol appearing as both gainer and loser (e.g. across indices or sessions)
        payload = {
            "records": [
                {"symbol": "INFY", "series": "EQ", "category": "gainer", "ltp": 1850.0},
                {"symbol": "INFY", "series": "EQ", "category": "loser", "ltp": 1820.0},
            ],
            "timestamp": "02-Nov-2026 16:00:00",
        }

        result = validator.validate(payload)

        assert result.is_valid is True
        # Both distinct records must be preserved!
        assert result.record_count == 2
        categories = {r["category"] for r in result.cleaned_records}
        assert categories == {"gainer", "loser"}

    def test_preserves_distinct_series_same_symbol(self, test_config):
        """Verify same symbol with different series (e.g. EQ vs BE) is preserved."""
        cfg = test_config["datasets"]["upper-band-hitters"]
        validator = DataValidator(cfg)

        payload = {
            "upper": {
                "AllSec": {
                    "timestamp": "02-Nov-2026 16:00:00",
                    "data": [
                        {"symbol": "TATAMOTORS", "series": "EQ", "ltp": 900.0, "priceBand": "20"},
                        {"symbol": "TATAMOTORS", "series": "DVR", "ltp": 600.0, "priceBand": "20"},
                    ],
                }
            }
        }

        result = validator.validate(payload)
        assert result.is_valid is True
        assert result.record_count == 2

    def test_removes_true_duplicate_records(self, test_config):
        """Verify identical duplicate records are detected and deduplicated."""
        cfg = test_config["datasets"]["volume-gainers-spurts"]
        validator = DataValidator(cfg)

        # CLCIND duplicated twice
        payload = {
            "timestamp": "02-Nov-2026 16:00:00",
            "data": [
                {"symbol": "CLCIND", "volume": "50 K", "week1AvgVolume": 100, "ltp": 42.0},
                {"symbol": "CLCIND", "volume": "50 K", "week1AvgVolume": 100, "ltp": 42.0},
            ],
        }

        result = validator.validate(payload)
        assert result.is_valid is True
        # Only 1 unique record should remain
        assert result.record_count == 1
        assert any("Duplicate record ignored" in w for w in result.warnings)

    def test_date_parsing_variations(self):
        """Verify various date format strings are parsed to YYYY-MM-DD."""
        assert DataValidator.parse_trading_date("02-Nov-2026 16:00:00") == "2026-11-02"
        assert DataValidator.parse_trading_date("02-Nov-2026") == "2026-11-02"
        assert DataValidator.parse_trading_date("02-November-2026") == "2026-11-02"
        assert DataValidator.parse_trading_date("2026-11-02") == "2026-11-02"
        assert DataValidator.parse_trading_date("31-Oct-2024") == "2024-10-31"
        assert DataValidator.parse_trading_date(None) is None
        assert DataValidator.parse_trading_date("invalid-date") is None
