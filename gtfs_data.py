from sqlalchemy import create_engine, inspect
import datetime as dt
import pandas as pd
import sys
from pathlib import Path
from collections import defaultdict, deque
from functools import cmp_to_key

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

def get_direction_headsign_variants(agency_name: str, route_id):
    """Return ordered headsign variants for each direction id."""
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

    return {
        direction_id: labels_df[labels_df["direction_id"] == direction_id]["trip_headsign"].tolist()
        for direction_id in (0, 1)
    }

def get_direction_labels(agency_name: str, route_id):
    """Build route-aware direction labels from trip headsigns."""
    variants = get_direction_headsign_variants(agency_name, route_id)

    labels = {}
    for direction_id in (0, 1):
        headsigns = variants[direction_id]

        if not headsigns:
            labels[direction_id] = f"Direction {direction_id}"
            continue

        if len(headsigns) == 1:
            labels[direction_id] = headsigns[0]
            continue

        labels[direction_id] = f"{headsigns[0]} (+{len(headsigns) - 1} variants)"

    return labels

def get_available_directions(agency_name: str, route_id):
    """Return available direction ids for one or more route ids."""
    engine = get_db_engine(agency_name)
    route_ids = normalize_route_ids(route_id)

    route_placeholders = ",".join([f":route_id_{i}" for i in range(len(route_ids))])
    params = {f"route_id_{i}": rid for i, rid in enumerate(route_ids)}

    directions_df = pd.read_sql_query(
        f"""
            SELECT DISTINCT direction_id
            FROM trips
            WHERE route_id IN ({route_placeholders})
            AND direction_id IN (0, 1)
            ORDER BY direction_id
        """,
        con=engine,
        params=params
    )

    return directions_df["direction_id"].astype(int).tolist()

