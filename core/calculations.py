import math

def calculate_distance(start, end):
    r = 6371000

    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return r * c


def get_angle(start, end):
    dx = end[1] - start[1]
    dy = end[0] - start[0]
    angle = math.degrees(math.atan2(dy, dx))
    return -angle