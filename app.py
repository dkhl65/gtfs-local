from flask import Flask, render_template, request, send_file
from datetime import datetime
import io
from output import generate_timetable, get_available_routes

app = Flask(__name__)

AGENCIES = {
    "miway": "Miway",
    "ttc": "TTC",
    "gotransit": "GO Transit"
}

DIRECTIONS = {
    0: "North/East",
    1: "South/West"
}

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

@app.route("/")
def index():
    """Show the form to select agency, route, direction, and date."""
    routes_by_agency = {}
    try:
        for agency_code in AGENCIES.keys():
            try:
                routes = get_available_routes(agency_code)
                routes_by_agency[agency_code] = routes
            except Exception as e:
                routes_by_agency[agency_code] = []
    except Exception as e:
        pass

    today = datetime.now().strftime("%Y-%m-%d")
    return render_template(
        "form.html",
        agencies=AGENCIES,
        routes_by_agency=routes_by_agency,
        directions=DIRECTIONS,
        today=today
    )

@app.route("/timetable")
def timetable():
    """Display timetable based on query parameters."""
    agency = request.args.get("agency", "").lower()
    route = request.args.get("route", "")
    direction = request.args.get("direction", "")
    date_str = request.args.get("date", "")

    if not all([agency, route, direction, date_str]):
        return render_template(
            "form.html",
            agencies=AGENCIES,
            error="Please select all fields"
        ), 400

    try:
        trip_date = date_str.replace("-", "")
        direction_id = int(direction)

        route_id = [int(r.strip()) for r in route.split(",")]
        if len(route_id) == 1:
            route_id = route_id[0]

        csv_string = generate_timetable(agency, trip_date, route_id, direction_id)

        if not csv_string:
            return render_template(
                "form.html",
                agencies=AGENCIES,
                error=f"No timetable data found for {AGENCIES[agency]} route {route} on {date_str}"
            ), 400

        headers, rows = parse_csv_to_table(csv_string)

        return render_template(
            "timetable.html",
            agency=AGENCIES.get(agency, agency),
            route=route,
            direction=DIRECTIONS.get(direction_id, direction),
            date=date_str,
            headers=headers,
            rows=rows,
            agency_code=agency,
            route_param=route,
            direction_param=direction,
            date_param=date_str
        )

    except Exception as e:
        return render_template(
            "form.html",
            agencies=AGENCIES,
            error=f"Error generating timetable: {str(e)}"
        ), 500

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
        route_id = [int(r.strip()) for r in route.split(",")]
        if len(route_id) == 1:
            route_id = route_id[0]

        csv_string = generate_timetable(agency, trip_date, route_id, direction_id)
        filename = f"{agency}_{route}_{direction}_{date_str.replace('-', '')}.csv"

        return send_file(
            io.BytesIO(csv_string.encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return f"Error downloading timetable: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)
