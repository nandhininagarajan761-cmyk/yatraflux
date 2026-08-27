"""
YatraFlux AI — ETA / Delay Recovery Training Pipeline
========================================================

Trains a LightGBM regression model to predict `arrival_delay_min` at each
downstream station for a given train, and generates SHAP values so the
FastAPI layer can serve human-readable explanations ("why did the ETA
change?").

Run:
    python -m ml_pipeline.train_eta --data data/section_events.csv --out models/

Expected raw input schema (one row per train-station event):
    train_number         str     e.g. "12951"
    station_code         str     e.g. "BRC"
    station_sequence     int     1-indexed position of station on route
    scheduled_arrival    datetime
    actual_arrival       datetime | NaN (NaN => not yet occurred, inference row)
    scheduled_distance_km float  cumulative distance from origin
    current_delay_min    float   delay AT the previous reporting point
    section_avg_delay_min float historical avg delay for this section (30d)
    weather_severity     int     0-3 ordinal
    is_weekend           int     0/1
    day_of_week          int     0-6
    hour_of_day          int     0-23
    train_type           str     "SF" | "EXP" | "PASS" | "MEMU" etc.
    priority_score       float   traffic-precedence score (higher = more priority)
    platform_congestion  float   0-1 normalized congestion index at next station
    num_stops_so_far     int
    halts_scheduled_min  float   scheduled halt duration at this station
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("yatraflux.train_eta")

TARGET_COL = "arrival_delay_min"

CATEGORICAL_FEATURES: list[str] = [
    "train_type",
    "station_code",
    "day_of_week",
]

NUMERIC_FEATURES: list[str] = [
    "station_sequence",
    "scheduled_distance_km",
    "current_delay_min",
    "section_avg_delay_min",
    "weather_severity",
    "is_weekend",
    "hour_of_day",
    "priority_score",
    "platform_congestion",
    "num_stops_so_far",
    "halts_scheduled_min",
    "delay_recovery_rate",       # engineered
    "time_since_origin_min",     # engineered
    "cumulative_halt_min",       # engineered
    "hour_sin",                  # engineered (cyclical)
    "hour_cos",                  # engineered (cyclical)
]

ALL_FEATURES: list[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass
class TrainingConfig:
    """Hyperparameters and run settings for the ETA regressor."""

    num_leaves: int = 63
    max_depth: int = -1
    learning_rate: float = 0.03
    n_estimators: int = 2000
    min_child_samples: int = 25
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 0.5
    early_stopping_rounds: int = 75
    test_size: float = 0.15
    val_size: float = 0.15
    random_state: int = 42
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)  # for confidence intervals
    extra_params: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Feature engineering
# ----------------------------------------------------------------------------


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive model-ready features from raw section-event rows.

    All transformations here are pure and deterministic so they can be
    replayed identically at inference time inside the FastAPI service.
    """
    out = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(out["scheduled_arrival"]):
        out["scheduled_arrival"] = pd.to_datetime(out["scheduled_arrival"])

    out["hour_of_day"] = out.get(
        "hour_of_day", out["scheduled_arrival"].dt.hour
    )
    out["day_of_week"] = out.get(
        "day_of_week", out["scheduled_arrival"].dt.dayofweek
    )
    out["is_weekend"] = out.get(
        "is_weekend", (out["day_of_week"] >= 5).astype(int)
    )

    # Cyclical encoding of hour-of-day so midnight/late-night rows sit close
    # to each other in feature space instead of at opposite numeric extremes.
    out["hour_sin"] = np.sin(2 * np.pi * out["hour_of_day"] / 24)
    out["hour_cos"] = np.cos(2 * np.pi * out["hour_of_day"] / 24)

    # Delay recovery rate: how fast the train has been gaining/losing time
    # per km travelled so far. A negative value means the train is
    # recovering lost time; positive means the delay is compounding.
    out["time_since_origin_min"] = (
        out["scheduled_arrival"]
        - out.groupby("train_number")["scheduled_arrival"].transform("min")
    ).dt.total_seconds() / 60.0
    safe_distance = out["scheduled_distance_km"].replace(0, np.nan)
    out["delay_recovery_rate"] = (
        out["current_delay_min"] / safe_distance
    ).fillna(0.0)

    out["cumulative_halt_min"] = out.groupby("train_number")[
        "halts_scheduled_min"
    ].cumsum()

    for col in CATEGORICAL_FEATURES:
        out[col] = out[col].astype("category")

    return out


