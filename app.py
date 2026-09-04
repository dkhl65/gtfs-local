from flask import Flask, render_template, request, send_file, jsonify
import datetime as dt
from io import BytesIO, StringIO
import csv
from gtfs_data import (
    generate_timetable,
    get_available_routes,
    get_direction_labels,
    get_direction_headsign_variants,
    get_available_directions,
)

app = Flask(__name__)

AGENCIES = {
    "miway": "MiWay",
    "ttc": "TTC",
    "gotransit": "GO Transit"
}

DEFAULT_DIRECTIONS = {
    0: "Direction 0",
    1: "Direction 1"
}

NO_SERVICE_MARKERS = {"\N{DOWNWARDS ARROW}", "N/A", ""}

def get_direction_label_for_display(agency, route, direction_id):
    """Get route-aware direction text for rendered timetable pages."""
    route_id = parse_route_ids(route)
    direction_variants = get_direction_headsign_variants(agency, route_id)
    headsigns = direction_variants.get(direction_id, [])
    if headsigns:
        return "\n".join(headsigns)

    direction_labels = get_direction_labels(agency, route_id)
    return direction_labels.get(direction_id, f"Direction {direction_id}")

def parse_route_ids(route_value):
    """Parse route query param into a string or list of strings."""
    route_ids = [r.strip() for r in route_value.split(",") if r.strip()]
    if len(route_ids) == 1:
        return route_ids[0]
    return route_ids

def parse_csv_to_table(csv_string):
    """Convert CSV string to table data (list of dicts)."""
    csv_stream = StringIO(csv_string)
    csv_reader = csv.reader(csv_stream)
    rows = list(csv_reader)
    if not rows:
        return [], []

    headers = rows[0]
    data_rows = rows[1:]
    return headers, data_rows

def parse_time_to_minutes(value):
    """Parse HH:MM (including >24h) to minutes from midnight."""
    if not value:
        return None

    raw = value.strip()
    if raw in NO_SERVICE_MARKERS:
        return None

    parts = raw.split(":")
    if len(parts) != 2:
        return None

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None

    if hours < 0 or minutes < 0 or minutes > 59:
        return None

    return (hours * 60) + minutes

def normalize_trip_times(departure, arrival):
    """Normalize trip times across midnight to ensure arrival >= departure."""
    dep = departure
    arr = arrival
    while arr < dep:
        arr += 24 * 60
    return dep, arr

def pick_trip_time(rows, col_index, row_start, row_end, pick_earliest):
    """Find first/last non-empty time in a row span for a trip column."""
    row_range = list(range(row_start, row_end + 1))
    indices = row_range if pick_earliest else list(reversed(row_range))

    for row_idx in indices:
        minute_value = parse_time_to_minutes(rows[row_idx][col_index + 1])
        if minute_value is not None:
            return minute_value
    return None

