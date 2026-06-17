from sqlalchemy import create_engine
from datetime import datetime
import pandas as pd
import sys
from pathlib import Path

def normalize_route_ids(route_id):
    """Normalize route input to a list of route ids."""
    return route_id if isinstance(route_id, list) else [route_id]

def get_db_engine(agency_name: str):
    """Get SQLAlchemy engine for a specific transit agency."""
    agency_name = agency_name.lower()
    db_path = Path(__file__).parent / "gtfs_data" / agency_name / f"{agency_name}.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found for agency '{agency_name}' at {db_path}")
    return create_engine(f"sqlite:///{db_path}")

def get_available_routes(agency_name: str):
    """Get list of available routes for an agency."""
    engine = get_db_engine(agency_name)
    routes_df = pd.read_sql(
        """
            SELECT DISTINCT
                route_id,
                route_short_name,
                route_long_name
            FROM routes
            ORDER BY CAST(route_short_name AS INTEGER)
        """,
        con=engine
    )
    return routes_df.to_dict("records")

def get_direction_labels(agency_name: str, route_id):
    """Build route-aware direction labels from trip headsigns."""
    engine = get_db_engine(agency_name)
    route_ids = normalize_route_ids(route_id)

    route_placeholders = ",".join([f":route_id_{i}" for i in range(len(route_ids))])
    params = {f"route_id_{i}": rid for i, rid in enumerate(route_ids)}

    labels_df = pd.read_sql_query(
        f"""
            SELECT
                direction_id,
                trip_headsign,
                COUNT(*) AS trip_count
            FROM trips
            WHERE route_id IN ({route_placeholders})
            AND direction_id IN (0, 1)
            AND trip_headsign IS NOT NULL
            AND TRIM(trip_headsign) <> ''
            GROUP BY direction_id, trip_headsign
            ORDER BY direction_id, trip_count DESC, trip_headsign
        """,
        con=engine,
        params=params
    )

    labels = {}
    for direction_id in (0, 1):
        headsigns = labels_df[labels_df["direction_id"] == direction_id]["trip_headsign"].tolist()

        if not headsigns:
            labels[direction_id] = f"Direction {direction_id}"
            continue

        if len(headsigns) == 1:
            labels[direction_id] = headsigns[0]
            continue

        labels[direction_id] = f"{headsigns[0]} (+{len(headsigns) - 1} variants)"

    return labels

def generate_timetable(agency_name: str, trip_date: str, route_id, direction_id: int):
    """Generate CSV-format timetable for a route on a specific date."""
    engine = get_db_engine(agency_name)

    service_id_df = pd.read_sql_query(
        "SELECT service_id FROM calendar_dates WHERE date = :date",
        con=engine,
        params={"date": trip_date}
    )
    service_ids = list(service_id_df["service_id"])

    route_ids = normalize_route_ids(route_id)
    route_placeholders = ",".join([f":route_id_{i}" for i in range(len(route_ids))])
    service_placeholders = ",".join([f":service_id_{i}" for i in range(len(service_ids))])

    params_trip_ids = {"direction_id": direction_id}
    for i, rid in enumerate(route_ids):
        params_trip_ids[f"route_id_{i}"] = rid
    for i, sid in enumerate(service_ids):
        params_trip_ids[f"service_id_{i}"] = sid

    trip_ids_df = pd.read_sql(
        f"""
            SELECT DISTINCT t.trip_id
            FROM trips AS t
            JOIN stop_times AS st ON t.trip_id = st.trip_id
            WHERE t.route_id IN ({route_placeholders})
            AND t.service_id IN ({service_placeholders})
            AND t.direction_id = :direction_id
            ORDER BY st.arrival_time
        """,
        con=engine,
        params=params_trip_ids
    )
    trip_ids = list(trip_ids_df["trip_id"])

    trip_id_placeholders = ",".join([f":trip_id_{i}" for i in range(len(trip_ids))])
    trip_id_params = {f"trip_id_{i}": tid for i, tid in enumerate(trip_ids)}
    all_stops_df = pd.read_sql(
        f"""
            SELECT
                t.trip_id,
                t.trip_headsign,
                st.arrival_time,
                s.stop_name,
                s.stop_id,
                st.stop_sequence
            FROM trips AS t
            JOIN stop_times AS st ON t.trip_id = st.trip_id
            JOIN stops AS s ON st.stop_id = s.stop_id
            JOIN routes AS r ON t.route_id = r.route_id
            WHERE t.service_id IN ({service_placeholders})
            AND t.direction_id = :direction_id
            AND t.trip_id IN ({trip_id_placeholders})
            ORDER BY st.stop_sequence, st.arrival_time
        """,
        con=engine,
        params={**params_trip_ids, **trip_id_params}
    )
    trips_by_id = {tid: group.reset_index(drop=True) for tid, group in all_stops_df.groupby("trip_id")}
    trips = [trips_by_id[tid] for tid in trip_ids]

    stops = {}
    sequence = []
    csv_header = "Stop"
    for trip in trips:
        inserter = []
        stop_occurrences = {}
        route_full_name = trip["trip_headsign"][0]
        direction_index = route_full_name.find(" ") + 1
        if route_full_name[direction_index] in ("N", "E", "W", "S"):
            route_number = route_full_name[:direction_index + 1]
        else:
            route_number = route_full_name[:direction_index - 1]
        csv_header += f",{route_number}"
        for _, row in trip.iterrows():
            stop_base = f"{row['stop_id']} {row['stop_name']}"
            stop_occurrences[stop_base] = stop_occurrences.get(stop_base, 0) + 1
            occurrence = stop_occurrences[stop_base]
            stop = f"{occurrence}|{stop_base}"
            if stop in stops:
                stops[stop][row["trip_id"]] = row["arrival_time"][:5]
                if len(inserter) > 0:
                    try:
                        k = sequence.index(stop)
                        sequence = sequence[:k] + inserter + sequence[k:]
                        inserter = []
                    except ValueError:
                        sequence = sequence + inserter
                        inserter = []
            else:
                stops[stop] = {row["trip_id"]: row["arrival_time"][:5]}
                inserter.append(stop)
        sequence = sequence + inserter
    csv_string = csv_header + "\n"

    for stop in sequence:
        _, stop_label = stop.split("|", 1)
        csv_row = stop_label[stop_label.find(" ")+1:]
        for trip_id in trip_ids:
            if trip_id in stops[stop]:
                csv_row += f",{stops[stop][trip_id]}"
            else:
                csv_row += ",\N{DOWNWARDS ARROW}"
        csv_string += csv_row + "\n"

    return csv_string

if __name__ == "__main__":
    agency_name = "miway"
    trip_date = datetime.now().strftime("%Y%m%d")
    route_id = 4
    direction_id = 0

    if len(sys.argv) > 1:
        agency_name = str(sys.argv[1]).lower()
        trip_date = str(sys.argv[2])
        route_id = str(sys.argv[3]).split(",")
        direction_input = str(sys.argv[4])
        if direction_input in ["e", "E", "n", "N", "0"]:
            direction_id = 0
        else:
            direction_id = 1

    print(generate_timetable(agency_name, trip_date, route_id, direction_id))