def make_training_frame(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    """Filter to rows with a known outcome and split into X, y."""
    labeled = df.dropna(subset=[TARGET_COL, "actual_arrival"]).copy()
    if labeled.empty:
        raise ValueError(
            "No labeled rows found — every row is missing `actual_arrival` "
            "or `arrival_delay_min`."
        )
    X = labeled[ALL_FEATURES]
    y = labeled[TARGET_COL].astype(float)
    return X, y


# ----------------------------------------------------------------------------
# Training
# ----------------------------------------------------------------------------


class ETADelayModel:
    """Wraps a point-estimate LightGBM regressor plus two quantile models
    (P10 / P90) so the API can return a confidence interval, not just a
    single number.
    """

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()
        self.point_model: lgb.LGBMRegressor | None = None
        self.lower_model: lgb.LGBMRegressor | None = None
        self.upper_model: lgb.LGBMRegressor | None = None
        self.explainer: shap.TreeExplainer | None = None
        self.feature_names: list[str] = ALL_FEATURES

    def _base_params(self) -> dict[str, Any]:
        cfg = self.config
        return dict(
            num_leaves=cfg.num_leaves,
            max_depth=cfg.max_depth,
            learning_rate=cfg.learning_rate,
            n_estimators=cfg.n_estimators,
            min_child_samples=cfg.min_child_samples,
            subsample=cfg.subsample,
            colsample_bytree=cfg.colsample_bytree,
            reg_alpha=cfg.reg_alpha,
            reg_lambda=cfg.reg_lambda,
            random_state=cfg.random_state,
            **cfg.extra_params,
        )

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
    ) -> "ETADelayModel":
        cfg = self.config
        callbacks = [
            lgb.early_stopping(cfg.early_stopping_rounds, verbose=False),
            lgb.log_evaluation(period=100),
        ]

        logger.info("Training point-estimate model (objective=regression_l1)...")
        self.point_model = lgb.LGBMRegressor(
            objective="regression_l1", **self._base_params()
        )
        self.point_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            categorical_feature=CATEGORICAL_FEATURES,
            callbacks=callbacks,
        )

        logger.info("Training P10 quantile model (lower confidence bound)...")
        self.lower_model = lgb.LGBMRegressor(
            objective="quantile", alpha=cfg.quantiles[0], **self._base_params()
        )
        self.lower_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            categorical_feature=CATEGORICAL_FEATURES,
            callbacks=callbacks,
        )

        logger.info("Training P90 quantile model (upper confidence bound)...")
        self.upper_model = lgb.LGBMRegressor(
            objective="quantile", alpha=cfg.quantiles[2], **self._base_params()
        )
        self.upper_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            categorical_feature=CATEGORICAL_FEATURES,
            callbacks=callbacks,
        )

        logger.info("Building SHAP TreeExplainer on point model...")
        self.explainer = shap.TreeExplainer(self.point_model)

        return self

    def _align_categoricals(self, X: pd.DataFrame) -> pd.DataFrame:
        """Cast categorical columns to pandas 'category' dtype before
        inference. LightGBM's sklearn API records the categorical dtype
        used at training time internally; passing plain object/int columns
        at predict time (instead of dtype='category') raises
        "train and valid dataset categorical_feature do not match" even
        though the raw values are fine. This is the single source of truth
        for that conversion — call it before every predict() / explain().
        """
        aligned = X.copy()
        for col in CATEGORICAL_FEATURES:
            if col in aligned.columns:
                aligned[col] = aligned[col].astype("category")
        return aligned

    def predict_with_interval(
        self, X: pd.DataFrame
    ) -> pd.DataFrame:
        """Return point estimate + P10/P90 interval, monotonically corrected
        (upper is never allowed to fall below the point estimate, etc.).
        """
        assert self.point_model and self.lower_model and self.upper_model

        X = self._align_categoricals(X)
        point = self.point_model.predict(X)
        lower = self.lower_model.predict(X)
        upper = self.upper_model.predict(X)

        lower = np.minimum(lower, point)
        upper = np.maximum(upper, point)

        return pd.DataFrame(
            {
                "predicted_delay_min": point,
                "confidence_low_min": lower,
                "confidence_high_min": upper,
            },
            index=X.index,
        )

    def explain(self, X: pd.DataFrame, top_k: int = 4) -> list[dict[str, Any]]:
        """Return top-k SHAP feature contributions per row, human-labeled,
        for the "explainable AI" ETA-change feature.
        """
        assert self.explainer is not None
        X = self._align_categoricals(X)
        shap_values = self.explainer.shap_values(X)

        explanations: list[dict[str, Any]] = []
        for row_idx in range(len(X)):
            row_shap = shap_values[row_idx]
            contributions = sorted(
                zip(self.feature_names, row_shap, X.iloc[row_idx].tolist()),
                key=lambda t: abs(t[1]),
                reverse=True,
            )[:top_k]
            explanations.append(
                {
                    "top_factors": [
                        {
                            "feature": _humanize_feature_name(name),
                            "impact_min": round(float(impact), 2),
                            "value": _stringify(value),
                            "direction": "increases_delay"
                            if impact > 0
                            else "reduces_delay",
                        }
                        for name, impact, value in contributions
                    ]
                }
            )
        return explanations

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.point_model, out_dir / "eta_point_model.pkl")
        joblib.dump(self.lower_model, out_dir / "eta_lower_model.pkl")
        joblib.dump(self.upper_model, out_dir / "eta_upper_model.pkl")
        joblib.dump(self.explainer, out_dir / "eta_shap_explainer.pkl")
        with open(out_dir / "feature_manifest.json", "w") as f:
            json.dump(
                {
                    "features": self.feature_names,
                    "categorical": CATEGORICAL_FEATURES,
                    "target": TARGET_COL,
                },
                f,
                indent=2,
            )
        logger.info("Model artifacts saved to %s", out_dir)

    @classmethod
    def load(cls, in_dir: Path) -> "ETADelayModel":
        model = cls()
        model.point_model = joblib.load(in_dir / "eta_point_model.pkl")
        model.lower_model = joblib.load(in_dir / "eta_lower_model.pkl")
        model.upper_model = joblib.load(in_dir / "eta_upper_model.pkl")
        model.explainer = joblib.load(in_dir / "eta_shap_explainer.pkl")
        return model