def apply_download_filters(headers, rows, request_args):
    """Apply the same stop/time filters used on the timetable page to CSV data."""
    if not headers or not rows:
        return headers, rows

    trip_column_count = max(0, len(headers) - 1)
    if trip_column_count == 0:
        return headers, rows

    def parse_index_arg(name):
        raw = request_args.get(name)
        if raw is None or raw == "":
            return None
        try:
            parsed = int(raw)
        except ValueError:
            return None
        return parsed if 0 <= parsed < len(rows) else None

    start_index = parse_index_arg("start_index")
    end_index = parse_index_arg("end_index")

    all_minutes = []
    for row in rows:
        for cell in row[1:]:
            minute = parse_time_to_minutes(cell)
            if minute is not None:
                all_minutes.append(minute)

    min_time = min(all_minutes) if all_minutes else 0
    max_time = max(all_minutes) if all_minutes else (24 * 60) - 1

    start_minutes = parse_time_to_minutes(request_args.get("start_time"))
    if start_minutes is None:
        start_minutes = min_time

    end_minutes = parse_time_to_minutes(request_args.get("end_time"))
    if end_minutes is None:
        end_minutes = max_time

    if start_minutes > end_minutes:
        start_minutes = end_minutes

    omit_intermediate = request_args.get("omit_intermediate", "").lower() in {"1", "true", "yes", "on"}

    visible_start = start_index if start_index is not None else 0
    visible_end = end_index if end_index is not None else len(rows) - 1

    visible_columns = [False] * trip_column_count

    for col in range(trip_column_count):
        selected_start_time = parse_time_to_minutes(rows[start_index][col + 1]) if start_index is not None else None
        selected_end_time = parse_time_to_minutes(rows[end_index][col + 1]) if end_index is not None else None

        if start_index is not None and selected_start_time is None:
            continue
        if end_index is not None and selected_end_time is None:
            continue

        departure = selected_start_time if selected_start_time is not None else pick_trip_time(rows, col, visible_start, visible_end, True)
        arrival = selected_end_time if selected_end_time is not None else pick_trip_time(rows, col, visible_start, visible_end, False)

        if departure is None or arrival is None:
            continue

        normalized_departure, normalized_arrival = normalize_trip_times(departure, arrival)
        visible_columns[col] = (
            normalized_departure >= start_minutes
            and normalized_arrival <= end_minutes
            and normalized_arrival >= normalized_departure
        )

    is_filtering_active = (
        start_index is not None
        or end_index is not None
        or start_minutes > min_time
        or end_minutes < max_time
        or omit_intermediate
    )

    default_column_order = list(range(trip_column_count))
    if is_filtering_active:
        def sort_key(col_index):
            start_time = pick_trip_time(rows, col_index, visible_start, visible_end, True)
            if start_time is None:
                return (1, 0, col_index)
            return (0, start_time, col_index)

        column_order = sorted(default_column_order, key=sort_key)
    else:
        column_order = default_column_order

    boundary_only = (
        omit_intermediate
        and start_index is not None
        and end_index is not None
        and start_index < end_index
    )

    shown_rows = []
    for row_idx in range(visible_start, visible_end + 1):
        if boundary_only and row_idx not in (visible_start, visible_end):
            continue
        shown_rows.append(row_idx)

    shown_columns = [col for col in column_order if visible_columns[col]]

    filtered_headers = [headers[0]] + [headers[col + 1] for col in shown_columns]
    filtered_rows = []
    for row_idx in shown_rows:
        base_row = rows[row_idx]
        filtered_rows.append([base_row[0]] + [base_row[col + 1] for col in shown_columns])

    return filtered_headers, filtered_rows

def table_to_csv_string(headers, rows):
    """Convert table headers/rows back into CSV text."""
    csv_stream = StringIO()
    csv_writer = csv.writer(csv_stream)
    csv_writer.writerow(headers)
    for row in rows:
        csv_writer.writerow(row)
    return csv_stream.getvalue()

def load_routes_by_agency():
    """Load routes for each configured agency."""
    routes_by_agency = {}
    for agency_code in AGENCIES:
        try:
            routes_by_agency[agency_code] = get_available_routes(agency_code)
        except Exception:
            routes_by_agency[agency_code] = []
    return routes_by_agency

def render_form(error=None, status_code=200):
    """Render the search form with required context."""
    response = render_template(
        "form.html",
        agencies=AGENCIES,
        routes_by_agency=load_routes_by_agency(),
        today=dt.datetime.now().strftime("%Y-%m-%d"),
        error=error
    )
    if status_code == 200:
        return response
    return response, status_code

@app.route("/")
def index():
    """Show the form to select agency, route, direction, and date."""
    return render_form()

@app.route("/transfers")
def transfers():
    """Show the transfers page."""
    response = render_template(
        "transfers.html",
        agencies=AGENCIES,
        routes_by_agency=load_routes_by_agency(),
        today=dt.datetime.now().strftime("%Y-%m-%d")
    )
    return response

@app.route("/direction-options")
def direction_options():
    """Return route-aware direction labels for the selected agency and route(s)."""
    agency = request.args.get("agency", "").lower()
    route = request.args.get("route", "")

    if not agency or not route:
        return jsonify({"options": [
            {"value": "0", "label": DEFAULT_DIRECTIONS[0]},
            {"value": "1", "label": DEFAULT_DIRECTIONS[1]}
        ]})

    try:
        route_id = parse_route_ids(route)
        available_directions = get_available_directions(agency, route_id)
        if not available_directions:
            available_directions = [0, 1]

        direction_labels = get_direction_labels(agency, route_id)
        return jsonify({"options": [
            {
                "value": str(direction_id),
                "label": direction_labels.get(direction_id, DEFAULT_DIRECTIONS[direction_id])
            }
            for direction_id in available_directions
        ]})
    except Exception:
        return jsonify({"options": [
            {"value": "0", "label": DEFAULT_DIRECTIONS[0]},
            {"value": "1", "label": DEFAULT_DIRECTIONS[1]}
        ]})

