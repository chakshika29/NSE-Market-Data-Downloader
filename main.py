"""Main entry point for NSE Market Data Downloader.

Provides a robust command-line interface to orchestrate the acquisition,
validation, and storage of four NSE market datasets.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Optional

from src.csv_manager import CSVManager
from src.db_manager import DatabaseManager
from src.downloader import AccessRestrictedError, NSEDownloader
from src.logger import setup_logger
from src.market_calendar import get_current_ist_time, is_market_open
from src.validator import DataValidator


ALL_DATASETS = [
    "top-gainers-losers",
    "upper-band-hitters",
    "volume-gainers-spurts",
    "52-week-high",
]


def load_config(config_path: Path) -> dict:
    """Load configuration JSON file safely."""
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fixture_for_dataset(dataset_id: str, fixtures_dir: Path) -> tuple[dict, list[dict]]:
    """Load synthetic test fixture data for a dataset."""
    fixture_files = {
        "top-gainers-losers": ("sample_gainers.json", "sample_loosers.json"),
        "upper-band-hitters": ("sample_upper_band.json",),
        "volume-gainers-spurts": ("sample_volume_gainers.json",),
        "52-week-high": ("sample_52_week_high.json",),
    }

    files = fixture_files.get(dataset_id, ())
    if dataset_id == "top-gainers-losers":
        gainers_path = fixtures_dir / files[0]
        losers_path = fixtures_dir / files[1]
        with open(gainers_path, "r", encoding="utf-8") as f:
            g_data = json.load(f)
        with open(losers_path, "r", encoding="utf-8") as f:
            l_data = json.load(f)

        records = []
        for r in g_data.get("allSec", {}).get("data", []):
            rec = dict(r)
            rec["category"] = "gainer"
            records.append(rec)
        for r in l_data.get("allSec", {}).get("data", []):
            rec = dict(r)
            rec["category"] = "loser"
            records.append(rec)

        return {"records": records, "timestamp": g_data.get("allSec", {}).get("timestamp")}, records

    file_path = fixtures_dir / files[0]
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data, []


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="NSE Market Data Downloader: Automates retrieval of 4 core NSE equity datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                      # Download all 4 datasets
  python main.py --dataset top-gainers-losers         # Download only Top Gainers / Losers
  python main.py --dataset upper-band-hitters         # Download only Upper Band Hitters
  python main.py --dataset volume-gainers-spurts      # Download only Volume Gainers / Spurts
  python main.py --dataset 52-week-high               # Download only 52-Week High Equity
  python main.py --output-dir ./market_data           # Custom output directory
  python main.py --save-db                            # Also save into SQLite database
  python main.py --check-market-open                  # Skip downloading if market is closed
  python main.py --use-fixture                        # Run using synthetic test fixtures (offline)
        """,
    )

    parser.add_argument(
        "--dataset",
        choices=ALL_DATASETS,
        help="Specific dataset to download. If omitted, all four datasets are downloaded.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to store generated CSV files (default: output).",
    )
    parser.add_argument(
        "--config",
        default="config/datasets.json",
        help="Path to datasets configuration JSON file (default: config/datasets.json).",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory to write execution logs (default: logs).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level (default: INFO).",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Optionally save records to SQLite database in addition to CSV.",
    )
    parser.add_argument(
        "--db-path",
        default="output/market_data.db",
        help="SQLite database path when --save-db is enabled (default: output/market_data.db).",
    )
    parser.add_argument(
        "--check-market-open",
        action="store_true",
        help="Check if NSE market is currently open and exit cleanly if closed.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass market-open check even if market is closed.",
    )
    parser.add_argument(
        "--use-fixture",
        action="store_true",
        help="Use bundled synthetic fixtures instead of live network requests (for offline/demo runs).",
    )

    return parser.parse_args(argv)


