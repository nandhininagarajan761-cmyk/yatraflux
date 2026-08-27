"""
Generates synthetic-but-physically-plausible section_events.csv so the ML
pipeline (ml_pipeline/train_eta.py) can actually be trained end-to-end
without needing a live Indian Railways data feed.

Simulation logic (kept simple and explainable on purpose):
  - Each train starts with delay 0 at its origin.
  - At every subsequent station, delay evolves as a function of platform
    congestion, weather, halt slack (recovery), and random noise —
    the same causal structure the heuristic fallback in app/main.py assumes,
    so a trained model and the fallback should broadly agree.

Run:
    python data/generate_synthetic_data.py --n-trains 400 --out data/section_events.csv
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

TRAIN_TYPES = ["SF", "EXP", "PASS", "MEMU"]
STATIONS = [
    "BCT", "BRC", "RTM", "KOTA", "NDLS", "ST", "ADI", "JP", "AGC", "CNB",
    "PRYJ", "MGS", "PNBE", "HWH", "BBS", "VSKP", "VJA", "SC", "BZA", "MAS",
]


def simulate_train(train_idx: int, start_date: datetime) -> list[dict]:
    train_number = str(10000 + train_idx)
    train_type = random.choices(TRAIN_TYPES, weights=[0.35, 0.35, 0.15, 0.15])[0]
    n_stops = random.randint(5, 12)
    route = random.sample(STATIONS, n_stops)

    origin_hour = random.randint(0, 23)
    scheduled_arrival = start_date.replace(
        hour=origin_hour, minute=random.choice([0, 15, 30, 45]), second=0, microsecond=0
    )

    rows: list[dict] = []
    delay = 0.0
    distance = 0.0

    for seq, station in enumerate(route, start=1):
        distance += random.uniform(60, 220)
        scheduled_arrival = scheduled_arrival + timedelta(
            minutes=random.uniform(45, 150)
        )
        halt_min = 0.0 if seq == 1 else random.choice([2, 3, 5, 5, 10, 15])
        weather_severity = random.choices([0, 1, 2, 3], weights=[0.6, 0.25, 0.1, 0.05])[0]
        platform_congestion = float(np.clip(np.random.beta(2, 5), 0, 1))
        section_avg_delay_min = float(max(0, np.random.normal(6, 4)))
        priority_score = {"SF": 0.85, "EXP": 0.6, "PASS": 0.3, "MEMU": 0.35}[train_type]

        current_delay_in = delay

        if seq > 1:
            # Congestion & weather add delay; halt slack recovers some of it;
            # section historical average pulls delay toward the local norm.
            congestion_penalty = platform_congestion * random.uniform(3, 9)
            weather_penalty = weather_severity * random.uniform(2, 6)
            halt_recovery = min(halt_min * random.uniform(0.2, 0.6), current_delay_in * 0.5)
            drift = (section_avg_delay_min - current_delay_in) * random.uniform(0.05, 0.25)
            noise = np.random.normal(0, 3)

            delay = max(
                0.0,
                current_delay_in + congestion_penalty + weather_penalty - halt_recovery + drift + noise,
            )
        else:
            delay = max(0.0, np.random.normal(2, 2))

        actual_arrival = scheduled_arrival + timedelta(minutes=delay)

        rows.append(
            {
                "train_number": train_number,
                "station_code": station,
                "station_sequence": seq,
                "scheduled_arrival": scheduled_arrival.isoformat(),
                "actual_arrival": actual_arrival.isoformat(),
                "scheduled_distance_km": round(distance, 1),
                "current_delay_min": round(current_delay_in, 1),
                "arrival_delay_min": round(delay, 1),
                "section_avg_delay_min": round(section_avg_delay_min, 1),
                "weather_severity": weather_severity,
                "is_weekend": int(scheduled_arrival.weekday() >= 5),
                "day_of_week": scheduled_arrival.weekday(),
                "hour_of_day": scheduled_arrival.hour,
                "train_type": train_type,
                "priority_score": priority_score,
                "platform_congestion": round(platform_congestion, 3),
                "num_stops_so_far": seq,
                "halts_scheduled_min": halt_min,
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-trains", type=int, default=400)
    parser.add_argument("--out", type=str, default="data/section_events.csv")
    args = parser.parse_args()

    all_rows: list[dict] = []
    base_date = datetime(2026, 6, 1)
    for i in range(args.n_trains):
        day_offset = random.randint(0, 59)
        all_rows.extend(simulate_train(i, base_date + timedelta(days=day_offset)))

    df = pd.DataFrame(all_rows)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows across {args.n_trains} trains to {args.out}")


if __name__ == "__main__":
    main()
