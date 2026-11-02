"""CSV management module for NSE Market Data Downloader.

Handles atomic file writes, deterministic naming, UTF-8 encoding,
numerical precision preservation, and duplicate file prevention.
"""

import logging
import os
from pathlib import Path
import tempfile
from typing import Optional
import uuid
import pandas as pd


class CSVManager:
    """Manages CSV file generation, formatting, and atomic persistence."""

    FILENAME_PREFIXES = {
        "top-gainers-losers": "top_gainers_losers",
        "upper-band-hitters": "upper_band_hitters",
        "volume-gainers-spurts": "volume_gainers_spurts",
        "52-week-high": "52_week_high",
    }

    def __init__(self, output_dir: str = "output", logger: Optional[logging.Logger] = None) -> None:
        """Initialize CSVManager with target output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(__name__)

    def get_filename(self, dataset_id: str, trading_date: str) -> str:
        """Generate deterministic filename for a dataset and trading date."""
        prefix = self.FILENAME_PREFIXES.get(dataset_id, dataset_id.replace("-", "_"))
        return f"{prefix}_{trading_date}.csv"

    def get_target_path(self, dataset_id: str, trading_date: str) -> Path:
        """Get the full target file path for a dataset and date."""
        filename = self.get_filename(dataset_id, trading_date)
        return self.output_dir / filename

    def file_exists_for_date(self, dataset_id: str, trading_date: str) -> bool:
        """Check if a valid CSV file already exists for the given dataset and date."""
        target_path = self.get_target_path(dataset_id, trading_date)
        return target_path.exists() and target_path.stat().st_size > 0

    def save_csv(
        self,
        dataset_id: str,
        records: list[dict],
        trading_date: str,
        column_order: Optional[list[str]] = None,
    ) -> Path:
        """Atomically save records to a UTF-8 CSV file.

        Guarantees:
        - Refuses to overwrite with empty or invalid records.
        - Writes to a temporary file first in the same filesystem.
        - Atomically replaces target using os.replace.
        - Preserves numerical precision and UTF-8 characters.
        """
        if not records:
            raise ValueError(
                f"Refusing to save empty dataset for '{dataset_id}' on date '{trading_date}'."
            )

        if not trading_date or not isinstance(trading_date, str):
            raise ValueError(f"Invalid trading date '{trading_date}' provided for dataset '{dataset_id}'.")

        target_path = self.get_target_path(dataset_id, trading_date)

        # Convert records to pandas DataFrame
        df = pd.DataFrame(records)

        # Apply column ordering if specified
        if column_order:
            ordered_cols = [c for c in column_order if c in df.columns]
            extra_cols = [c for c in df.columns if c not in column_order]
            df = df[ordered_cols + extra_cols]

        # Use temporary file in the same directory to allow atomic os.replace across platforms
        temp_filename = f".{target_path.stem}_{uuid.uuid4().hex[:8]}.tmp"
        temp_path = self.output_dir / temp_filename

        try:
            # Write to temporary file with UTF-8 encoding preserving precision
            df.to_csv(
                temp_path,
                index=False,
                encoding="utf-8",
            )

            # Atomic swap
            os.replace(temp_path, target_path)

            self.logger.info(
                "[%s] Successfully saved %d records atomically to %s",
                dataset_id,
                len(records),
                target_path,
            )
            return target_path

        except Exception as exc:
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            self.logger.error(
                "[%s] Failed to write CSV file %s: %s",
                dataset_id,
                target_path,
                exc,
            )
            raise
