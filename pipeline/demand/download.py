"""
Download stage — fetch AEMO NEM Operational Demand data from NEMWeb.

Downloads daily operational demand ZIP files from the AEMO NEMWeb archive
and current directories, extracts the CSVs, and concatenates them into a
single consolidated file.

Importable entry point:
    from pipelines.demand.download import run
    csv_path = run(start_date="2025-07-01", end_date="2026-06-30",
                   output_dir=Path(...), raw_dir=Path(...))

Standalone usage:
    python -m pipelines.demand.download --start-date 2025-07-01 --end-date 2026-06-30

Source: https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/
Licence: AEMO public data — free to use with attribution.
"""

import argparse
import io
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from . import config


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def get_file_list(index_url: str, verbose: bool = False) -> list[str]:
    """Parse a NEMWeb directory listing to extract ZIP file names."""
    if verbose:
        print(f"    Fetching directory listing: {index_url}")
    response = requests.get(index_url, timeout=config.TIMEOUT)
    response.raise_for_status()

    pattern = r'(PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_\d{8}[^"]*\.zip)'
    files = re.findall(pattern, response.text, re.IGNORECASE)
    return sorted(set(files))


def filter_files_by_date(files: list[str], start: str, end: str) -> list[str]:
    """Filter file list to those within the target date range (YYYYMMDD)."""
    filtered = []
    for f in files:
        match = re.search(r'DAILY_(\d{8})', f, re.IGNORECASE)
        if match:
            file_date = match.group(1)
            if start <= file_date <= end:
                filtered.append(f)
    return filtered


def parse_aemo_csv(file_obj) -> pd.DataFrame | None:
    """
    Parse an AEMO CSV file.

    AEMO CSVs use an I/D/C row format:
      C = comment, I = header, D = data.
    Falls back to plain CSV parsing if that structure is not detected.
    """
    try:
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')

        lines = content.strip().split('\n')

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
            # Try reading as a plain CSV
            file_obj_new = io.StringIO(content)
            df = pd.read_csv(file_obj_new)
            if len(df) > 0:
                return df
            return None

        header_fields = [f.strip() for f in header_line.split(',')]

        all_data = []
        for line in data_lines:
            fields = [f.strip() for f in line.split(',')]
            all_data.append(fields)

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


