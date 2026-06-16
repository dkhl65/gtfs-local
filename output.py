from sqlalchemy import create_engine
from datetime import datetime
import pandas as pd
import sys
from pathlib import Path

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
    routes_df = pd.read_sql("SELECT DISTINCT route_id, route_short_name FROM routes ORDER BY CAST(route_short_name AS INTEGER)", con=engine)
    return routes_df.to_dict('records')

def generate_timetable(agency_name: str, trip_date: str, route_id, direction_id: int):
    """Generate CSV-format timetable for a route on a specific date."""
    engine = get_db_engine(agency_name)

    # Get service IDs for the given date using parameterized query
    service_id_df = pd.read_sql_query(
        "SELECT service_id FROM calendar_dates WHERE date = :date",
        con=engine,
        params={"date": trip_date}
    )
    service_ids = list(service_id_df["service_id"])

    # Normalize route_id to a list
    route_ids = route_id if isinstance(route_id, list) else [route_id]

    # Build named parameters for trip IDs query
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

    trips = []
    for trip_id in trip_ids:
        trips.append(
            pd.read_sql(
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
                    AND t.trip_id = :trip_id
                    ORDER BY st.stop_sequence, st.arrival_time
                """,
                con=engine,
                params={**params_trip_ids, "trip_id": trip_id}
            )
        )

    stops = {}
    sequence = []
    csv_header = "Stop"
    for trip in trips:
        inserter = []
        route_full_name = trip["trip_headsign"][0]
        direction_index = route_full_name.find(" ") + 1
        if route_full_name[direction_index] in ("N", "E", "W", "S"):
            route_number = route_full_name[:direction_index + 1]
        else:
            route_number = route_full_name[:direction_index - 1]
        csv_header += f",{route_number}"
        for _, row in trip.iterrows():
            stop = f"{row['stop_id']} {row['stop_name']}" #{row['stop_sequence']}-
            if stop in stops:
                stops[stop][row["trip_id"]] = row["arrival_time"][:5]
                if len(inserter) > 0:
                    try:
                        k = sequence.index(stop)
                        sequence = sequence[:k] + inserter + sequence[k:]
                        inserter = []
                    except:
                        print("Duplicate stop, need to handle manually")
                        return ""
            else:
                stops[stop] = {row["trip_id"]: row["arrival_time"][:5]}
                inserter.append(stop)
        sequence = sequence + inserter
    csv_string = csv_header + "\n"

    for stop in sequence:
        csv_row = stop[stop.find(" ")+1:]
        for trip_id in trip_ids:
            if trip_id in stops[stop]:
                csv_row += f",{stops[stop][trip_id]}"
            else:
                csv_row += ",\u2193"
        csv_string += csv_row + "\n"

    return csv_string

if __name__ == "__main__":
    agency_name = "miway"
    trip_date = datetime.now().strftime("%Y%m%d")
    route_id = 4
    direction_id = 0 # E/N 0, W/S 1

    if len(sys.argv) > 1:
        agency_name = str(sys.argv[1]).lower()
        trip_date = str(sys.argv[2])
        route_id = str(sys.argv[3]).split(',')
        direction_input = str(sys.argv[4])
        if direction_input in ['e', 'E', 'n', 'N', '0']:
            direction_id = 0
        else:
            direction_id = 1

    print(generate_timetable(agency_name, trip_date, route_id, direction_id))
