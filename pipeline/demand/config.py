"""
Shared configuration for the electricity demand pipeline.

All paths, defaults, and constants live here so individual stage modules
stay free of hard-coded values.
"""

from pathlib import Path

# --- Directory layout ---
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent.parent

# Output directories (created by the pipeline if missing)
OUTPUT_DIR = PROJECT_ROOT / "DATA" / "electricity-demand"
RAW_DIR = OUTPUT_DIR / "raw"

# --- AEMO NEMWeb URLs ---
ARCHIVE_URL = "https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/"
CURRENT_URL = "https://nemweb.com.au/Reports/Current/Operational_Demand/ACTUAL_DAILY/"

# --- Default date range ---
DEFAULT_START_DATE = "2025-07-01"
DEFAULT_END_DATE = "2026-06-30"

# --- NEM regions (expected) ---
NEM_REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]

# --- Request settings ---
TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds
REQUEST_DELAY = 0.5  # polite delay between downloads

# --- Output filenames ---
def consolidated_csv_name(start_yyyymmdd: str, end_yyyymmdd: str) -> str:
    """Return the filename for the consolidated half-hourly CSV."""
    return f"aemo_operational_demand_{start_yyyymmdd}_{end_yyyymmdd}.csv"


AGGREGATED_CSV_NAME = "demand_annual_summary.csv"
AGGREGATED_META_NAME = "demand_annual_summary.meta.json"
INSPECTION_SUMMARY_NAME = "inspection_summary.txt"

# --- Pipeline stages (in execution order) ---
STAGES = ["download", "validate", "inspect", "aggregate"]
