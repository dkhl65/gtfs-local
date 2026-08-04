#!/usr/bin/env python3
import sys
import zipfile
import requests
import pandas as pd
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, text

AGENCIES = {
    "miway": "https://www.miapp.ca/GTFS/google_transit.zip",
    "ttc": "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/b811ead4-6eaf-4adb-8408-d389fb5a069c/resource/c920e221-7a1c-488b-8c5b-6d8cd4e85eaf/download/Complete%20GTFS.zip",
    "gotransit": "https://assets.metrolinx.com/raw/upload/Documents/Metrolinx/Open%20Data/GO-GTFS.zip",
}
GTFS_DATA_DIR = "gtfs_data"
DOWNLOAD_DIR = "downloads"

def create_query_indexes(engine, table_names):
    """Create query indexes for common timetable lookups."""
    table_set = set(table_names)
    statements = []

    if "trips" in table_set:
        statements.append(
            """
            CREATE INDEX IF NOT EXISTS idx_trips_route_service_dir_trip
            ON trips(route_id, service_id, direction_id, trip_id)
            """
        )
    if "stop_times" in table_set:
        statements.append(
            """
            CREATE INDEX IF NOT EXISTS idx_stop_times_trip_seq_arr
            ON stop_times(trip_id, stop_sequence, arrival_time)
            """
        )
    if "calendar_dates" in table_set:
        statements.append(
            """
            CREATE INDEX IF NOT EXISTS idx_calendar_dates_date_exception_service
            ON calendar_dates(date, exception_type, service_id)
            """
        )
    if "stops" in table_set:
        statements.append(
            """
            CREATE INDEX IF NOT EXISTS idx_stops_stop_id
            ON stops(stop_id)
            """
        )

    if not statements:
        return 0

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    return len(statements)

def setup_directories():
    base = Path(GTFS_DATA_DIR)
    downloads = base / DOWNLOAD_DIR
    base.mkdir(exist_ok=True)
    downloads.mkdir(exist_ok=True)
    return base, downloads

def download_gtfs(agency_name: str, url: str, download_dir: Path) -> Optional[Path]:
    zip_path = download_dir / f"{agency_name}.zip"

    print(f"  Downloading {agency_name} from {url}...")

    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"    \N{CHECK MARK} Saved to {zip_path}")
        return zip_path

    except requests.RequestException as e:
        print(f"    \N{BALLOT X} Failed to download {agency_name}: {e}", file=sys.stderr)
        return None


def extract_gtfs(agency_name: str, zip_path: Path, base_dir: Path) -> Optional[Path]:
    extract_dir = base_dir / agency_name

    if extract_dir.exists():
        import shutil
        shutil.rmtree(extract_dir)

    extract_dir.mkdir(exist_ok=True)

    print(f"  Extracting {agency_name}...")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        txt_files = list(extract_dir.glob("*.txt"))
        print(f"    \N{CHECK MARK} Extracted {len(txt_files)} .txt files to {extract_dir}")
        return extract_dir

    except zipfile.BadZipFile as e:
        print(f"    \N{BALLOT X} Bad zip file for {agency_name}: {e}", file=sys.stderr)
        return None

def build_sqlite(agency_name: str, extract_dir: Path) -> Optional[Path]:
    db_path = extract_dir / f"{agency_name}.db"
    txt_files = sorted(extract_dir.glob("*.txt"))

    if not txt_files:
        print(f"    \N{BALLOT X} No .txt files found in {extract_dir}", file=sys.stderr)
        return None

    print(f"  Building SQLite database for {agency_name}...")

    engine = create_engine(f"sqlite:///{db_path}")
    table_count = 0
    for txt_file in txt_files:
        pd.read_csv(txt_file).to_sql(txt_file.stem, con=engine, index=False)
        table_count += 1

    indexed = create_query_indexes(engine, [txt_file.stem for txt_file in txt_files])

    print(f"    \N{CHECK MARK} Created {table_count} table(s) in {db_path}")
    if indexed:
        print(f"    \N{CHECK MARK} Created {indexed} index(es) for query performance")
    return db_path

def cleanup_zips(download_dir: Path):
    zips = list(download_dir.glob("*.zip"))
    for z in zips:
        z.unlink()
    if zips:
        print(f"  Cleaned up {len(zips)} zip file(s)")

def main():
    print("=" * 60)
    print("GTFS Downloader & Database Builder")
    print("=" * 60)

    base_dir, download_dir = setup_directories()

    for agency_name, url in AGENCIES.items():
        print(f"\nProcessing: {agency_name}")
        print("-" * 40)

        zip_path = download_gtfs(agency_name, url, download_dir)
        if not zip_path:
            continue

        extract_dir = extract_gtfs(agency_name, zip_path, base_dir)
        if not extract_dir:
            continue

        build_sqlite(agency_name, extract_dir)

    print(f"\n{'=' * 60}")
    cleanup_zips(download_dir)

    print("Done! \N{CHECK MARK}")
    print(f"\nData location: {Path(GTFS_DATA_DIR).resolve()}")

if __name__ == "__main__":
    main()
