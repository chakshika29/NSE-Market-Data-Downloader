"""Integration tests for NSE Market Data Downloader pipeline."""

from datetime import datetime
from pathlib import Path
import sqlite3
from unittest.mock import MagicMock, patch
import pytest

from main import parse_args, run_pipeline
from src.market_calendar import IST_OFFSET, is_market_open


class TestPipelineIntegration:
    """End-to-end integration test suite using fixtures and mocks."""

    def test_all_four_csv_files_generated_with_fixtures(self, tmp_path):
        """Requirement: All four CSV files being generated using controlled fixtures."""
        args = parse_args(["--use-fixture", "--output-dir", str(tmp_path)])
        exit_code = run_pipeline(args)

        assert exit_code == 0

        # Check all 4 files exist in output directory
        expected_files = [
            "top_gainers_losers_2026-11-02.csv",
            "upper_band_hitters_2026-11-02.csv",
            "volume_gainers_spurts_2026-11-02.csv",
            "52_week_high_2026-11-02.csv",
        ]
        for fname in expected_files:
            file_path = tmp_path / fname
            assert file_path.exists(), f"Expected file {fname} not found."
            assert file_path.stat().st_size > 0, f"File {fname} is unexpectedly empty."

    @pytest.mark.parametrize(
        "dataset_arg, expected_prefix",
        [
            ("top-gainers-losers", "top_gainers_losers"),
            ("upper-band-hitters", "upper_band_hitters"),
            ("volume-gainers-spurts", "volume_gainers_spurts"),
            ("52-week-high", "52_week_high"),
        ],
    )
    def test_independent_dataset_cli_execution(self, tmp_path, dataset_arg, expected_prefix):
        """Requirement: Support downloading each individual dataset independently via CLI."""
        args = parse_args(["--dataset", dataset_arg, "--use-fixture", "--output-dir", str(tmp_path)])
        exit_code = run_pipeline(args)

        assert exit_code == 0
        csv_files = list(tmp_path.glob(f"{expected_prefix}_*.csv"))
        assert len(csv_files) == 1
        assert csv_files[0].stat().st_size > 0

    def test_failure_isolation_continues_processing_other_datasets(self, tmp_path):
        """Requirement: A failure in one dataset must not prevent the remaining datasets from processing."""
        # We patch load_fixture_for_dataset to raise an error only for 'upper-band-hitters'
        from main import load_fixture_for_dataset as original_loader

        def selective_failing_loader(dataset_id, fixtures_dir):
            if dataset_id == "upper-band-hitters":
                raise RuntimeError("Simulated transient failure for upper-band-hitters")
            return original_loader(dataset_id, fixtures_dir)

        with patch("main.load_fixture_for_dataset", side_effect=selective_failing_loader):
            args = parse_args(["--use-fixture", "--output-dir", str(tmp_path)])
            exit_code = run_pipeline(args)

            # Overall exit code is 1 because one dataset failed
            assert exit_code == 1

            # However, the OTHER three datasets must have succeeded and produced valid CSVs!
            assert (tmp_path / "top_gainers_losers_2026-11-02.csv").exists()
            assert (tmp_path / "volume_gainers_spurts_2026-11-02.csv").exists()
            assert (tmp_path / "52_week_high_2026-11-02.csv").exists()

            # The failed dataset must not have generated an invalid file
            assert not (tmp_path / "upper_band_hitters_2026-11-02.csv").exists()

    def test_database_persistence_bonus(self, tmp_path):
        """Verify SQLite database storage persists all records cleanly."""
        db_path = tmp_path / "test_market_data.db"
        args = parse_args([
            "--use-fixture",
            "--output-dir", str(tmp_path),
            "--save-db",
            "--db-path", str(db_path),
        ])
        exit_code = run_pipeline(args)

        assert exit_code == 0
        assert db_path.exists()

        # Connect and check tables and row counts
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM top_gainers_losers")
        assert cursor.fetchone()[0] == 5

        cursor.execute("SELECT COUNT(*) FROM upper_band_hitters")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT COUNT(*) FROM volume_gainers_spurts")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT COUNT(*) FROM fifty_two_week_high")
        assert cursor.fetchone()[0] == 2

        conn.close()

    def test_market_calendar_logic(self):
        """Verify market calendar accurately identifies open vs closed market sessions."""
        # Sunday 12:00 PM IST -> Closed (Weekend)
        sunday_dt = datetime(2026, 11, 1, 12, 0, tzinfo=IST_OFFSET)
        is_open, reason = is_market_open(sunday_dt)
        assert is_open is False
        assert "weekend" in reason.lower()

        # Monday 08:30 AM IST -> Closed (Pre-open)
        monday_early = datetime(2026, 11, 2, 8, 30, tzinfo=IST_OFFSET)
        is_open, reason = is_market_open(monday_early)
        assert is_open is False
        assert "not opened yet" in reason.lower()

        # Monday 11:30 AM IST -> Open
        monday_trading = datetime(2026, 11, 2, 11, 30, tzinfo=IST_OFFSET)
        is_open, reason = is_market_open(monday_trading)
        assert is_open is True
        assert "currently open" in reason.lower()

        # Monday 16:30 PM IST -> Closed
        monday_late = datetime(2026, 11, 2, 16, 30, tzinfo=IST_OFFSET)
        is_open, reason = is_market_open(monday_late)
        assert is_open is False
        assert "closed for the day" in reason.lower()
