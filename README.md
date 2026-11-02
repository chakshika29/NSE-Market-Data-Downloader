# NSE Market Data Downloader

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-31%20passed%2C%204%20skipped-brightgreen.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-pep8-green.svg)]()
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

A production-grade Python backend application that automatically retrieves four core market datasets from the National Stock Exchange of India (NSE) and persists each dataset as an independently validated, atomic CSV file.

Built according to the specification of the **NSE Market Data Downloader Engineering Assignment**.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Assignment Objective](#assignment-objective)
3. [Key Features](#key-features)
4. [Technology Stack](#technology-stack)
5. [Architecture & Project Structure](#architecture--project-structure)
6. [Data Acquisition Method & Permitted Access](#data-acquisition-method--permitted-access)
7. [Installation & Virtual Environment Setup](#installation--virtual-environment-setup)
8. [Configuration Guide](#configuration-guide)
9. [Command-Line Interface (CLI) Usage](#command-line-interface-cli-usage)
10. [CSV Output Specifications & Examples](#csv-output-specifications--examples)
11. [Data Validation Engine](#data-validation-engine)
12. [Duplicate Handling Strategy](#duplicate-handling-strategy)
13. [Error Handling & Reliability](#error-handling--reliability)
14. [Logging Architecture](#logging-architecture)
15. [Automated Scheduling (Windows & Linux/macOS)](#automated-scheduling-windows--linuxmacos)
16. [Automated Test Suite (Pytest)](#automated-test-suite-pytest)
17. [Bonus Features](#bonus-features)
    - [Optional SQLite Database Storage](#optional-sqlite-database-storage)
    - [Market Session Calendar & Hours Check](#market-session-calendar--hours-check)
    - [Docker Containerization](#docker-containerization)
18. [Assumptions & Known Limitations](#assumptions--known-limitations)
19. [Verification & Submission Checklist](#verification--submission-checklist)

---

## Project Overview

The **NSE Market Data Downloader** is designed as a resilient, maintainable, and observable financial data pipeline. Instead of relying on fragile web scrapers, rotating proxies, or unauthorized anti-bot circumventions, this application connects directly to the underlying REST endpoints that power NSE's public web components, enforces strict dataset validation, guarantees atomic file persistence, and cleanly isolates failures so that a transient issue in one market sector never compromises the processing of the others.

---

## Assignment Objective

The primary objective is to automatically retrieve four specific market-data segments from NSE India and save them as separate CSV files:

| # | Dataset Name | Public Web Page | Primary API Endpoint |
|---|---|---|---|
| 1 | **Top Gainers / Losers** | [/market-data/top-gainers-losers](https://www.nseindia.com/market-data/top-gainers-losers) | `/api/live-analysis-variations?index=gainers` & `loosers` |
| 2 | **Upper Band Hitters** | [/market-data/upper-band-hitters](https://www.nseindia.com/market-data/upper-band-hitters) | `/api/live-analysis-price-band-hitter` |
| 3 | **Volume Gainers / Spurts** | [/market-data/volume-gainers-spurts](https://www.nseindia.com/market-data/volume-gainers-spurts) | `/api/live-analysis-volume-gainers` |
| 4 | **52-Week High — Equity** | [/market-data/52-week-high-equity-market](https://www.nseindia.com/market-data/52-week-high-equity-market) | `/api/live-analysis-data-52weekhighstock` |

---

## Key Features

- **Failure Isolation:** Each dataset executes independently. A failure in one dataset does not block the pipeline from processing the remaining datasets.
- **Deterministic File Naming:** Filenames follow standard conventions (`top_gainers_losers_YYYY-MM-DD.csv`, `upper_band_hitters_YYYY-MM-DD.csv`, `volume_gainers_spurts_YYYY-MM-DD.csv`, `52_week_high_YYYY-MM-DD.csv`).
- **Source Metadata Date Parsing:** Extracts the actual trading date directly from the payload timestamp metadata (e.g., `'02-Nov-2026 16:00:00'` $\to$ `2026-11-02`) preventing silent mislabeling of weekend or historical records with today's date.
- **Atomic File Writes:** Writes to a unique `.tmp` staging file first and swaps into place via `os.replace`. Existing files are never overwritten with invalid or empty data.
- **Precision Preservation:** Preserves high-precision floating point ratios, turnover numbers, and large transaction quantities without scientific notation truncation.
- **Top Gainers & Losers Merging:** Combines both market variation endpoints into a single unified dataset while explicitly preserving the `category` attribute (`'gainer'` vs `'loser'`).
- **Legitimate Distinct Records Safeguard:** Deduplication respects composite keys (`['symbol', 'category']` or `['symbol', 'series']`), ensuring legitimate market records sharing the same symbol across different categories or share classes (e.g. `EQ` vs `DVR`) are not dropped.
- **Exponential Backoff:** Retries transient server errors (500, 502, 503, 504, timeouts) with exponential backoff, while failing fast immediately on authorization/access-denied (401, 403) responses.
- **Dual Execution Modes:** Supports live network execution as well as offline/demonstration runs with bundled synthetic test fixtures (`--use-fixture`).
- **Comprehensive Logging:** Dual logging to console and persistent file `logs/app.log`.

---

## Technology Stack

- **Python 3.11+**: Standard Python modern typing, dataclasses, and path handling.
- **Requests**: Permitted HTTP client with connection pooling and session management.
- **Pandas**: Structured data processing, column ordering, and UTF-8 CSV generation.
- **Pytest**: Automated test suite for unit, integration, and mocking scenarios.
- **SQLite3**: Standard library database engine for optional historical storage.
- **Docker**: Containerized deployment capability.

---

## Architecture & Project Structure

The project follows a clean separation of concerns:

```
NSE-Market-Data-Downloader/
│
├── main.py                     # CLI entrypoint, argument parsing, pipeline orchestration
├── config/
│   └── datasets.json           # Declarative dataset configurations, endpoints, validation rules
├── src/
│   ├── __init__.py             # Package marker
│   ├── downloader.py           # HTTP client, session management, backoff retries, fast-fail
│   ├── validator.py            # Reusable validation engine, date parsing, duplicate handler
│   ├── csv_manager.py          # Atomic CSV persistence, deterministic naming, precision safety
│   ├── db_manager.py           # (Bonus) SQLite database persistence for historical data
│   ├── market_calendar.py      # (Bonus) Market session hours and trading holiday checker
│   └── logger.py               # Structured dual-handler logging configuration
├── tests/
│   ├── __init__.py             # Test package marker
│   ├── conftest.py             # Pytest fixtures, mock loaders, CLI test options
│   ├── test_downloader.py      # Unit tests for HTTP client, retries, 403 fast-fail, HTML reject
│   ├── test_validator.py       # Unit tests for schema validation, date parsing, dedup safety
│   ├── test_csv_manager.py     # Unit tests for atomic file writes, precision, empty-write protection
│   ├── test_integration.py     # Pipeline integration tests, CLI flags, failure isolation, SQLite
│   └── test_live.py            # Optional live endpoint tests (marked with @pytest.mark.live)
├── fixtures/                   # Deterministic synthetic test fixtures (offline testing)
│   ├── sample_gainers.json
│   ├── sample_loosers.json
│   ├── sample_upper_band.json
│   ├── sample_volume_gainers.json
│   └── sample_52_week_high.json
├── output/                     # Generated CSV files and SQLite database
│   ├── .gitkeep
│   ├── top_gainers_losers_2026-11-02.csv
│   ├── upper_band_hitters_2026-11-02.csv
│   ├── volume_gainers_spurts_2026-11-02.csv
│   └── 52_week_high_2026-11-02.csv
├── logs/                       # Application runtime logs
│   ├── .gitkeep
│   └── app.log
├── requirements.txt            # Pinned dependencies
├── Dockerfile                  # Containerized execution environment
├── .dockerignore               # Docker ignore rules
├── .gitignore                  # Git ignore rules
└── README.md                   # Comprehensive technical documentation
```

---

## Data Acquisition Method & Permitted Access

### Permitted Data Access Principles
1. **Respect for Exchange Policies:** The application does not bypass CAPTCHAs, decrypt bot challenges, use headless stealth browsers, or employ rotating proxy farms.
2. **Authorized Public REST Endpoints:** Rather than parsing complex HTML frontends or scraping DOM trees, the application queries the direct, public JSON endpoints invoked by NSE's frontend JavaScript components (`live-analysis`).
3. **Session Warmup & Headers:** Requests include standard HTTP headers (`User-Agent`, `Accept`, `Accept-Language`) and maintain a shared `requests.Session()` instance to handle standard cookies.
4. **Honest Restriction Reporting:** If NSE's security gateways (such as Akamai Web Application Firewall) return an `HTTP 401 Unauthorized` or `HTTP 403 Forbidden`, the application treats this as a hard boundary, reports an `AccessRestrictedError` with clear diagnostics, and does not retry.
5. **No Fabricated Data:** The pipeline operates strictly on genuine data retrieved from the server. When running offline or in unit tests, test fixtures are clearly separated in the `fixtures/` directory and labeled as synthetic test data.

---

## Installation & Virtual Environment Setup

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/NSE-Market-Data-Downloader.git
cd NSE-Market-Data-Downloader
```

### 2. Set Up a Virtual Environment

#### On Windows (PowerShell / Command Prompt):
```powershell
python -m venv .venv
.venv\Scripts\activate
```

#### On Linux / macOS (Bash / Zsh):
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Required Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Configuration Guide

All endpoints, required fields, deduplication keys, column orderings, and network retry parameters are maintained externally in [`config/datasets.json`](config/datasets.json). Application logic does not hard-code endpoint URLs or schema definitions.

Example excerpt for `volume-gainers-spurts`:
```json
{
  "id": "volume-gainers-spurts",
  "name": "Volume Gainers / Spurts",
  "page_url": "https://www.nseindia.com/market-data/volume-gainers-spurts",
  "csv_filename_prefix": "volume_gainers_spurts",
  "endpoints": {
    "primary": "https://www.nseindia.com/api/live-analysis-volume-gainers"
  },
  "data_path": ["data"],
  "timestamp_path": ["timestamp"],
  "required_fields": ["symbol", "volume", "week1AvgVolume"],
  "dedup_keys": ["symbol"],
  "numeric_fields": ["ltp", "pChange", "week1AvgVolume", "week1volChange", "week2AvgVolume", "week2volChange"]
}
```

---

## Command-Line Interface (CLI) Usage

### 1. Download All Four Datasets (Default)
Attempts to download and validate all four market datasets in sequence:
```bash
python main.py
```

### 2. Download Individual Datasets
```bash
# Top Gainers / Losers
python main.py --dataset top-gainers-losers

# Upper Band Hitters
python main.py --dataset upper-band-hitters

# Volume Gainers / Spurts
python main.py --dataset volume-gainers-spurts

# 52-Week High Equity Market
python main.py --dataset 52-week-high
```

### 3. Configurable Output Directory
Specify any custom target directory for generated CSV files:
```bash
python main.py --output-dir ./market_data
```

### 4. Display Help and Usage Instructions
```bash
python main.py --help
```

### 5. Optional Flags
```bash
# Persist records to an SQLite database in addition to CSV
python main.py --save-db --db-path ./output/market_data.db

# Check whether the NSE market is open (09:15 - 15:30 IST) and exit cleanly if closed
python main.py --check-market-open

# Run offline using synthetic test fixtures (useful for demonstrations or CI/CD)
python main.py --use-fixture

# Increase logging verbosity to DEBUG
python main.py --log-level DEBUG
```

---

## CSV Output Specifications & Examples

### Filename Standards
Files are saved with deterministic filenames derived from the dataset prefix and the trading date parsed from source metadata:
- `top_gainers_losers_YYYY-MM-DD.csv`
- `upper_band_hitters_YYYY-MM-DD.csv`
- `volume_gainers_spurts_YYYY-MM-DD.csv`
- `52_week_high_YYYY-MM-DD.csv`

### Sample Output Headers & Records

#### 1. Top Gainers / Losers (`output/top_gainers_losers_2026-11-02.csv`)
```csv
symbol,series,category,open_price,high_price,low_price,ltp,prev_price,net_price,perChange,trade_quantity,turnover
ITI,EQ,gainer,216.25,259.14,214.39,259.14,215.95,20,20,171.99 L,431.65 Cr
GAYAHWS,EQ,gainer,1.57,1.88,1.57,1.88,1.57,19.75,19.75,9.97 L,18.05 L
SHIVAM-RE1,BE,loser,0.61,0.61,0.5,0.51,0.61,-16.39,-16.39,1.77 L,90.30 K
SANGHVIMOV,EQ,loser,365.75,382.1,296.65,319,366.3,-12.91,-12.91,63.00 L,206.10 Cr
```

#### 2. Upper Band Hitters (`output/upper_band_hitters_2026-11-02.csv`)
```csv
symbol,series,priceBand,ltp,change,pChange,highPrice,lowPrice,totalTradedVol,totalTradedVolcsv,turnover,turnovercsv,yearHigh,yearLow
ITI,EQ,20,259.14,43.19,20.00,259.14,214.39,171.99 L,17199121,431.65 Cr,4316463397.37,335,210.76
MENONBE,EQ,20,310.2,34,12.31,331.4,278.95,36.24 L,3623964,114.79 Cr,1147930000.0,331.4,101.5
BHARATWIRE,EQ,20,159.29,17.59,12.41,170.04,142,27.85 L,2784640,45.11 Cr,451140000.0,262,140.5
```

#### 3. Volume Gainers / Spurts (`output/volume_gainers_spurts_2026-11-02.csv`)
```csv
symbol,companyName,ltp,pChange,volume,week1AvgVolume,week1volChange,week2AvgVolume,week2volChange,turnover
CLCIND,CLC Industries Limited,42,0,50.00 K,115,434.809,157,317.479,21.00 L
MONEXT50,Motilal Oswal Mutual Fund - Motilal Oswal Nifty Next 50 ETF,68.42,0.97,12.65 L,4830,261.901,8027,157.591,8.71 Cr
ITI,ITI Limited,259.14,20,171.99 L,135055,127.349,161292,106.633,431.65 Cr
```

#### 4. 52-Week High Equity (`output/52_week_high_2026-11-02.csv`)
```csv
symbol,comapnyName,series,ltp,change,pChange,new52WHL,prev52WHL,prevHLDate,prevClose
21STCENMGM,21st Century Management Services Limited,EQ,60.71,2.89,4.9982704946385335,60.71,57.82,30-Oct-2026,57.82
63MOONS,63 moons technologies limited,EQ,959.5,10.65,1.12241,981.85,968.75,30-Oct-2026,948.85
ACUTAAS,Acutaas Chemicals Limited,EQ,3878,-125.6,-3.13718,4045.3,4032.2,29-Oct-2026,4003.6
```

---

## Data Validation Engine

The `DataValidator` class ([`src/validator.py`](src/validator.py)) performs comprehensive multi-stage checks before any dataset is written to disk:

1. **Payload Structure Validation:** Ensures the root payload is an instantiated dictionary or list and not `None` or an empty payload.
2. **Non-Empty Result Check:** Verifies that the record list contains at least one record.
3. **Required Field Verification:** Every record is checked for presence and non-null values of dataset-specific required fields (e.g. `symbol`, `ltp`, `priceBand`).
4. **Numerical Precision & Format Verification:** Validates that numerical fields can be parsed without data corruption, cleanly handling Indian currency suffixes (`Cr`, `L`, `K`) when present in market volume strings.
5. **Atomic Writing Safeguard:** If validation fails, `CSVManager` refuses to touch the target file. An invalid response will **never** overwrite an existing valid CSV.

---

## Duplicate Handling Strategy

- **True Duplicate Elimination:** When duplicate records with identical composite keys are received in the same response, the duplicate instances are dropped and logged with a warning.
- **Preservation of Distinct Market Records:**
  - **Category Separation:** For *Top Gainers / Losers*, deduplication operates on the composite key `['symbol', 'series', 'category']`. If a stock appears as both a gainer and a loser across different sessions or market segments, neither record is discarded.
  - **Share Class Separation:** Deduplication incorporates `series` (e.g. `EQ`, `BE`, `SM`), ensuring multiple share classes of the same company (e.g., standard equity vs. differential voting rights) are preserved.

---

## Error Handling & Reliability

| Failure Scenario | Component | Handling Behavior |
|---|---|---|
| **Network Disconnection / Timeout** | `NSEDownloader` | Retries up to 3 times with exponential backoff ($1.5 \times 2^{\text{attempt}-1}$). Raises `NetworkTimeoutError` if exhausted. |
| **HTTP 500 / 502 / 503 / 504** | `NSEDownloader` | Treated as transient server errors. Retried with exponential backoff. |
| **HTTP 401 / 403 (Access Denied)** | `NSEDownloader` | **Fails fast immediately.** No repeated retries. Raises `AccessRestrictedError` and logs clear policy diagnostic. |
| **Unexpected HTML / Captcha** | `NSEDownloader` | Detects HTML doctype on JSON routes and raises `InvalidResponseError`. |
| **Empty or Corrupt JSON** | `NSEDownloader` | Traps `json.JSONDecodeError` and logs detailed parsing error. |
| **Dataset Failure Isolation** | `main.py` | Exceptions during processing of one dataset are caught and recorded. The loop continues to the next dataset. |
| **CSV Write Interruption** | `CSVManager` | Writes to a temporary `.tmp` file first. The target file is replaced only upon complete, error-free write. |

---

## Logging Architecture

Logs are written simultaneously to the terminal (for interactive CLI visibility) and to [`logs/app.log`](logs/app.log) (for persistent audit trails).

Log format:
```text
2026-11-02 16:35:59 | INFO     | nse_downloader | [upper-band-hitters] Successfully downloaded 116 records in 0.21s (Trading Date: 2026-11-02)
2026-11-02 16:35:59 | INFO     | nse_downloader | [upper-band-hitters] Validation result: Status: PASSED | Records: 116 | Errors: 0 | Warnings: 0 | Date: 2026-11-02
2026-11-02 16:35:59 | INFO     | nse_downloader | [upper-band-hitters] Successfully saved 116 records atomically to output\upper_band_hitters_2026-11-02.csv
```

At the conclusion of every execution, a structured tabular summary is printed:
```text
=================================================================
FINAL EXECUTION SUMMARY
=================================================================
Dataset                  | Status           | Records  | Date       | CSV Output
--------------------------------------------------------------------------------
top-gainers-losers       | SUCCESS          | 40       | 2026-11-02 | top_gainers_losers_2026-11-02.csv
upper-band-hitters       | SUCCESS          | 116      | 2026-11-02 | upper_band_hitters_2026-11-02.csv
volume-gainers-spurts    | SUCCESS          | 25       | 2026-11-02 | volume_gainers_spurts_2026-11-02.csv
52-week-high             | SUCCESS          | 57       | 2026-11-02 | 52_week_high_2026-11-02.csv
=================================================================
```

---

## Automated Scheduling (Windows & Linux/macOS)

The downloader can run unattended via system schedulers. By pairing with `--check-market-open`, the scheduler will skip redundant executions on weekends or when the market is closed.

### 1. Linux / macOS (cron)
Run every weekday (Monday through Friday) at 16:00 IST (after market close):

Edit your crontab:
```bash
crontab -e
```

Add the entry:
```cron
# Run NSE downloader Monday to Friday at 16:00 IST (10:30 UTC)
30 10 * * 1-5 cd /path/to/NSE-Market-Data-Downloader && /path/to/NSE-Market-Data-Downloader/.venv/bin/python main.py --check-market-open >> logs/cron.log 2>&1
```

### 2. Windows Task Scheduler
You can schedule the task using PowerShell or the `schtasks` utility:

#### Using PowerShell:
```powershell
$Action = New-ScheduledTaskAction -Execute "C:\Users\Dell\Desktop\NSE-Market-Data-Downloader\.venv\Scripts\python.exe" `
    -Argument "main.py --check-market-open" `
    -WorkingDirectory "C:\Users\Dell\Desktop\NSE-Market-Data-Downloader"

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 16:00

Register-ScheduledTask -TaskName "NSE_Market_Data_Downloader" -Action $Action -Trigger $Trigger -Description "Automated daily download of NSE equity market datasets"
```

#### Using Command Prompt (`schtasks`):
```cmd
schtasks /create /tn "NSE_Market_Data_Downloader" /tr "C:\Users\Dell\Desktop\NSE-Market-Data-Downloader\.venv\Scripts\python.exe main.py --check-market-open" /sc weekly /d MON,TUE,WED,THU,FRI /st 16:00
```

---

## Automated Test Suite (Pytest)

The project includes unit tests, error simulation tests, and end-to-end integration tests.

### 1. Run All Deterministic Unit & Integration Tests (Mocked)
```bash
pytest -v
```
*Result: 31 passed, 4 skipped (live tests cleanly skipped by default).*

### 2. Run Only Integration Tests
```bash
pytest tests/test_integration.py -v
```

### 3. Run Optional Live Network Tests (Against NSE Servers)
```bash
pytest tests/test_live.py -v --run-live
```
*Connects to live endpoints to confirm real network communication.*

---

## Bonus Features

### Optional SQLite Database Storage
Pass `--save-db` to store records in an embedded SQLite database (`output/market_data.db`):
```bash
python main.py --save-db
```
The database maintains historical data and enforces uniqueness constraints:
- `top_gainers_losers`: Unique on `(trading_date, symbol, series, category)`
- `upper_band_hitters`: Unique on `(trading_date, symbol, series)`
- `volume_gainers_spurts`: Unique on `(trading_date, symbol)`
- `fifty_two_week_high`: Unique on `(trading_date, symbol, series)`

### Market Session Calendar & Hours Check
The `src/market_calendar.py` module models:
- Normal trading session: Monday–Friday, 09:15 to 15:30 IST.
- Weekend closure detection (Saturday/Sunday).
- Declared annual NSE trading holidays (Republic Day, Independence Day, Gandhi Jayanti, Diwali, Christmas, etc.).

### Docker Containerization
Run without any local Python setup via Docker:

```bash
# Build the Docker image
docker build -t nse-downloader:latest .

# Run container (mounting local output directory for CSV persistence)
docker run --rm -v "$(pwd)/output:/app/output" -v "$(pwd)/logs:/app/logs" nse-downloader:latest

# Run for a single dataset
docker run --rm -v "$(pwd)/output:/app/output" nse-downloader:latest --dataset volume-gainers-spurts
```

---

## Assumptions & Known Limitations

1. **Market Hours & Live Updates:** During active market hours (09:15–15:30 IST), figures update dynamically. Running the application multiple times on the same trading day atomically updates the same date CSV file with the most recent snapshot.
2. **Cloudflare / Akamai Bot Mitigation:** NSE occasionally adjusts anti-bot thresholds. If access restrictions (`HTTP 403`) occur, the application halts cleanly without spamming requests. For authorized high-throughput enterprise feeds, an official NSE Data & Analytics subscription feed should be configured in `config/datasets.json`.
3. **Data Availability Outside Trading Sessions:** When markets are closed for holidays or weekends, NSE serves the last recorded session's closing figures. The metadata date parser preserves this historical trading date rather than labeling the file with the current calendar date.

---

## Verification & Submission Checklist

- [x] Python 3.11+ clean compilation with zero warnings (`python -m py_compile main.py src/*.py`).
- [x] All 4 required datasets supported independently.
- [x] CLI supports all required flags (`--dataset`, `--output-dir`, `--help`).
- [x] Reusable validator enforces schema, required columns, and non-empty responses.
- [x] Duplicate handling preserves distinct categories (`gainer` vs `loser`) and series.
- [x] Deterministic CSV filenames generated atomically via temporary files.
- [x] Full numerical precision preserved in exported CSVs.
- [x] Failure in one dataset isolated from other datasets.
- [x] Structured logs written to `logs/app.log` and console.
- [x] 31 unit and integration tests passing in Pytest.
- [x] 4 live connectivity tests verified and passing against NSE endpoints.
- [x] Optional SQLite historical database storage implemented.
- [x] Optional Dockerfile and scheduling documentation provided.
- [x] Clean `.gitignore` excluding caches, logs, and temp files.
