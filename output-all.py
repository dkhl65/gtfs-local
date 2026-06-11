from sqlalchemy import create_engine
from output import miway_csv_string
import pandas as pd

if __name__ == "__main__":
    engine = create_engine("sqlite:///gtfs_data/miway/miway.db")
    routes = list(pd.read_sql_query(f"SELECT route_id FROM routes", con=engine)["route_id"])
    dates = ["20260613", "20260614", "20260615"]
    day_names = ["Saturday", "Sunday", "Weekday"]
    for route in routes:
        for i, date in enumerate(dates):
            for direction in range(2):
                csv_string = miway_csv_string(engine, date, route, direction)
                first_comma = csv_string.find(",")
                if first_comma < 0:
                    continue
                second_comma = csv_string.find(",", first_comma + 1)
                first_newline = csv_string.find("\n")
                file_name = f"{csv_string[first_comma + 1:min(second_comma, first_newline)].replace(' ', '')}-{day_names[i]}.csv"
                try:
                    with open(f"gtfs_data/miway/timetables/{file_name}", "w") as f:
                        f.write(csv_string)
                    print(f"Created {file_name}")
                except:
                    print(f"Skipping {file_name}")
