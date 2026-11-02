"""Shared pytest fixtures and test configuration."""

import json
from pathlib import Path
import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def test_config(project_root: Path) -> dict:
    """Load and return the real configuration dictionary."""
    config_path = project_root / "config" / "datasets.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_gainers_payload(project_root: Path) -> dict:
    """Return parsed sample gainers fixture."""
    path = project_root / "fixtures" / "sample_gainers.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_loosers_payload(project_root: Path) -> dict:
    """Return parsed sample losers fixture."""
    path = project_root / "fixtures" / "sample_loosers.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_upper_band_payload(project_root: Path) -> dict:
    """Return parsed sample upper band hitters fixture."""
    path = project_root / "fixtures" / "sample_upper_band.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_volume_gainers_payload(project_root: Path) -> dict:
    """Return parsed sample volume gainers fixture."""
    path = project_root / "fixtures" / "sample_volume_gainers.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_52_week_high_payload(project_root: Path) -> dict:
    """Return parsed sample 52 week high fixture."""
    path = project_root / "fixtures" / "sample_52_week_high.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pytest_addoption(parser):
    """Add custom CLI options to pytest."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live network tests against NSE endpoints.",
    )


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "live: mark test as requiring live NSE connectivity")


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --run-live option is passed."""
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="Live test skipped by default. Pass --run-live to execute.")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
