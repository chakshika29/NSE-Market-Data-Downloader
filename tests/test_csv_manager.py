"""Unit tests for the CSVManager module."""

from pathlib import Path
import pytest
import pandas as pd

from src.csv_manager import CSVManager


class TestCSVManager:
    """Test suite for atomic CSV writing, deterministic naming, and precision."""

    def test_deterministic_filename_format(self, tmp_path):
        """Verify filenames adhere to the required naming conventions."""
        manager = CSVManager(output_dir=str(tmp_path))

        assert manager.get_filename("top-gainers-losers", "2026-11-02") == "top_gainers_losers_2026-11-02.csv"
        assert manager.get_filename("upper-band-hitters", "2026-11-02") == "upper_band_hitters_2026-11-02.csv"
        assert manager.get_filename("volume-gainers-spurts", "2026-11-02") == "volume_gainers_spurts_2026-11-02.csv"
        assert manager.get_filename("52-week-high", "2026-11-02") == "52_week_high_2026-11-02.csv"

    def test_save_csv_creates_valid_utf8_file_with_headers(self, tmp_path):
        """Verify CSV is created with valid UTF-8, proper headers, and content."""
        manager = CSVManager(output_dir=str(tmp_path))

        records = [
            {"symbol": "RELIANCE", "ltp": 1310.25, "category": "gainer"},
            {"symbol": "TCS", "ltp": 4195.5, "category": "gainer"},
        ]

        csv_path = manager.save_csv(
            dataset_id="top-gainers-losers",
            records=records,
            trading_date="2026-11-02",
        )

        assert csv_path.exists()
        assert csv_path.name == "top_gainers_losers_2026-11-02.csv"

        # Verify readability with pandas and encoding
        df = pd.read_csv(csv_path, encoding="utf-8")
        assert len(df) == 2
        assert list(df.columns) == ["symbol", "ltp", "category"]
        assert df.iloc[0]["symbol"] == "RELIANCE"

    def test_atomic_replacement_of_existing_file(self, tmp_path):
        """Verify existing same-date file is replaced atomically without temp leftovers."""
        manager = CSVManager(output_dir=str(tmp_path))

        initial_records = [{"symbol": "OLD", "ltp": 100.0, "category": "gainer"}]
        updated_records = [{"symbol": "NEW", "ltp": 200.0, "category": "gainer"}]

        # Write first version
        p1 = manager.save_csv("top-gainers-losers", initial_records, "2026-11-02")
        df1 = pd.read_csv(p1)
        assert df1.iloc[0]["symbol"] == "OLD"

        # Replace atomically
        p2 = manager.save_csv("top-gainers-losers", updated_records, "2026-11-02")
        assert p1 == p2
        df2 = pd.read_csv(p2)
        assert df2.iloc[0]["symbol"] == "NEW"

        # Ensure no dangling .tmp files exist in output dir
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_refuse_to_overwrite_with_empty_records(self, tmp_path):
        """Requirement: Never overwrite a valid CSV with an empty or invalid response."""
        manager = CSVManager(output_dir=str(tmp_path))

        valid_records = [{"symbol": "SUZLON", "ltp": 72.45, "priceBand": "5"}]
        target_path = manager.save_csv("upper-band-hitters", valid_records, "2026-11-02")
        assert target_path.exists()

        # Attempting to save empty records must raise ValueError and NOT touch existing file
        with pytest.raises(ValueError, match="Refusing to save empty dataset"):
            manager.save_csv("upper-band-hitters", [], "2026-11-02")

        # Verify existing file content is completely intact
        df = pd.read_csv(target_path)
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "SUZLON"

    def test_preserves_numerical_precision(self, tmp_path):
        """Requirement: Preserve numerical precision without truncation or loss."""
        manager = CSVManager(output_dir=str(tmp_path))

        high_precision_val = 4.9982704946385335
        large_int = 17199121
        records = [
            {"symbol": "TEST", "ratio": high_precision_val, "volume": large_int}
        ]

        csv_path = manager.save_csv("52-week-high", records, "2026-11-02")
        df = pd.read_csv(csv_path)

        assert abs(df.iloc[0]["ratio"] - high_precision_val) < 1e-12
        assert df.iloc[0]["volume"] == large_int

    def test_column_ordering_applied(self, tmp_path):
        """Verify custom column ordering is applied if specified."""
        manager = CSVManager(output_dir=str(tmp_path))

        records = [{"c": 3, "a": 1, "b": 2}]
        col_order = ["a", "b", "c"]

        csv_path = manager.save_csv("volume-gainers-spurts", records, "2026-11-02", column_order=col_order)
        df = pd.read_csv(csv_path)

        assert list(df.columns) == ["a", "b", "c"]
