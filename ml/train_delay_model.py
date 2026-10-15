"""
Train the delay-risk classifier.

DATA HONESTY NOTE
-----------------
No public, licence-clear dataset of historical Indian train delays was available,
so this script generates SYNTHETIC labels on top of REAL timetable features:
  * features (train type, zone, distance, halts, arrival hour, season) come from
    real legs sampled from the timetable database;
  * the label "arrived >30 min late" is drawn from a documented generating rule
    (see `synthetic_logit`) plus random noise.

This demonstrates a complete, reproducible ML pipeline (sampling -> train/test split
-> model vs baseline -> calibration metrics -> versioned artifact + model card).
Predictions only become meaningful once `--labels` points to real delay records:
a CSV with columns train_number,board_code,alight_code,travel_date,delayed (0/1).

Usage:
  python -m ml.train_delay_model                      # synthetic labels
  python -m ml.train_delay_model --labels real.csv    # real labels
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.config import get_settings
from app.db import connect
from app.services.delay_model import leg_features
from app.services.timetable import Timetable

log = logging.getLogger("railmate.train")

TYPE_EFFECT = {"Rajdhani": -0.7, "Shatabdi": -0.9, "Duronto": -0.5, "Jan Shatabdi": -0.2,
               "Superfast": -0.2, "Mail": 0.1, "Garib Rath": 0.1, "Passenger": 0.5,
               "MEMU": -0.3, "DEMU": -0.3, "Suburban": -0.4}


def synthetic_logit(f: dict) -> float:
    """The documented rule used to generate synthetic labels."""
    z = -2.0
    z += 0.00075 * f["km_from_origin"]            # delays accumulate along the route
    z += TYPE_EFFECT.get(f["train_type"], 0.0)    # premium trains get priority paths
    z += 1.2 * f["north_winter"]                  # winter fog in north India
    z += 0.2 * (f["season"] == "winter") * (1 - f["north_winter"])
    z += 0.5 * f["monsoon_coast"]                 # monsoon on coastal/western routes
    z += 0.015 * f["halts_before"]                # each halt adds risk
    z += 0.2 * (f["arr_hour"] < 5)                # night operations
    return z


def sample_synthetic(tt: Timetable, n: int, seed: int) -> tuple[list[dict], list[int]]:
    rng = random.Random(seed)
    trains = [t for t in tt.trains.values() if len(t.halts) >= 2]
    start = date(2024, 1, 1)
    X, y = [], []
    for _ in range(n):
        t = rng.choice(trains)
        i = rng.randrange(0, len(t.halts) - 1)
        j = rng.randrange(i + 1, len(t.halts))
        d = start + timedelta(days=rng.randrange(365))
        f = leg_features(t, t.halts[i], t.halts[j], d)
        z = synthetic_logit(f) + rng.gauss(0, 0.6)    # unobserved noise
        X.append(f)
        y.append(int(rng.random() < 1 / (1 + math.exp(-z))))
    return X, y


def load_real_labels(tt: Timetable, path: Path) -> tuple[list[dict], list[int]]:
    X, y = [], []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = tt.trains.get(row["train_number"])
            if not t:
                continue
            seqs = {h.station: h for h in t.halts}
            b, a = seqs.get(row["board_code"]), seqs.get(row["alight_code"])
            if not b or not a or a.seq <= b.seq:
                continue
            X.append(leg_features(t, b, a, date.fromisoformat(row["travel_date"])))
            y.append(int(row["delayed"]))
    return X, y


def train(tt: Timetable, out: Path, n: int = 60000, seed: int = 42, labels: Path | None = None) -> dict:
    if labels:
        X, y = load_real_labels(tt, labels)
        source = f"real labels from {labels.name}"
    else:
        X, y = sample_synthetic(tt, n, seed)
        source = "SYNTHETIC labels on real timetable features"
    if len(set(y)) < 2:
        raise ValueError("Training labels contain a single class")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)

    candidates = {
        "HistGradientBoostingClassifier": make_pipeline(
            DictVectorizer(sparse=False),
            HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08,
                                           l2_regularization=1.0, random_state=seed)),
        "LogisticRegression": make_pipeline(
            DictVectorizer(sparse=False), StandardScaler(), LogisticRegression(max_iter=1000)),
    }
    results = {}
    for name, pipe in candidates.items():
        pipe.fit(X_tr, y_tr)
        p = pipe.predict_proba(X_te)[:, 1]
        results[name] = {"roc_auc": round(float(roc_auc_score(y_te, p)), 3),
                         "brier": round(float(brier_score_loss(y_te, p)), 4), "_p": p}

    # Model selection on held-out data: lowest Brier score (rewards calibrated probabilities)
    chosen = min(results, key=lambda k: results[k]["brier"])
    model, p_model = candidates[chosen], results[chosen]["_p"]
    base_rate = float(np.mean(y_tr))

    # simple reliability table: predicted vs observed in 5 bins
    bins = np.linspace(0, 1, 6)
    calibration = []
    for lo, hi in zip(bins[:-1], bins[1:], strict=False):
        mask = (p_model >= lo) & (p_model < hi)
        if mask.sum():
            calibration.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()),
                                "predicted": round(float(p_model[mask].mean()), 3),
                                "observed": round(float(np.array(y_te)[mask].mean()), 3)})

    card = {
        "model": chosen,
        "selection": "lowest Brier score on a 20% held-out test set",
        "target": "arrival delay > 30 minutes",
        "training_data": source,
        "synthetic": labels is None,
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "positive_rate": round(base_rate, 3),
        "metrics": {
            "roc_auc": results[chosen]["roc_auc"],
            "brier": results[chosen]["brier"],
            "constant_baseline_brier": round(float(brier_score_loss(y_te, [base_rate] * len(y_te))), 4),
        },
        "candidates": {k: {m: v for m, v in r.items() if m != "_p"} for k, r in results.items()},
        "calibration": calibration,
        "features": sorted(X[0].keys()),
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "limitations": [
            "Synthetic labels: metrics show the pipeline works, not real-world accuracy."
            if labels is None else "Accuracy depends on the coverage of the supplied delay records.",
            "Does not use live running status, weather feeds or track maintenance blocks.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "card": card}, out)
    return card


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=s.db_path)
    ap.add_argument("--out", type=Path, default=s.model_path)
    ap.add_argument("--samples", type=int, default=60000)
    ap.add_argument("--labels", type=Path, default=None)
    args = ap.parse_args(argv)

    conn = connect(args.db)
    tt = Timetable.from_db(conn)
    conn.close()
    if not tt.loaded:
        log.error("Timetable is empty. Run: python -m scripts.build_dataset")
        return 1
    card = train(tt, args.out, n=args.samples, labels=args.labels)
    log.info("Saved model to %s", args.out)
    log.info("Metrics: %s", card["metrics"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
