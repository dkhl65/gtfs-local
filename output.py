from sqlalchemy import create_engine
from datetime import datetime
import pandas as pd
import sys

def miway_csv_string(engine, trip_date, route_id, direction_id):
    service_id = pd.read_sql_query(f"SELECT service_id FROM calendar_dates WHERE date = '{trip_date}'", con=engine)["service_id"]

    route_query = "t.route_id = "
    if isinstance(route_id, list):
        for i, r in enumerate(route_id):
            if i == 0:
                route_query += str(r)
            else:
                route_query += f" OR t.route_id = {r}"
    else:
        route_query += str(route_id)

    service_query = "t.service_id = "
    for i, s in enumerate(list(service_id)):
        if i == 0:
            service_query += f"'{s}'"
        else:
            service_query += f" OR t.service_id = '{s}'"

    trip_ids_df = pd.read_sql(
        f"""
            SELECT DISTINCT t.trip_id
            FROM trips AS t
            JOIN stop_times AS st ON t.trip_id = st.trip_id
            WHERE ({route_query})
            AND ({service_query})
            AND t.direction_id = {direction_id}
            ORDER BY st.arrival_time
        """,
        con=engine
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
                    AND ({service_query})
                    AND t.direction_id = {direction_id}
                    AND t.trip_id = '{trip_id}'
                    ORDER BY st.stop_sequence, st.arrival_time
                """,
                con=engine
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
            stop = f"{row['stop_id']} {row['stop_name']}"
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
                csv_row += ",\N{DOWNWARDS ARROW}"
        csv_string += csv_row + "\n"

    return csv_string

if __name__ == "__main__":
    engine = create_engine("sqlite:///gtfs_data/miway/miway.db")
    trip_date = datetime.now().strftime("%Y%m%d")
    route_id = 4
    direction_id = 0 # E/N 0, W/S 1
    if len(sys.argv) > 1:
        trip_date = str(sys.argv[1])
        route_id = str(sys.argv[2]).split(",")
        direction_input = str(sys.argv[3])
        if direction_input in ["e", "E", "n", "N", "0"]:
            direction_id = 0
        else:
            direction_id = 1
    print(miway_csv_string(engine, trip_date, route_id, direction_id))
