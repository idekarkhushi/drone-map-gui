import csv

def load_csv_waypoints(file_path):
    points = []

    with open(file_path, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            points.append((float(row[0]), float(row[1])))

    return points