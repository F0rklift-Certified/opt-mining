"""
Download AEMO NEM Operational Demand data from nemweb.com.au.

This script downloads daily operational demand ZIP files from the AEMO NEMWeb
archive and current directories, extracts the CSVs, and concatenates them into
a single consolidated file for analysis.

Target: Operational_Demand/ACTUAL_DAILY/ — one file per day, all NEM regions.

Usage:
  python download_aemo_demand.py --start-date 2025-07-01 --end-date 2026-06-30
  python download_aemo_demand.py  # defaults to 2025-07-01 to 2026-06-30

Output:
  - Raw ZIPs:  raw/
  - Consolidated CSV: aemo_operational_demand_YYYYMMDD_YYYYMMDD.csv

Source: https://nemweb.com.au/Reports/
Licence: AEMO public data — free to use with attribution.
"""

import argparse
import io
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"

# NEMWeb URLs
ARCHIVE_URL = "https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/"
CURRENT_URL = "https://nemweb.com.au/Reports/Current/Operational_Demand/ACTUAL_DAILY/"

# Request settings
TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds
REQUEST_DELAY = 0.5  # polite delay between downloads

# Default date range
DEFAULT_START_DATE = "2025-07-01"
DEFAULT_END_DATE = "2026-06-30"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download AEMO NEM Operational Demand data.",
        epilog=(
            "Example:\n"
            "  python download_aemo_demand.py --start-date 2023-07-01 --end-date 2026-06-30\n"
            "  python download_aemo_demand.py  # uses defaults (2025-07-01 to 2026-06-30)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=DEFAULT_START_DATE,
        help=f"Start date in YYYY-MM-DD format (default: {DEFAULT_START_DATE})",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=DEFAULT_END_DATE,
        help=f"End date in YYYY-MM-DD format (default: {DEFAULT_END_DATE})",
    )
    return parser.parse_args()


