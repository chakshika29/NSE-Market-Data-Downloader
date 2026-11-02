"""Data validation engine for NSE market datasets.

Validates payload structures, record integrity, expected columns,
numerical types, missing values, and handles duplicates safely.
"""

from dataclasses import dataclass, field
from datetime import datetime
import logging
import re
from typing import Any, Optional


@dataclass
class ValidationResult:
    """Encapsulates the outcome of validating a dataset."""
    is_valid: bool
    record_count: int
    cleaned_records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trading_date: Optional[str] = None

    def summary(self) -> str:
        """Return a human-readable validation summary."""
        status = "PASSED" if self.is_valid else "FAILED"
        return (
            f"Status: {status} | Records: {self.record_count} | "
            f"Errors: {len(self.errors)} | Warnings: {len(self.warnings)} | "
            f"Date: {self.trading_date or 'N/A'}"
        )


class DataValidator:
    """Reusable validator for NSE market datasets based on dataset-specific rules."""

    def __init__(self, config: dict, logger: Optional[logging.Logger] = None) -> None:
        """Initialize validator with dataset-specific configuration."""
        self.config = config
        self.dataset_id = config.get("id", "unknown")
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def parse_trading_date(raw_date_str: Optional[str]) -> Optional[str]:
        """Convert NSE timestamp string to YYYY-MM-DD.

        Examples handled:
            - '02-Nov-2026 16:00:00' -> '2026-11-02'
            - '02-Nov-2026' -> '2026-11-02'
            - '2026-11-02' -> '2026-11-02'
            - '02/11/2026' -> '2026-11-02'
        """
        if not raw_date_str or not isinstance(raw_date_str, str):
            return None

        raw = raw_date_str.strip()
        # Common NSE date patterns
        date_patterns = [
            ("%d-%b-%Y %H:%M:%S", 0),
            ("%d-%b-%Y", 0),
            ("%d-%B-%Y %H:%M:%S", 0),
            ("%d-%B-%Y", 0),
            ("%Y-%m-%d %H:%M:%S", 0),
            ("%Y-%m-%d", 0),
            ("%d/%m/%Y", 0),
        ]

        # Extract date portion if timestamp has trailing noise
        # E.g. '02-Nov-2026 16:00:00'
        match = re.search(r"(\d{1,2}-[A-Za-z]{3,9}-\d{4})", raw)
        if match:
            candidate = match.group(1)
            for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
                try:
                    return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass

        # Try standard pattern matches
        for pattern, _ in date_patterns:
            try:
                dt = datetime.strptime(raw, pattern)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try regex YYYY-MM-DD
        iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
        if iso_match:
            return iso_match.group(1)

        return None

    def extract_trading_date_from_payload(self, payload: Any) -> Optional[str]:
        """Traverse the payload using the configured timestamp path."""
        path = self.config.get("timestamp_path", [])
        curr = payload
        for step in path:
            if isinstance(curr, dict) and step in curr:
                curr = curr[step]
            else:
                curr = None
                break

        if isinstance(curr, str):
            parsed = self.parse_trading_date(curr)
            if parsed:
                return parsed

        # Search top-level timestamp key as fallback
        if isinstance(payload, dict):
            for key in ("timestamp", "tradeDate", "asOnDate", "date"):
                if key in payload and isinstance(payload[key], str):
                    parsed = self.parse_trading_date(payload[key])
                    if parsed:
                        return parsed

        return None

    def extract_records(self, payload: Any) -> tuple[list[dict], Optional[str]]:
        """Extract record list and metadata date from response payload."""
        if not isinstance(payload, (dict, list)):
            return [], None

        trading_date = self.extract_trading_date_from_payload(payload)

        # Dataset-specific extraction logic
        records: list[dict] = []

        if self.dataset_id == "top-gainers-losers":
            # Can be either a combined dictionary with 'gainers' and 'losers',
            # or a single variation dict with 'allSec' or 'NIFTY'
            if isinstance(payload, dict):
                # Check if it has pre-combined records
                if "records" in payload and isinstance(payload["records"], list):
                    records = payload["records"]
                else:
                    # Extract from configured section (e.g., 'allSec')
                    section = self.config.get("section", "allSec")
                    sec_dict = payload.get(section, {})
                    if isinstance(sec_dict, dict) and "data" in sec_dict:
                        records = sec_dict["data"]
                    elif isinstance(sec_dict, list):
                        records = sec_dict
                    else:
                        # Try fallbacks
                        for fb in self.config.get("fallback_sections", ["NIFTY"]):
                            if fb in payload and isinstance(payload[fb], dict) and "data" in payload[fb]:
                                records = payload[fb]["data"]
                                break

        elif "data_path" in self.config:
            curr = payload
            for step in self.config["data_path"]:
                if isinstance(curr, dict) and step in curr:
                    curr = curr[step]
                else:
                    curr = []
                    break
            if isinstance(curr, list):
                records = curr

        elif isinstance(payload, list):
            records = payload

        return records, trading_date

    def validate(self, payload: Any, trading_date_override: Optional[str] = None) -> ValidationResult:
        """Validate payload and its records comprehensively.

        Returns a ValidationResult object detailing validity, clean records,
        errors, and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Structure check
        if payload is None:
            return ValidationResult(
                is_valid=False,
                record_count=0,
                errors=["Payload is None / empty."],
            )

        if not isinstance(payload, (dict, list)):
            return ValidationResult(
                is_valid=False,
                record_count=0,
                errors=[f"Expected dict or list payload, got {type(payload).__name__}."],
            )

        # 2. Extract records and date
        raw_records, meta_date = self.extract_records(payload)
        effective_date = trading_date_override or meta_date

        if not raw_records:
            return ValidationResult(
                is_valid=False,
                record_count=0,
                errors=["Dataset contains 0 records (empty dataset)."],
                trading_date=effective_date,
            )

        # 3. Required fields validation
        required_fields = set(self.config.get("required_fields", []))
        dedup_keys = self.config.get("dedup_keys", ["symbol"])
        numeric_fields = set(self.config.get("numeric_fields", []))

        cleaned_records: list[dict] = []
        seen_keys: set[tuple] = set()
        duplicate_count = 0

        for idx, row in enumerate(raw_records):
            if not isinstance(row, dict):
                errors.append(f"Record at index {idx} is not a dictionary.")
                continue

            # Check required fields
            missing_reqs = [
                field for field in required_fields
                if field not in row or row[field] is None or str(row[field]).strip() == ""
            ]
            if missing_reqs:
                errors.append(f"Record {idx} missing required fields: {missing_reqs}.")
                continue

            # Check numeric validity
            for num_col in numeric_fields:
                if num_col in row and row[num_col] is not None:
                    val = row[num_col]
                    if isinstance(val, (int, float)):
                        continue
                    if isinstance(val, str):
                        # Clean common formatting like commas or percentage spaces
                        cleaned_str = val.replace(",", "").replace("%", "").strip()
                        # Handle suffixes like 'Cr', 'L', 'K' if present in trade values
                        if cleaned_str.endswith(("Cr", "cr", "L", "l", "K", "k")):
                            # Keep formatted string or accept as valid formatted metric
                            continue
                        try:
                            float(cleaned_str)
                        except ValueError:
                            warnings.append(
                                f"Record {idx} ('{row.get('symbol', 'N/A')}'): "
                                f"Field '{num_col}' has non-numeric value '{val}'."
                            )

            # Deduplication: build composite key
            dedup_tuple = tuple(str(row.get(k, "")).strip().upper() for k in dedup_keys)
            if dedup_tuple in seen_keys:
                duplicate_count += 1
                warnings.append(
                    f"Duplicate record ignored for key {dedup_keys}={dedup_tuple} at index {idx}."
                )
                continue

            seen_keys.add(dedup_tuple)
            cleaned_records.append(row)

        if duplicate_count > 0:
            self.logger.warning(
                "[%s] Detected and removed %d duplicate records based on keys %s.",
                self.dataset_id,
                duplicate_count,
                dedup_keys,
            )

        if not cleaned_records:
            errors.append("No valid records remaining after schema validation.")

        is_valid = len(errors) == 0 and len(cleaned_records) > 0

        result = ValidationResult(
            is_valid=is_valid,
            record_count=len(cleaned_records),
            cleaned_records=cleaned_records,
            errors=errors,
            warnings=warnings,
            trading_date=effective_date,
        )

        return result