def download_and_extract(
    base_url: str,
    filename: str,
    raw_dir: Path,
    verbose: bool = False,
) -> pd.DataFrame | None:
    """Download a single ZIP file and extract its CSV content into a DataFrame."""
    url = base_url + filename
    local_zip = raw_dir / filename

    # Use cached ZIP if already downloaded
    if local_zip.exists():
        try:
            with zipfile.ZipFile(local_zip, 'r') as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
                if csv_names:
                    with zf.open(csv_names[0]) as csv_file:
                        return parse_aemo_csv(csv_file)
        except (zipfile.BadZipFile, Exception):
            local_zip.unlink(missing_ok=True)  # Re-download if corrupt

    for attempt in range(config.RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=config.TIMEOUT)
            resp.raise_for_status()

            # Save ZIP locally
            local_zip.write_bytes(resp.content)

            # Extract CSV from ZIP
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
                if not csv_names:
                    if verbose:
                        print(f"    WARNING: No CSV found in {filename}")
                    return None
                with zf.open(csv_names[0]) as csv_file:
                    return parse_aemo_csv(csv_file)

        except requests.exceptions.RequestException as e:
            if attempt < config.RETRY_ATTEMPTS - 1:
                if verbose:
                    print(f"    Retry {attempt + 1}/{config.RETRY_ATTEMPTS} for {filename}: {e}")
                time.sleep(config.RETRY_DELAY)
            else:
                print(f"    FAILED to download {filename}: {e}")
                return None

    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    start_date: str,
    end_date: str,
    output_dir: Path,
    raw_dir: Path,
    verbose: bool = False,
) -> Path:
    """
    Download and consolidate AEMO demand data for the given date range.

    Parameters
    ----------
    start_date : str
        Start date in YYYY-MM-DD format.
    end_date : str
        End date in YYYY-MM-DD format.
    output_dir : Path
        Directory for the consolidated CSV output.
    raw_dir : Path
        Directory for raw ZIP archives.
    verbose : bool
        Enable detailed progress logging.

    Returns
    -------
    Path
        Path to the consolidated CSV file.
    """
    start_yyyymmdd = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
    end_yyyymmdd = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d")

    output_csv = output_dir / config.consolidated_csv_name(start_yyyymmdd, end_yyyymmdd)

    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Output: {output_csv.name}")

    # Ensure directories exist
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Get file listings from Archive and Current
    print("\n  [1/4] Scanning NEMWeb directories...")

    all_files: dict[str, str] = {}  # filename -> base_url

    try:
        archive_files = get_file_list(config.ARCHIVE_URL, verbose=verbose)
        archive_filtered = filter_files_by_date(archive_files, start_yyyymmdd, end_yyyymmdd)
        print(f"    Archive: {len(archive_filtered)} files in date range (of {len(archive_files)} total)")
        for f in archive_filtered:
            all_files[f] = config.ARCHIVE_URL
    except Exception as e:
        print(f"    Archive unavailable: {e}")

    try:
        current_files = get_file_list(config.CURRENT_URL, verbose=verbose)
        current_filtered = filter_files_by_date(current_files, start_yyyymmdd, end_yyyymmdd)
        print(f"    Current: {len(current_filtered)} files in date range (of {len(current_files)} total)")
        for f in current_filtered:
            if f not in all_files:
                all_files[f] = config.CURRENT_URL
    except Exception as e:
        print(f"    Current unavailable: {e}")

    if not all_files:
        print("\n  ERROR: No files found for the target date range.")
        print("  Trying fallback: most recent files from Current directory...")

        try:
            current_files = get_file_list(config.CURRENT_URL, verbose=verbose)
            if current_files:
                for f in current_files[-60:]:
                    all_files[f] = config.CURRENT_URL
                print(f"    Fallback: using {len(all_files)} most recent files from Current")
        except Exception as e:
            print(f"    Fallback also failed: {e}")
            raise RuntimeError("No AEMO demand data files could be located.") from e

    sorted_files = sorted(all_files.keys())
    print(f"    Total files to download: {len(sorted_files)}")

    # Step 2: Download and extract
    print(f"\n  [2/4] Downloading {len(sorted_files)} files...")

    all_dfs = []
    success_count = 0
    fail_count = 0

    for i, filename in enumerate(sorted_files, 1):
        if verbose and (i % 50 == 0 or i == 1):
            print(f"    Progress: {i}/{len(sorted_files)}")

        base_url = all_files[filename]
        df = download_and_extract(base_url, filename, raw_dir, verbose=verbose)

        if df is not None and len(df) > 0:
            all_dfs.append(df)
            success_count += 1
        else:
            fail_count += 1

        time.sleep(config.REQUEST_DELAY)

    print(f"    Downloaded: {success_count} files, {fail_count} failures")

    if not all_dfs:
        raise RuntimeError("No data was successfully downloaded from AEMO.")

    # Step 3: Concatenate
    print("\n  [3/4] Concatenating into single DataFrame...")
    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"    Combined shape: {combined.shape[0]:,} rows × {combined.shape[1]} columns")

    # Step 4: Save
    print(f"\n  [4/4] Saving to {output_csv.name}...")
    combined.to_csv(output_csv, index=False)
    file_size_mb = output_csv.stat().st_size / (1024 * 1024)
    print(f"    Saved: {file_size_mb:.2f} MB")

    return output_csv


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download AEMO NEM Operational Demand data.")
    parser.add_argument("--start-date", default=config.DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=config.DEFAULT_END_DATE)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR
    raw = out_dir / "raw"

    try:
        result_path = run(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=out_dir,
            raw_dir=raw,
            verbose=args.verbose,
        )
        print(f"\nDone. Output: {result_path}")
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
