"""Metres; east=0 degrees, counterclockwise bearings."""
import math

def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360

def angle_delta(a, b):
    return (a - b + 180) % 360 - 180

def advance(point, angle, length):
    theta = math.radians(angle)
    return (point[0] + length * math.cos(theta), point[1] + length * math.sin(theta))