@app.route("/stop-options")
def stop_options():
    """Return stops in the same order as the selected route timetable."""
    agency = request.args.get("agency", "").lower()
    route = request.args.get("route", "")
    direction = request.args.get("direction", "")
    date_str = request.args.get("date", "")

    if agency not in AGENCIES or not route or not direction or not date_str:
        return jsonify({"options": []})

    try:
        csv_string = generate_timetable(
            agency,
            date_str.replace("-", ""),
            parse_route_ids(route),
            int(direction)
        )
        _, rows = parse_csv_to_table(csv_string)
        return jsonify({"options": [
            {"value": str(index), "label": row[0]}
            for index, row in enumerate(rows)
            if row
        ]})
    except Exception:
        return jsonify({"options": []})

@app.route("/timetable")
def timetable():
    """Display timetable based on query parameters."""
    agency = request.args.get("agency", "").lower()
    if agency not in AGENCIES:
        return render_form(error="Unknown transit agency", status_code=400)
    route = request.args.get("route", "")
    secondary_route = request.args.get("secondary-route", "")
    direction = request.args.get("direction", "")
    date_str = request.args.get("date", "")

    if not all([agency, route, direction, date_str]):
        return render_form(error="Please select all fields", status_code=400)

    try:
        trip_date = date_str.replace("-", "")
        direction_id = int(direction)

        if secondary_route:
            route += f",{secondary_route}"
        route_id = parse_route_ids(route)
        available_directions = get_available_directions(agency, route_id)
        if not available_directions:
            available_directions = [0, 1]

        if direction_id not in available_directions:
            return render_form(
                error=f"Direction {direction_id} is not available for {AGENCIES[agency]} route {route}",
                status_code=400
            )

        csv_string = generate_timetable(agency, trip_date, route_id, direction_id)

        if not csv_string:
            return render_form(
                error=f"No timetable data found for {AGENCIES[agency]} route {route} on {date_str}",
                status_code=400
            )

        headers, rows = parse_csv_to_table(csv_string)

        show_switch_direction = len(available_directions) > 1
        switch_direction_id = None
        switch_direction_label = None
        if show_switch_direction:
            switch_direction_id = next(d for d in available_directions if d != direction_id)
            switch_direction_label = get_direction_label_for_display(agency, route, switch_direction_id)

        date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
        date_full = date_obj.strftime("%A, %B %d, %Y")

        return render_template(
            "timetable.html",
            agency=AGENCIES.get(agency, agency),
            route=route,
            direction=get_direction_label_for_display(agency, route, direction_id),
            date=date_full,
            headers=headers,
            rows=rows,
            agency_code=agency,
            route_param=route,
            direction_param=direction,
            show_switch_direction=show_switch_direction,
            switch_direction_param=str(switch_direction_id) if switch_direction_id is not None else "",
            switch_direction_label=switch_direction_label,
            date_param=date_str
        )

    except Exception as e:
        return render_form(error=f"Error generating timetable: {str(e)}", status_code=500)

@app.route("/download")
def download():
    """Download timetable as CSV."""
    agency = request.args.get("agency", "").lower()
    route = request.args.get("route", "")
    direction = request.args.get("direction", "")
    date_str = request.args.get("date", "")

    if not all([agency, route, direction, date_str]):
        return "Missing parameters", 400

    try:
        trip_date = date_str.replace("-", "")
        direction_id = int(direction)
        route_id = parse_route_ids(route)

        csv_string = generate_timetable(agency, trip_date, route_id, direction_id)
        headers, rows = parse_csv_to_table(csv_string)
        filtered_headers, filtered_rows = apply_download_filters(headers, rows, request.args)
        csv_string = table_to_csv_string(filtered_headers, filtered_rows)
        filename = f"{agency}_{route}_{direction}_{date_str.replace('-', '')}.csv"

        return send_file(
            BytesIO(csv_string.encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return f"Error downloading timetable: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)
