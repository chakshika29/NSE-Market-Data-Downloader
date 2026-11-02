"""SQLite database manager for optional historical storage of NSE datasets.

Provides table schema creation, historical upsert capability, and querying.
Standard library sqlite3 only, zero extra dependencies.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any, Optional


class DatabaseManager:
    """Manages SQLite storage for historical NSE market data."""

    TABLE_SCHEMAS = {
        "top-gainers-losers": """
            CREATE TABLE IF NOT EXISTS top_gainers_losers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                series TEXT,
                category TEXT NOT NULL,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                ltp REAL,
                prev_price REAL,
                net_price REAL,
                per_change REAL,
                trade_quantity TEXT,
                turnover TEXT,
                recorded_at TEXT NOT NULL,
                UNIQUE(trading_date, symbol, series, category)
            )
        """,
        "upper-band-hitters": """
            CREATE TABLE IF NOT EXISTS upper_band_hitters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                series TEXT,
                price_band TEXT,
                ltp REAL,
                change REAL,
                p_change REAL,
                high_price REAL,
                low_price REAL,
                total_traded_vol TEXT,
                turnover TEXT,
                year_high REAL,
                year_low REAL,
                recorded_at TEXT NOT NULL,
                UNIQUE(trading_date, symbol, series)
            )
        """,
        "volume-gainers-spurts": """
            CREATE TABLE IF NOT EXISTS volume_gainers_spurts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                company_name TEXT,
                ltp REAL,
                p_change REAL,
                volume TEXT,
                week1_avg_volume REAL,
                week1_vol_change REAL,
                week2_avg_volume REAL,
                week2_vol_change REAL,
                turnover TEXT,
                recorded_at TEXT NOT NULL,
                UNIQUE(trading_date, symbol)
            )
        """,
        "52-week-high": """
            CREATE TABLE IF NOT EXISTS fifty_two_week_high (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                company_name TEXT,
                series TEXT,
                ltp REAL,
                change REAL,
                p_change REAL,
                new_52_week_high REAL,
                prev_52_week_high REAL,
                prev_high_date TEXT,
                prev_close TEXT,
                recorded_at TEXT NOT NULL,
                UNIQUE(trading_date, symbol, series)
            )
        """,
    }

    TABLE_NAMES = {
        "top-gainers-losers": "top_gainers_losers",
        "upper-band-hitters": "upper_band_hitters",
        "volume-gainers-spurts": "volume_gainers_spurts",
        "52-week-high": "fifty_two_week_high",
    }

    def __init__(self, db_path: str = "output/market_data.db", logger: Optional[logging.Logger] = None) -> None:
        """Initialize database connection and ensure tables exist."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(__name__)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables for all supported datasets."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for schema in self.TABLE_SCHEMAS.values():
                cursor.execute(schema)
            conn.commit()
        self.logger.debug("Database initialized at %s", self.db_path)

    def save_records(self, dataset_id: str, records: list[dict], trading_date: str) -> int:
        """Insert or replace records for the given dataset and trading date."""
        table = self.TABLE_NAMES.get(dataset_id)
        if not table or not records:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        inserted_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            if dataset_id == "top-gainers-losers":
                query = f"""
                    INSERT OR REPLACE INTO {table}
                    (trading_date, symbol, series, category, open_price, high_price, low_price,
                     ltp, prev_price, net_price, per_change, trade_quantity, turnover, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                for r in records:
                    cursor.execute(
                        query,
                        (
                            trading_date,
                            r.get("symbol"),
                            r.get("series"),
                            r.get("category", "gainer"),
                            self._safe_float(r.get("open_price")),
                            self._safe_float(r.get("high_price")),
                            self._safe_float(r.get("low_price")),
                            self._safe_float(r.get("ltp")),
                            self._safe_float(r.get("prev_price")),
                            self._safe_float(r.get("net_price")),
                            self._safe_float(r.get("perChange")),
                            str(r.get("trade_quantity", "")),
                            str(r.get("turnover", "")),
                            now_iso,
                        ),
                    )
                    inserted_count += 1

            elif dataset_id == "upper-band-hitters":
                query = f"""
                    INSERT OR REPLACE INTO {table}
                    (trading_date, symbol, series, price_band, ltp, change, p_change,
                     high_price, low_price, total_traded_vol, turnover, year_high, year_low, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                for r in records:
                    cursor.execute(
                        query,
                        (
                            trading_date,
                            r.get("symbol"),
                            r.get("series"),
                            str(r.get("priceBand", "")),
                            self._safe_float(r.get("ltp")),
                            self._safe_float(r.get("change")),
                            self._safe_float(r.get("pChange")),
                            self._safe_float(r.get("highPrice")),
                            self._safe_float(r.get("lowPrice")),
                            str(r.get("totalTradedVol", "")),
                            str(r.get("turnover", "")),
                            self._safe_float(r.get("yearHigh")),
                            self._safe_float(r.get("yearLow")),
                            now_iso,
                        ),
                    )
                    inserted_count += 1

            elif dataset_id == "volume-gainers-spurts":
                query = f"""
                    INSERT OR REPLACE INTO {table}
                    (trading_date, symbol, company_name, ltp, p_change, volume,
                     week1_avg_volume, week1_vol_change, week2_avg_volume, week2_vol_change,
                     turnover, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                for r in records:
                    cursor.execute(
                        query,
                        (
                            trading_date,
                            r.get("symbol"),
                            r.get("companyName"),
                            self._safe_float(r.get("ltp")),
                            self._safe_float(r.get("pChange")),
                            str(r.get("volume", "")),
                            self._safe_float(r.get("week1AvgVolume")),
                            self._safe_float(r.get("week1volChange")),
                            self._safe_float(r.get("week2AvgVolume")),
                            self._safe_float(r.get("week2volChange")),
                            str(r.get("turnover", "")),
                            now_iso,
                        ),
                    )
                    inserted_count += 1

            elif dataset_id == "52-week-high":
                query = f"""
                    INSERT OR REPLACE INTO {table}
                    (trading_date, symbol, company_name, series, ltp, change, p_change,
                     new_52_week_high, prev_52_week_high, prev_high_date, prev_close, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                for r in records:
                    cursor.execute(
                        query,
                        (
                            trading_date,
                            r.get("symbol"),
                            r.get("comapnyName"),
                            r.get("series"),
                            self._safe_float(r.get("ltp")),
                            self._safe_float(r.get("change")),
                            self._safe_float(r.get("pChange")),
                            self._safe_float(r.get("new52WHL")),
                            self._safe_float(r.get("prev52WHL")),
                            str(r.get("prevHLDate", "")),
                            str(r.get("prevClose", "")),
                            now_iso,
                        ),
                    )
                    inserted_count += 1

            conn.commit()

        self.logger.info("[%s] Saved %d records to SQLite database %s", dataset_id, inserted_count, self.db_path)
        return inserted_count

    @staticmethod
    def _safe_float(val: Any) -> Optional[float]:
        """Convert a value to float safely or return None."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            cleaned = str(val).replace(",", "").replace("%", "").strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return None