def run_pipeline(args: argparse.Namespace) -> int:
    """Execute the data downloader pipeline according to arguments."""
    logger = setup_logger(
        name="nse_downloader",
        log_dir=args.log_dir,
        level=getattr(logging, args.log_level),
    )

    logger.info("=" * 65)
    logger.info("NSE Market Data Downloader execution started.")
    logger.info("Output directory: %s", args.output_dir)

    # 1. Market calendar check if requested
    if args.check_market_open and not args.force:
        is_open, reason = is_market_open()
        if not is_open:
            logger.info("Market status check: %s", reason)
            logger.info("Skipping execution because market is closed. Use --force to run anyway.")
            return 0
        logger.info("Market status: %s", reason)

    # 2. Load configuration
    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except Exception as exc:
        logger.error("Failed to load configuration: %s", exc)
        return 2

    # 3. Determine datasets to process
    targets = [args.dataset] if args.dataset else ALL_DATASETS
    logger.info("Target datasets to process: %s", targets)

    # 4. Initialize services
    csv_manager = CSVManager(output_dir=args.output_dir, logger=logger)
    db_manager = DatabaseManager(db_path=args.db_path, logger=logger) if args.save_db else None
    downloader = NSEDownloader(config=config, logger=logger)

    results_summary = []
    has_failures = False
    fixtures_dir = Path("fixtures")

    # 5. Process each dataset independently
    for dataset_id in targets:
        logger.info("-" * 65)
        logger.info("[%s] Processing dataset...", dataset_id)
        ds_cfg = config.get("datasets", {}).get(dataset_id, {})
        validator = DataValidator(ds_cfg, logger=logger)

        try:
            # Step A: Data acquisition
            if args.use_fixture:
                logger.info("[%s] Using synthetic fixture data (--use-fixture).", dataset_id)
                payload, records = load_fixture_for_dataset(dataset_id, fixtures_dir)
                trading_date = validator.extract_trading_date_from_payload(payload) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            else:
                download_res = downloader.download_dataset(dataset_id)
                if not download_res.success:
                    results_summary.append({
                        "dataset": dataset_id,
                        "status": "DOWNLOAD_FAILED",
                        "records": 0,
                        "trading_date": "N/A",
                        "csv_file": "None",
                        "error": download_res.error_message,
                    })
                    has_failures = True
                    continue

                payload = download_res.payload
                trading_date = download_res.trading_date

                # If top-gainers-losers returned pre-combined records in DownloadResult
                if dataset_id == "top-gainers-losers" and download_res.records:
                    payload = {"records": download_res.records, "timestamp": trading_date}

            # Step B: Data validation
            val_result = validator.validate(payload, trading_date_override=trading_date)
            logger.info("[%s] Validation result: %s", dataset_id, val_result.summary())

            if not val_result.is_valid:
                error_msg = "; ".join(val_result.errors)
                logger.error("[%s] Validation failed: %s", dataset_id, error_msg)
                results_summary.append({
                    "dataset": dataset_id,
                    "status": "VALIDATION_FAILED",
                    "records": 0,
                    "trading_date": trading_date or "N/A",
                    "csv_file": "None",
                    "error": error_msg,
                })
                has_failures = True
                continue

            # Ensure trading date is determined
            effective_date = val_result.trading_date
            if not effective_date:
                effective_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                logger.warning(
                    "[%s] Source metadata did not contain a valid date. Falling back to today: %s",
                    dataset_id,
                    effective_date,
                )

            # Step C: CSV Generation (atomic write)
            col_order = ds_cfg.get("column_order")
            csv_path = csv_manager.save_csv(
                dataset_id=dataset_id,
                records=val_result.cleaned_records,
                trading_date=effective_date,
                column_order=col_order,
            )

            # Step D: Optional SQLite storage
            if db_manager:
                db_manager.save_records(
                    dataset_id=dataset_id,
                    records=val_result.cleaned_records,
                    trading_date=effective_date,
                )

            results_summary.append({
                "dataset": dataset_id,
                "status": "SUCCESS",
                "records": val_result.record_count,
                "trading_date": effective_date,
                "csv_file": csv_path.name,
                "error": None,
            })

        except AccessRestrictedError as exc:
            logger.error("[%s] Access restricted: %s", dataset_id, exc)
            results_summary.append({
                "dataset": dataset_id,
                "status": "ACCESS_RESTRICTED",
                "records": 0,
                "trading_date": "N/A",
                "csv_file": "None",
                "error": str(exc),
            })
            has_failures = True

        except Exception as exc:
            logger.exception("[%s] Unexpected processing failure: %s", dataset_id, exc)
            results_summary.append({
                "dataset": dataset_id,
                "status": "ERROR",
                "records": 0,
                "trading_date": "N/A",
                "csv_file": "None",
                "error": str(exc),
            })
            has_failures = True

    # 6. Print and log final execution summary table
    logger.info("=" * 65)
    logger.info("FINAL EXECUTION SUMMARY")
    logger.info("=" * 65)
    header = f"{'Dataset':<24} | {'Status':<16} | {'Records':<8} | {'Date':<10} | {'CSV Output'}"
    logger.info(header)
    logger.info("-" * 80)
    for row in results_summary:
        line = (
            f"{row['dataset']:<24} | "
            f"{row['status']:<16} | "
            f"{row['records']:<8} | "
            f"{row['trading_date']:<10} | "
            f"{row['csv_file']}"
        )
        logger.info(line)
        if row["error"]:
            logger.warning("   -> Error detail [%s]: %s", row["dataset"], row["error"])

    logger.info("=" * 65)

    return 1 if has_failures else 0


def main() -> None:
    """CLI script entry point."""
    args = parse_args()
    exit_code = run_pipeline(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
