"""Metres; east=0°, counterclockwise bearings."""
import math

ARENA_RADIUS = 1800.0

def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360

def angle_delta(a, b):
    return (a - b + 180) % 360 - 180

def covered(source, point):
    if distance(source.position, point) > source.radius:
        return False
    # 假设 A4：重合点视为覆盖；浮点角边界容差为 1e-10 度。
    return (source.direction_deg is None or point == source.position or
            abs(angle_delta(bearing(source.position, point), source.direction_deg)) <= 90 + 1e-10)

def advance(point, angle, length):
    theta = math.radians(angle)
    return (point[0] + length * math.cos(theta), point[1] + length * math.sin(theta))
