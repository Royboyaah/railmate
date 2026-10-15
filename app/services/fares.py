"""
Fare ESTIMATION model.

Indian Railways fares are distance-slab based with class-specific surcharges.
This module approximates that structure; results are estimates, not official fares.
Rates are illustrative and should be recalibrated against an official fare table.
"""

from __future__ import annotations

import math

CLASS_LABELS = {
    "GN": "General (unreserved)",
    "SL": "Sleeper",
    "CC": "AC Chair Car",
    "3A": "AC 3 Tier",
    "2A": "AC 2 Tier",
    "1A": "AC First Class",
}

BASE_RATE_PER_KM = {"GN": 0.18, "SL": 0.47, "CC": 1.30, "3A": 1.25, "2A": 1.80, "1A": 3.05}
RESERVATION_FEE = {"GN": 0, "SL": 20, "CC": 40, "3A": 40, "2A": 50, "1A": 60}
SUPERFAST_FEE = {"GN": 15, "SL": 30, "CC": 45, "3A": 45, "2A": 45, "1A": 75}
MIN_CHARGEABLE_KM = {"GN": 10, "SL": 200, "CC": 50, "3A": 300, "2A": 300, "1A": 300}

SUPERFAST_TYPES = {"Superfast", "Rajdhani", "Shatabdi", "Duronto", "Garib Rath",
                   "Jan Shatabdi", "Sampark Kranti"}
# Premium trains include catering and higher base fares
TYPE_MULTIPLIER = {"Rajdhani": 1.45, "Shatabdi": 1.80, "Duronto": 1.30, "Garib Rath": 0.70}

# Tapering: longer journeys cost less per km
TAPER = ((500, 1.0), (1000, 0.85), (math.inf, 0.70))


def tapered_km(km: float) -> float:
    remaining, total = km, 0.0
    for slab, factor in TAPER:
        part = min(remaining, slab)
        total += part * factor
        remaining -= part
        if remaining <= 0:
            break
    return total


def estimate_fare(km: float, travel_class: str, train_type: str = "Express") -> int:
    if travel_class not in BASE_RATE_PER_KM:
        raise ValueError(f"Unknown class {travel_class}")
    chargeable = max(km, MIN_CHARGEABLE_KM[travel_class])
    fare = tapered_km(chargeable) * BASE_RATE_PER_KM[travel_class]
    fare *= TYPE_MULTIPLIER.get(train_type, 1.0)
    fare += RESERVATION_FEE[travel_class]
    if train_type in SUPERFAST_TYPES:
        fare += SUPERFAST_FEE[travel_class]
    return int(math.ceil(fare / 5.0) * 5)