def table_exists(engine, table_name):
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def sort_trip_ids_by_row_times(trip_ids, stops, sequence):
    """Order trip ids so times progress left-to-right across stop rows when possible."""

    def to_minutes(hhmm):
        hour, minute = hhmm.split(":")
        return int(hour) * 60 + int(minute)

    if len(trip_ids) <= 1:
        return trip_ids

    graph = defaultdict(set)
    indegree = {tid: 0 for tid in trip_ids}
    first_seen_minutes = {}
    original_index = {tid: i for i, tid in enumerate(trip_ids)}
    pairwise_wins = defaultdict(lambda: defaultdict(int))

    for stop in sequence:
        timed = []
        for tid in trip_ids:
            value = stops[stop].get(tid)
            if value:
                minutes = to_minutes(value)
                timed.append((minutes, tid))
                if tid not in first_seen_minutes:
                    first_seen_minutes[tid] = minutes

        timed.sort()
        for i in range(len(timed)):
            for j in range(i + 1, len(timed)):
                left_minutes, left_tid = timed[i]
                right_minutes, right_tid = timed[j]
                if left_minutes < right_minutes:
                    pairwise_wins[left_tid][right_tid] += 1

        for i in range(len(timed) - 1):
            left_tid = timed[i][1]
            right_tid = timed[i + 1][1]
            if right_tid not in graph[left_tid]:
                graph[left_tid].add(right_tid)
                indegree[right_tid] += 1

    queue = deque(
        sorted(
            [tid for tid in trip_ids if indegree[tid] == 0],
            key=lambda tid: (first_seen_minutes.get(tid, float("inf")), original_index[tid])
        )
    )
    ordered = []

    while queue:
        tid = queue.popleft()
        ordered.append(tid)
        released = []
        for nxt in graph[tid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                released.append(nxt)
        for nxt in sorted(
            released,
            key=lambda t: (first_seen_minutes.get(t, float("inf")), original_index[t])
        ):
            queue.append(nxt)

    if len(ordered) == len(trip_ids):
        return ordered

    remaining = [tid for tid in trip_ids if tid not in ordered]
    wins_out = {tid: 0 for tid in trip_ids}
    wins_in = {tid: 0 for tid in trip_ids}
    for left_tid, targets in pairwise_wins.items():
        for right_tid, count in targets.items():
            wins_out[left_tid] += count
            wins_in[right_tid] += count

    def compare_trip_order(left_tid, right_tid):
        left_over_right = pairwise_wins[left_tid].get(right_tid, 0)
        right_over_left = pairwise_wins[right_tid].get(left_tid, 0)
        if left_over_right != right_over_left:
            return -1 if left_over_right > right_over_left else 1

        left_net = wins_out[left_tid] - wins_in[left_tid]
        right_net = wins_out[right_tid] - wins_in[right_tid]
        if left_net != right_net:
            return -1 if left_net > right_net else 1

        left_first = first_seen_minutes.get(left_tid, float("inf"))
        right_first = first_seen_minutes.get(right_tid, float("inf"))
        if left_first != right_first:
            return -1 if left_first < right_first else 1

        if original_index[left_tid] != original_index[right_tid]:
            return -1 if original_index[left_tid] < original_index[right_tid] else 1

        return 0

    ordered.extend(sorted(remaining, key=cmp_to_key(compare_trip_order)))
    return ordered

def generate_timetable(agency_name: str, trip_date: str, route_id, direction_id: int):
    """Generate CSV-format timetable for a route on a specific date."""
    engine = get_db_engine(agency_name)

    service_id_df1 = pd.DataFrame(columns=["service_id"])
    if table_exists(engine, "calendar"):
        no_service_id_df = pd.read_sql_query(
            "SELECT service_id FROM calendar_dates WHERE exception_type = 2 AND date = :date",
            con=engine,
            params={"date": trip_date}
        )
        if trip_date not in no_service_id_df["service_id"].values:
            day_of_week = dt.datetime.strptime(trip_date, "%Y%m%d").strftime("%A").lower()
            service_id_df1 = pd.read_sql_query(
                f"SELECT service_id FROM calendar WHERE {day_of_week} = 1 AND start_date <= :date AND end_date >= :date",
                con=engine,
                params={"date": trip_date}
            )
    service_id_df2 = pd.read_sql_query(
        "SELECT service_id FROM calendar_dates WHERE date = :date AND exception_type = 1",
        con=engine,
        params={"date": trip_date}
    )
    service_ids = list(service_id_df1["service_id"]) + list(service_id_df2["service_id"])

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
    for trip in trips:
        inserter = []
        stop_occurrences = {}
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
    ordered_trip_ids = sort_trip_ids_by_row_times(trip_ids, stops, sequence)

    csv_header = "Stop"
    for trip_id in ordered_trip_ids:
        trip = trips_by_id[trip_id]
        route_split_name = trip["trip_headsign"][0].split(" - ", 1)
        if len(route_split_name) >= 2 and route_split_name[0].strip() in ("North", "East", "West", "South"):
            route_full_name = route_split_name[1].strip()
        else:
            route_full_name = trip["trip_headsign"][0].strip()
        direction_index = route_full_name.find(" ") + 1
        if route_full_name[direction_index:direction_index + 2] in ("N ", "E ", "W ", "S "):
            route_number = route_full_name[:direction_index + 1]
        else:
            route_number = route_full_name[:direction_index - 1]
        csv_header += f",{route_number}"

    csv_string = csv_header + "\n"

    for stop in sequence:
        _, stop_label = stop.split("|", 1)
        csv_row = stop_label[stop_label.find(" ")+1:]
        for trip_id in ordered_trip_ids:
            if trip_id in stops[stop]:
                csv_row += f",{stops[stop][trip_id]}"
            else:
                csv_row += ",\N{DOWNWARDS ARROW}"
        csv_string += csv_row + "\n"

    return csv_string

if __name__ == "__main__":
    agency_name = "miway"
    trip_date = dt.datetime.now().strftime("%Y%m%d")
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
