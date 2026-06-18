from flask import Flask, render_template, request, send_file, jsonify
import datetime as dt
import io
from output import (
    generate_timetable,
    get_available_routes,
    get_direction_labels,
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

def get_direction_label_for_display(agency, route, direction_id):
    """Get route-aware direction text for rendered timetable pages."""
    route_id = parse_route_ids(route)
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
    lines = csv_string.strip().split("\n")
    if not lines:
        return [], []

    headers = lines[0].split(",")
    rows = []
    for line in lines[1:]:
        rows.append(line.split(","))

    return headers, rows

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

@app.route("/timetable")
def timetable():
    """Display timetable based on query parameters."""
    agency = request.args.get("agency", "").lower()
    route = request.args.get("route", "")
    direction = request.args.get("direction", "")
    date_str = request.args.get("date", "")

    if not all([agency, route, direction, date_str]):
        return render_form(error="Please select all fields", status_code=400)

    try:
        trip_date = date_str.replace("-", "")
        direction_id = int(direction)

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
        filename = f"{agency}_{route}_{direction}_{date_str.replace('-', '')}.csv"

        return send_file(
            io.BytesIO(csv_string.encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return f"Error downloading timetable: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)
