"""Distance and the speed test (spec sections 2, 4.3).

Both are whole-number arithmetic on purpose. A float square root and a division
each introduce a value that is only nearly right, and both of them decide
whether a sign-in is reported to a security team.

The distance is the integer square root: the largest whole number whose square
does not exceed dx^2 + dy^2. It floors, so a 14.76 km hop is reported as 14 -
which is what last quarter's signed-off export shows for the london/annexe pair.

The speed test is the cross-multiplied form of `km / hours > limit`. Written
that way a journey exactly at the limit is not impossible, and a zero-second gap
needs no special case: covering any ground in no time at all makes the left side
larger, which is precisely the thing the check exists to catch.
"""
from math import isqrt


def distance_km(here, there):
    dx = here["x"] - there["x"]
    dy = here["y"] - there["y"]
    return isqrt(dx * dx + dy * dy)


def exceeds_speed(km, seconds, max_speed_kmh):
    return km * 3600 > max_speed_kmh * seconds
