"""
YatraFlux AI — Standalone Feature Engineering Pipeline
======================================================

Derives model-ready features from cleaned section-event data and prepares
matrices for LightGBM training.

Usage:
    python -m ml_pipeline.feature_engineering --in data/section_events_cleaned.csv --out data/section_events.csv
"""

import argparse
from pathlib import Path
import pandas as pd
from ml_pipeline.train_eta import engineer_features


def process_features(input_path: Path, output_path: Path) -> None:
    print(f"Loading cleaned section events from {input_path}...")
    raw = pd.read_csv(input_path)

    print("Deriving cyclical time features, delay recovery rates, and cumulative halts...")
    processed = engineer_features(raw)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(output_path, index=False)
    print(f"Saved engineered dataset with {len(processed)} rows to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Feature engineering pipeline.")
    parser.add_argument("--in", type=Path, required=True, dest="input_path", help="Cleaned CSV")
    parser.add_argument("--out", type=Path, default=Path("data/section_events.csv"), help="Output CSV")
    args = parser.parse_args()

    process_features(args.input_path, args.out)


if __name__ == "__main__":
    main()