def _humanize_feature_name(name: str) -> str:
    mapping = {
        "current_delay_min": "Current running delay",
        "section_avg_delay_min": "Historical section congestion",
        "platform_congestion": "Platform / yard congestion",
        "weather_severity": "Weather conditions",
        "delay_recovery_rate": "Delay recovery trend",
        "halts_scheduled_min": "Scheduled halt duration",
        "priority_score": "Train traffic priority",
        "hour_sin": "Time of day",
        "hour_cos": "Time of day",
        "cumulative_halt_min": "Cumulative halts so far",
    }
    return mapping.get(name, name.replace("_", " ").title())


def _stringify(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


# ----------------------------------------------------------------------------
# Evaluation
# ----------------------------------------------------------------------------


def evaluate(model: ETADelayModel, X_test: pd.DataFrame, y_test: pd.Series) -> dict[str, float]:
    preds = model.predict_with_interval(X_test)
    point = preds["predicted_delay_min"]

    coverage = (
        (y_test >= preds["confidence_low_min"]) & (y_test <= preds["confidence_high_min"])
    ).mean()

    metrics = {
        "mae_min": float(mean_absolute_error(y_test, point)),
        "rmse_min": float(np.sqrt(mean_squared_error(y_test, point))),
        "r2": float(r2_score(y_test, point)),
        "p10_p90_coverage": float(coverage),  # target ~0.80
    }
    logger.info("Evaluation metrics: %s", json.dumps(metrics, indent=2))
    return metrics


# ----------------------------------------------------------------------------
# CLI entrypoint
# ----------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YatraFlux ETA delay model.")
    parser.add_argument("--data", type=Path, required=True, help="Path to section_events.csv")
    parser.add_argument("--out", type=Path, default=Path("models/"), help="Output directory")
    args = parser.parse_args()

    logger.info("Loading raw data from %s", args.data)
    raw = pd.read_csv(args.data)

    logger.info("Engineering features...")
    engineered = engineer_features(raw)
    X, y = make_training_frame(engineered)

    cfg = TrainingConfig()
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=cfg.test_size, random_state=cfg.random_state
    )
    val_fraction = cfg.val_size / (1 - cfg.test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=val_fraction, random_state=cfg.random_state
    )
    logger.info(
        "Split sizes -> train: %d, val: %d, test: %d",
        len(X_train),
        len(X_val),
        len(X_test),
    )

    model = ETADelayModel(cfg).fit(X_train, y_train, X_val, y_val)
    metrics = evaluate(model, X_test, y_test)

    model.save(args.out)
    with open(args.out / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    sample_explanations = model.explain(X_test.head(3))
    logger.info("Sample SHAP explanations:\n%s", json.dumps(sample_explanations, indent=2))


if __name__ == "__main__":
    main()
