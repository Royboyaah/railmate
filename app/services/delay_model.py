"""
Delay-risk model: probability that a leg arrives more than 30 minutes late.

The SAME feature function is used for training (ml/train_delay_model.py) and for
live predictions, so the two can never drift apart.

IMPORTANT: the shipped model is trained on SYNTHETIC labels (see the model card).
Replace the training labels with real delay records to make predictions meaningful.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.services.timetable import Halt, Train

log = logging.getLogger("railmate.delay")

NORTH_ZONES = {"NR", "NCR", "NER", "ECR", "NWR", "NFR"}
MONSOON_ZONES = {"CR", "WR", "KR", "SWR", "SR"}


def season_of(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5, 6):
        return "summer"
    if month in (7, 8, 9):
        return "monsoon"
    return "post_monsoon"


def leg_features(train: Train, board: Halt, alight: Halt, travel_date: date) -> dict:
    """Features describing arrival at `alight`. All are known before travel."""
    zone = train.zone or "UNK"
    return {
        "train_type": train.type,
        "zone": zone,
        "season": season_of(travel_date.month),
        "north_winter": int(zone in NORTH_ZONES and travel_date.month in (12, 1, 2)),
        "monsoon_coast": int(zone in MONSOON_ZONES and travel_date.month in (7, 8, 9)),
        "km_from_origin": alight.km,
        "leg_km": alight.km - board.km,
        "halts_before": alight.seq,
        "arr_hour": (alight.arr // 60) % 24 if alight.arr is not None else 0,
        "train_total_km": train.distance_km,
    }


class DelayModel:
    """Wraps the trained scikit-learn pipeline, with a transparent fallback."""

    def __init__(self, path: Path):
        self.path = path
        self.pipeline = None
        self.card: dict = {}
        try:
            import joblib

            artifact = joblib.load(path)
            self.pipeline = artifact["pipeline"]
            self.card = artifact["card"]
            log.info("Loaded delay model (%s)", self.card.get("model"))
        except FileNotFoundError:
            log.warning("No delay model at %s - using heuristic fallback. Run: python -m ml.train_delay_model", path)
        except Exception:  # corrupt or incompatible artifact
            log.exception("Could not load delay model - using heuristic fallback")

    @property
    def status(self) -> str:
        return "model" if self.pipeline is not None else "heuristic_fallback"

    def predict(self, rows: list[dict]) -> list[float]:
        if not rows:
            return []
        if self.pipeline is not None:
            return [round(float(p), 3) for p in self.pipeline.predict_proba(rows)[:, 1]]
        return [self._heuristic(r) for r in rows]

    @staticmethod
    def _heuristic(r: dict) -> float:
        p = 0.12 + 0.00025 * r["km_from_origin"] + 0.25 * r["north_winter"]
        if r["train_type"] in {"Rajdhani", "Shatabdi", "Duronto"}:
            p -= 0.06
        return round(min(max(p, 0.02), 0.95), 3)


def missed_connection_risk(p_delay_leg1: float, layover_min: int) -> float:
    """Heuristic: chance a delay on leg 1 eats the whole layover."""
    if layover_min <= 60:
        factor = 0.8
    elif layover_min <= 120:
        factor = 0.4
    elif layover_min <= 240:
        factor = 0.15
    else:
        factor = 0.05
    return round(p_delay_leg1 * factor, 3)