def validate_date(date_str: str, label: str) -> str:
    """Validate a date string and return it in YYYYMMDD format for filename filtering."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid {label} format: '{date_str}'. Expected YYYY-MM-DD.")
        sys.exit(1)
    return dt.strftime("%Y%m%d")


def get_output_csv_path(start_yyyymmdd: str, end_yyyymmdd: str) -> Path:
    """Generate the output CSV path based on the date range."""
    return BASE_DIR / f"aemo_operational_demand_{start_yyyymmdd}_{end_yyyymmdd}.csv"


def get_file_list(index_url: str) -> list[str]:
    """Parse a NEMWeb directory listing to extract ZIP file names."""
    print(f"  Fetching directory listing: {index_url}")
    response = requests.get(index_url, timeout=TIMEOUT)
    response.raise_for_status()

    # NEMWeb uses simple HTML directory listings with filenames in the text
    # Pattern: PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_YYYYMMDD*.zip
    pattern = r'(PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_\d{8}[^"]*\.zip)'
    files = re.findall(pattern, response.text, re.IGNORECASE)
    return sorted(set(files))


def filter_files_by_date(files: list[str], start: str, end: str) -> list[str]:
    """Filter file list to those within the target date range."""
    filtered = []
    for f in files:
        # Extract date from filename: PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_YYYYMMDD...
        match = re.search(r'DAILY_(\d{8})', f, re.IGNORECASE)
        if match:
            file_date = match.group(1)
            if start <= file_date <= end:
                filtered.append(f)
    return filtered


def download_and_extract(base_url: str, filename: str) -> pd.DataFrame | None:
    """Download a single ZIP file and extract its CSV content into a DataFrame."""
    url = base_url + filename
    local_zip = RAW_DIR / filename

    # Skip if already downloaded
    if local_zip.exists():
        try:
            with zipfile.ZipFile(local_zip, 'r') as zf:
                csv_names = [n for n in zf.namelist() if n.endswith('.csv') or n.endswith('.CSV')]
                if csv_names:
                    with zf.open(csv_names[0]) as csv_file:
                        return parse_aemo_csv(csv_file)
        except (zipfile.BadZipFile, Exception):
            local_zip.unlink(missing_ok=True)  # Re-download if corrupt

    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()

            # Save ZIP locally
            local_zip.write_bytes(resp.content)

            # Extract CSV from ZIP
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith('.csv') or n.endswith('.CSV')]
                if not csv_names:
                    print(f"    WARNING: No CSV found in {filename}")
                    return None
                with zf.open(csv_names[0]) as csv_file:
                    return parse_aemo_csv(csv_file)

        except requests.exceptions.RequestException as e:
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"    Retry {attempt + 1}/{RETRY_ATTEMPTS} for {filename}: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"    FAILED to download {filename}: {e}")
                return None


def parse_aemo_csv(file_obj) -> pd.DataFrame | None:
    """
    Parse an AEMO CSV file.

    AEMO CSVs have a specific structure:
    - Row 1: Header line starting with 'C' (comment) or 'I' (header) or 'D' (data)
    - The actual data rows start with 'D' in the first column
    - Header row starts with 'I'
    """
    try:
        # Read all lines
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')

        lines = content.strip().split('\n')

        # Find header line (starts with I) and data lines (start with D)
        header_line = None
        data_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            first_field = stripped.split(',')[0].strip().upper()
            if first_field == 'I':
                header_line = stripped
            elif first_field == 'D':
                data_lines.append(stripped)

        if header_line is None or not data_lines:
            # Try reading as a plain CSV (some AEMO files are simpler)
            file_obj_new = io.StringIO(content)
            df = pd.read_csv(file_obj_new)
            if len(df) > 0:
                return df
            return None

        # Parse header
        header_fields = [f.strip() for f in header_line.split(',')]

        # Parse data
        all_data = []
        for line in data_lines:
            fields = [f.strip() for f in line.split(',')]
            all_data.append(fields)

        # Create DataFrame — align columns with header
        # Ensure all rows have same number of columns as header
        n_cols = len(header_fields)
        aligned_data = []
        for row in all_data:
            if len(row) >= n_cols:
                aligned_data.append(row[:n_cols])
            else:
                aligned_data.append(row + [''] * (n_cols - len(row)))

        df = pd.DataFrame(aligned_data, columns=header_fields)
        return df

    except Exception as e:
        print(f"    WARNING: Failed to parse CSV: {e}")
        return None


def main():
    """Main download and consolidation workflow."""
    args = parse_args()

    # Validate dates
    start_yyyymmdd = validate_date(args.start_date, "start-date")
    end_yyyymmdd = validate_date(args.end_date, "end-date")

    if start_yyyymmdd >= end_yyyymmdd:
        print(f"ERROR: --start-date ({args.start_date}) must be before --end-date ({args.end_date}).")
        sys.exit(1)

    output_csv = get_output_csv_path(start_yyyymmdd, end_yyyymmdd)

    print("=" * 70)
    print("AEMO NEM Operational Demand Data Download")
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Output: {output_csv}")
    print("=" * 70)

    # Ensure directories exist
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Get file listings from Archive and Current
    print("\n[1/4] Scanning NEMWeb directories for available files...")

    all_files = {}  # filename -> base_url

    # Try Archive first (has older data)
    try:
        archive_files = get_file_list(ARCHIVE_URL)
        archive_filtered = filter_files_by_date(archive_files, start_yyyymmdd, end_yyyymmdd)
        print(f"  Archive: {len(archive_filtered)} files in date range (of {len(archive_files)} total)")
        for f in archive_filtered:
            all_files[f] = ARCHIVE_URL
    except Exception as e:
        print(f"  Archive unavailable: {e}")

    # Also check Current (has recent data)
    try:
        current_files = get_file_list(CURRENT_URL)
        current_filtered = filter_files_by_date(current_files, start_yyyymmdd, end_yyyymmdd)
        print(f"  Current: {len(current_filtered)} files in date range (of {len(current_files)} total)")
        for f in current_filtered:
            if f not in all_files:  # Don't override archive with current
                all_files[f] = CURRENT_URL
    except Exception as e:
        print(f"  Current unavailable: {e}")

    if not all_files:
        print("\nERROR: No files found for the target date range.")
        print("This may mean the Archive directory structure is different.")
        print("Trying alternative: download from Current directory (recent data only)...")

        # Fallback: just download whatever is available in Current
        try:
            current_files = get_file_list(CURRENT_URL)
            if current_files:
                # Take up to 60 most recent files as a sample
                for f in current_files[-60:]:
                    all_files[f] = CURRENT_URL
                print(f"  Fallback: using {len(all_files)} most recent files from Current")
        except Exception as e:
            print(f"  Fallback also failed: {e}")
            sys.exit(1)

    sorted_files = sorted(all_files.keys())
    print(f"\n  Total files to download: {len(sorted_files)}")

    # Step 2: Download and extract
    print(f"\n[2/4] Downloading {len(sorted_files)} files...")

    all_dfs = []
    success_count = 0
    fail_count = 0

    for i, filename in enumerate(sorted_files, 1):
        if i % 50 == 0 or i == 1:
            print(f"  Progress: {i}/{len(sorted_files)}")

        base_url = all_files[filename]
        df = download_and_extract(base_url, filename)

        if df is not None and len(df) > 0:
            all_dfs.append(df)
            success_count += 1
        else:
            fail_count += 1

        time.sleep(REQUEST_DELAY)

    print(f"\n  Downloaded: {success_count} files successfully, {fail_count} failures")

    if not all_dfs:
        print("\nERROR: No data was successfully downloaded.")
        sys.exit(1)

    # Step 3: Concatenate
    print("\n[3/4] Concatenating into a single DataFrame...")
    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"  Combined shape: {combined.shape[0]} rows x {combined.shape[1]} columns")
    print(f"  Columns: {list(combined.columns)}")

    # Step 4: Save
    print(f"\n[4/4] Saving to {output_csv}...")
    combined.to_csv(output_csv, index=False)
    file_size_mb = output_csv.stat().st_size / (1024 * 1024)
    print(f"  Saved: {file_size_mb:.2f} MB")

    # Summary
    print("\n" + "=" * 70)
    print("DOWNLOAD COMPLETE")
    print(f"  Date range: {args.start_date} to {args.end_date}")
    print(f"  Rows: {len(combined):,}")
    print(f"  Columns: {combined.shape[1]}")
    print(f"  File: {output_csv}")
    print(f"  Size: {file_size_mb:.2f} MB")
    print("=" * 70)


if __name__ == "__main__":
    main()
