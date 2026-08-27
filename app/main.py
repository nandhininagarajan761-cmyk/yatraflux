"""
YatraFlux AI — FastAPI Core Service
=======================================

Serves three endpoints:
    GET  /api/trains/{train_number}/eta
    POST /api/connections/risk
    POST /api/simulate/what-if

Run (dev):
    uvicorn app.main:app --reload --port 8000

Run (demo / SQLite):
    export DATABASE_URL="sqlite:///./yatraflux.db"
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import math
import os
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Database setup (SQLite for MVP; swap DATABASE_URL for Postgres in prod)
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./yatraflux.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class Train(Base):
    __tablename__ = "trains"

    id = Column(Integer, primary_key=True)
    train_number = Column(String(10), unique=True, index=True, nullable=False)
    train_name = Column(String(120), nullable=False)
    train_type = Column(String(10), default="EXP")

    stops = relationship("StationStop", back_populates="train", order_by="StationStop.sequence")


class StationStop(Base):
    __tablename__ = "station_stops"

    id = Column(Integer, primary_key=True)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    station_code = Column(String(10), nullable=False)
    station_name = Column(String(120), nullable=False)
    sequence = Column(Integer, nullable=False)
    scheduled_arrival = Column(DateTime, nullable=False)
    scheduled_departure = Column(DateTime, nullable=False)
    distance_km = Column(Float, nullable=False)
    halt_min = Column(Float, default=2.0)
    section_avg_delay_min = Column(Float, default=5.0)  # rolling historical avg
    platform_congestion = Column(Float, default=0.2)  # 0-1

    train = relationship("Train", back_populates="stops")


class LiveStatus(Base):
    """Latest known real-world position/delay for a train (fed by an
    ingestion job in production; used here as the source of current_delay).
    """

    __tablename__ = "live_status"

    id = Column(Integer, primary_key=True)
    train_number = Column(String(10), index=True, nullable=False)
    last_station_code = Column(String(10), nullable=False)
    current_delay_min = Column(Float, default=0.0)
    reported_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Pydantic schemas (mirrored 1:1 by the TypeScript interfaces in the frontend)
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DelayFactor(BaseModel):
    feature: str
    impact_min: float
    value: str
    direction: str  # "increases_delay" | "reduces_delay"


class StationETA(BaseModel):
    station_code: str
    station_name: str
    sequence: int
    scheduled_arrival: datetime
    predicted_arrival: datetime
    predicted_delay_min: float
    confidence_low_min: float
    confidence_high_min: float
    recovery_min: float = Field(
        description="Minutes of delay expected to be recovered vs. current running delay "
        "by the time the train reaches this station. Positive = recovering."
    )
    top_factors: list[DelayFactor]


class TrainETAResponse(BaseModel):
    train_number: str
    train_name: str
    current_delay_min: float
    last_known_station: str
    generated_at: datetime
    stations: list[StationETA]


class ConnectionRiskRequest(BaseModel):
    primary_train_number: str
    connecting_train_number: str
    connection_station_code: str
    buffer_min: int = Field(
        default=20, ge=0, le=360, description="Minimum acceptable connection buffer"
    )

    @field_validator("primary_train_number", "connecting_train_number")
    @classmethod
    def _numeric_train(cls, v: str) -> str:
        if not v.strip().isdigit():
            raise ValueError("train_number must be numeric")
        return v.strip()


class AlternativeTrain(BaseModel):
    train_number: str
    train_name: str
    departure_time: datetime
    success_probability: float


class ConnectionRiskResponse(BaseModel):
    primary_train_number: str
    connecting_train_number: str
    connection_station_code: str
    primary_predicted_arrival: datetime
    connecting_scheduled_departure: datetime
    effective_buffer_min: float
    required_buffer_min: int
    success_probability: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    explanation: str
    alternative_trains: list[AlternativeTrain]


class WhatIfRequest(BaseModel):
    train_number: str
    delay_station_code: str
    injected_delay_min: int = Field(ge=1, le=600)
    propagation_horizon_min: int = Field(
        default=240, ge=30, le=720, description="How far ahead (minutes) to simulate impact"
    )


class ImpactedTrain(BaseModel):
    train_number: str
    train_name: str
    shared_station_code: str
    conflict_type: str  # "same_track_section" | "platform_conflict" | "crossing_precedence"
    estimated_secondary_delay_min: float
    estimated_impact_time: datetime


class WhatIfResponse(BaseModel):
    origin_train_number: str
    injected_delay_min: int
    delay_station_code: str
    total_network_delay_min: float
    impacted_trains: list[ImpactedTrain]
    cascade_depth: int
    narrative: str


class StationCongestionInfo(BaseModel):
    station_code: str
    station_name: str
    avg_delay_min: float
    platform_congestion: float
    active_trains_count: int


class ActiveTrainStatus(BaseModel):
    train_number: str
    train_name: str
    current_delay_min: float
    last_station_code: str


class NetworkStatusResponse(BaseModel):
    active_trains_count: int
    network_avg_delay_min: float
    high_risk_junctions_count: int
    congested_stations: list[StationCongestionInfo]
    recent_trains: list[ActiveTrainStatus]
    prediction_mode: str



# ---------------------------------------------------------------------------
# Prediction engine
# ---------------------------------------------------------------------------
# In production this loads ml_pipeline artifacts (LightGBM point/quantile
# models + SHAP TreeExplainer) via ETADelayModel.load(). For the MVP/demo
# path (no trained artifacts on disk yet) we fall back to a transparent
# rule-based estimator so every endpoint is runnable out of the box, and the
# response shapes never change between the two modes.

MODEL_DIR = Path(os.getenv("YATRAFLUX_MODEL_DIR", "models/"))


class ETAPredictor:
    def __init__(self, model_dir: Path) -> None:
        self.model = None
        try:
            from ml_pipeline.train_eta import ETADelayModel  # local import, optional dep

            if (model_dir / "eta_point_model.pkl").exists():
                self.model = ETADelayModel.load(model_dir)
        except Exception:
            self.model = None  # graceful fallback to heuristic mode below

    @property
    def is_ml_backed(self) -> bool:
        return self.model is not None

    def predict_station(
        self,
        current_delay_min: float,
        sequence: int,
        distance_km: float,
        section_avg_delay_min: float,
        platform_congestion: float,
        halt_min: float,
        hour_of_day: int,
    ) -> tuple[float, float, float, list[DelayFactor]]:
        """Returns (point_delay, low, high, top_factors)."""

        if self.model is not None:
            import pandas as pd

            row = pd.DataFrame(
                [
                    {
                        "station_sequence": sequence,
                        "scheduled_distance_km": distance_km,
                        "current_delay_min": current_delay_min,
                        "section_avg_delay_min": section_avg_delay_min,
                        "weather_severity": 0,
                        "is_weekend": 0,
                        "hour_of_day": hour_of_day,
                        "priority_score": 0.5,
                        "platform_congestion": platform_congestion,
                        "num_stops_so_far": sequence,
                        "halts_scheduled_min": halt_min,
                        "delay_recovery_rate": current_delay_min / max(distance_km, 1.0),
                        "time_since_origin_min": sequence * 45.0,
                        "cumulative_halt_min": halt_min * sequence,
                        "hour_sin": math.sin(2 * math.pi * hour_of_day / 24),
                        "hour_cos": math.cos(2 * math.pi * hour_of_day / 24),
                        "train_type": "EXP",
                        "station_code": "NA",
                        "day_of_week": 0,
                    }
                ]
            )
            preds = self.model.predict_with_interval(row).iloc[0]
            factors_raw = self.model.explain(row)[0]["top_factors"]
            factors = [DelayFactor(**f) for f in factors_raw]
            return (
                float(preds["predicted_delay_min"]),
                float(preds["confidence_low_min"]),
                float(preds["confidence_high_min"]),
                factors,
            )

        # --- Heuristic fallback (transparent, explainable, no ML dependency) ---
        # Delay tends to regress toward the historical section average, damped
        # by how congested the next platform is and how much halt time is
        # scheduled (more halt = more slack to absorb delay).
        congestion_penalty = platform_congestion * 6.0
        halt_recovery = min(halt_min * 0.4, current_delay_min * 0.5)
        drift_to_section_avg = (section_avg_delay_min - current_delay_min) * 0.15

        point = max(
            0.0,
            current_delay_min + drift_to_section_avg + congestion_penalty - halt_recovery,
        )
        spread = max(3.0, current_delay_min * 0.25 + platform_congestion * 4.0)
        low = max(0.0, point - spread)
        high = point + spread

        factors = [
            DelayFactor(
                feature="Current running delay",
                impact_min=round(current_delay_min * 0.6, 2),
                value=f"{current_delay_min:.1f} min",
                direction="increases_delay" if current_delay_min > 0 else "reduces_delay",
            ),
            DelayFactor(
                feature="Platform / yard congestion",
                impact_min=round(congestion_penalty, 2),
                value=f"{platform_congestion:.2f}",
                direction="increases_delay",
            ),
            DelayFactor(
                feature="Scheduled halt duration",
                impact_min=round(-halt_recovery, 2),
                value=f"{halt_min:.1f} min",
                direction="reduces_delay",
            ),
            DelayFactor(
                feature="Historical section congestion",
                impact_min=round(drift_to_section_avg, 2),
                value=f"{section_avg_delay_min:.1f} min avg",
                direction="increases_delay" if drift_to_section_avg > 0 else "reduces_delay",
            ),
        ]
        factors.sort(key=lambda f: abs(f.impact_min), reverse=True)
        return point, low, high, factors[:4]


predictor = ETAPredictor(MODEL_DIR)


def connection_success_probability(
    effective_buffer_min: float, required_buffer_min: int, arrival_uncertainty_min: float
) -> float:
    """Logistic model over buffer margin, widened by prediction uncertainty.

    A buffer exactly equal to the required minimum sits at ~50%. Higher
    uncertainty (wider ETA confidence interval) flattens the curve, i.e.
    makes YatraFlux appropriately less confident either way.
    """
    margin = effective_buffer_min - required_buffer_min
    steepness = 1.0 / max(2.0, arrival_uncertainty_min / 2.0)
    probability = 1.0 / (1.0 + math.exp(-steepness * margin))
    return round(probability * 100, 1)


def risk_level_from_probability(p: float) -> RiskLevel:
    if p >= 75:
        return RiskLevel.LOW
    if p >= 45:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="YatraFlux AI",
    description="Predictive Railway Intelligence & Delay Management Platform (SIH26028)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "prediction_mode": "ml" if predictor.is_ml_backed else "heuristic"}


eta_cache: dict[str, TrainETAResponse] = {}


@app.get("/api/trains/{train_number}/eta", response_model=TrainETAResponse)
def get_train_eta(train_number: str, db: Session = Depends(get_db)) -> TrainETAResponse:
    global eta_cache
    if train_number in eta_cache:
        return eta_cache[train_number]

    train = db.query(Train).filter(Train.train_number == train_number).first()
    if train is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Train {train_number} not found")

    live = (
        db.query(LiveStatus)
        .filter(LiveStatus.train_number == train_number)
        .order_by(LiveStatus.reported_at.desc())
        .first()
    )
    current_delay = live.current_delay_min if live else 0.0
    last_station = live.last_station_code if live else (train.stops[0].station_code if train.stops else "N/A")

    stations: list[StationETA] = []
    running_delay = current_delay

    for stop in train.stops:
        predicted_delay, low, high, factors = predictor.predict_station(
            current_delay_min=running_delay,
            sequence=stop.sequence,
            distance_km=stop.distance_km,
            section_avg_delay_min=stop.section_avg_delay_min,
            platform_congestion=stop.platform_congestion,
            halt_min=stop.halt_min,
            hour_of_day=stop.scheduled_arrival.hour,
        )
        recovery = running_delay - predicted_delay

        stations.append(
            StationETA(
                station_code=stop.station_code,
                station_name=stop.station_name,
                sequence=stop.sequence,
                scheduled_arrival=stop.scheduled_arrival,
                predicted_arrival=stop.scheduled_arrival + timedelta(minutes=predicted_delay),
                predicted_delay_min=round(predicted_delay, 1),
                confidence_low_min=round(low, 1),
                confidence_high_min=round(high, 1),
                recovery_min=round(recovery, 1),
                top_factors=factors,
            )
        )
        running_delay = predicted_delay  # carry forward for next section

    response = TrainETAResponse(
        train_number=train.train_number,
        train_name=train.train_name,
        current_delay_min=current_delay,
        last_known_station=last_station,
        generated_at=datetime.utcnow(),
        stations=stations,
    )
    eta_cache[train_number] = response
    return response



@app.post("/api/connections/risk", response_model=ConnectionRiskResponse)
def check_connection_risk(
    req: ConnectionRiskRequest, db: Session = Depends(get_db)
) -> ConnectionRiskResponse:
    primary = db.query(Train).filter(Train.train_number == req.primary_train_number).first()
    connecting = db.query(Train).filter(Train.train_number == req.connecting_train_number).first()
    if primary is None or connecting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or both trains not found")

    primary_stop = next(
        (s for s in primary.stops if s.station_code == req.connection_station_code), None
    )
    connecting_stop = next(
        (s for s in connecting.stops if s.station_code == req.connection_station_code), None
    )
    if primary_stop is None or connecting_stop is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"One or both trains do not stop at {req.connection_station_code}",
        )

    live = (
        db.query(LiveStatus)
        .filter(LiveStatus.train_number == req.primary_train_number)
        .order_by(LiveStatus.reported_at.desc())
        .first()
    )
    current_delay = live.current_delay_min if live else 0.0

    predicted_delay, low, high, _factors = predictor.predict_station(
        current_delay_min=current_delay,
        sequence=primary_stop.sequence,
        distance_km=primary_stop.distance_km,
        section_avg_delay_min=primary_stop.section_avg_delay_min,
        platform_congestion=primary_stop.platform_congestion,
        halt_min=primary_stop.halt_min,
        hour_of_day=primary_stop.scheduled_arrival.hour,
    )
    predicted_arrival = primary_stop.scheduled_arrival + timedelta(minutes=predicted_delay)
    effective_buffer = (connecting_stop.scheduled_departure - predicted_arrival).total_seconds() / 60.0
    uncertainty = max(1.0, (high - low) / 2)

    probability = connection_success_probability(effective_buffer, req.buffer_min, uncertainty)
    risk = risk_level_from_probability(probability)

    if effective_buffer < 0:
        explanation = (
            f"Predicted arrival at {req.connection_station_code} is already after "
            f"{connecting.train_number}'s scheduled departure — connection is at serious risk."
        )
    elif effective_buffer < req.buffer_min:
        explanation = (
            f"Only ~{effective_buffer:.0f} min buffer expected, below your "
            f"{req.buffer_min} min minimum, with ETA uncertainty of ±{uncertainty:.0f} min."
        )
    else:
        explanation = (
            f"~{effective_buffer:.0f} min buffer expected, comfortably above your "
            f"{req.buffer_min} min minimum."
        )

    alternatives_q = (
        db.query(Train, StationStop)
        .join(StationStop, Train.id == StationStop.train_id)
        .filter(
            StationStop.station_code == req.connection_station_code,
            Train.train_number != connecting.train_number,
            StationStop.scheduled_departure > predicted_arrival,
        )
        .order_by(StationStop.scheduled_departure.asc())
        .limit(3)
        .all()
    )
    alternatives = [
        AlternativeTrain(
            train_number=t.train_number,
            train_name=t.train_name,
            departure_time=stop.scheduled_departure,
            success_probability=connection_success_probability(
                (stop.scheduled_departure - predicted_arrival).total_seconds() / 60.0,
                req.buffer_min,
                uncertainty,
            ),
        )
        for t, stop in alternatives_q
    ]

    return ConnectionRiskResponse(
        primary_train_number=primary.train_number,
        connecting_train_number=connecting.train_number,
        connection_station_code=req.connection_station_code,
        primary_predicted_arrival=predicted_arrival,
        connecting_scheduled_departure=connecting_stop.scheduled_departure,
        effective_buffer_min=round(effective_buffer, 1),
        required_buffer_min=req.buffer_min,
        success_probability=probability,
        risk_level=risk,
        explanation=explanation,
        alternative_trains=alternatives,
    )


@app.post("/api/simulate/what-if", response_model=WhatIfResponse)
def simulate_what_if(req: WhatIfRequest, db: Session = Depends(get_db)) -> WhatIfResponse:
    global eta_cache
    eta_cache.clear()
    origin = db.query(Train).filter(Train.train_number == req.train_number).first()
    if origin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Train {req.train_number} not found")

    origin_stop = next(
        (s for s in origin.stops if s.station_code == req.delay_station_code), None
    )
    if origin_stop is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{req.train_number} does not stop at {req.delay_station_code}",
        )

    horizon_end = origin_stop.scheduled_arrival + timedelta(minutes=req.propagation_horizon_min)

    # Build conflict edges: any other train stopping at the SAME station
    # within the horizon window after the injected delay.
    candidates = (
        db.query(Train, StationStop)
        .join(StationStop, Train.id == StationStop.train_id)
        .filter(
            StationStop.station_code == req.delay_station_code,
            Train.train_number != origin.train_number,
            StationStop.scheduled_arrival >= origin_stop.scheduled_arrival,
            StationStop.scheduled_arrival <= horizon_end,
        )
        .all()
    )

    # BFS-style propagation, decaying 35% per hop, floored once negligible.
    DECAY = 0.65
    MIN_IMPACT_MIN = 1.0

    impacted: list[ImpactedTrain] = []
    queue: deque[tuple[float, int]] = deque()
    queue.append((float(req.injected_delay_min), 0))

    visited_trains: set[str] = {origin.train_number}
    total_network_delay = 0.0
    max_depth = 0

    frontier = [(t, s, float(req.injected_delay_min), 1) for t, s in candidates]
    while frontier:
        next_frontier: list[tuple[Train, StationStop, float, int]] = []
        for t, s, incoming_delay, depth in frontier:
            if t.train_number in visited_trains:
                continue

            congestion_factor = 1.0 + s.platform_congestion
            propagated = incoming_delay * DECAY * congestion_factor
            if propagated < MIN_IMPACT_MIN:
                continue

            gap_min = (s.scheduled_arrival - origin_stop.scheduled_arrival).total_seconds() / 60.0
            conflict_type = (
                "platform_conflict"
                if gap_min < 15
                else "same_track_section"
                if gap_min < 60
                else "crossing_precedence"
            )

            impacted.append(
                ImpactedTrain(
                    train_number=t.train_number,
                    train_name=t.train_name,
                    shared_station_code=req.delay_station_code,
                    conflict_type=conflict_type,
                    estimated_secondary_delay_min=round(propagated, 1),
                    estimated_impact_time=s.scheduled_arrival + timedelta(minutes=propagated),
                )
            )
            total_network_delay += propagated
            visited_trains.add(t.train_number)
            max_depth = max(max_depth, depth)

            # second-order propagation: trains that meet THIS train downstream
            second_order = (
                db.query(Train, StationStop)
                .join(StationStop, Train.id == StationStop.train_id)
                .filter(
                    StationStop.station_code == req.delay_station_code,
                    Train.train_number != t.train_number,
                    Train.train_number.notin_(visited_trains),
                    StationStop.scheduled_arrival > s.scheduled_arrival,
                    StationStop.scheduled_arrival <= horizon_end,
                )
                .all()
            )
            next_frontier.extend((t2, s2, propagated, depth + 1) for t2, s2 in second_order)
        frontier = next_frontier

    impacted.sort(key=lambda x: x.estimated_secondary_delay_min, reverse=True)

    narrative = (
        f"Injecting a {req.injected_delay_min}-min delay for {origin.train_number} at "
        f"{req.delay_station_code} propagates to {len(impacted)} train(s) across "
        f"{max_depth} cascade hop(s) within a {req.propagation_horizon_min}-min horizon, "
        f"adding an estimated {round(total_network_delay, 1)} cumulative minutes of "
        f"network-wide secondary delay."
        if impacted
        else (
            f"Injecting a {req.injected_delay_min}-min delay for {origin.train_number} at "
            f"{req.delay_station_code} shows no significant downstream conflicts within the "
            f"{req.propagation_horizon_min}-min horizon."
        )
    )

    return WhatIfResponse(
        origin_train_number=origin.train_number,
        injected_delay_min=req.injected_delay_min,
        delay_station_code=req.delay_station_code,
        total_network_delay_min=round(total_network_delay, 1),
        impacted_trains=impacted,
        cascade_depth=max_depth,
        narrative=narrative,
    )


@app.get("/api/network/status", response_model=NetworkStatusResponse)
def get_network_status(db: Session = Depends(get_db)) -> NetworkStatusResponse:
    trains = db.query(Train).all()
    live_statuses = db.query(LiveStatus).all()

    total_trains = len(trains)
    delays = [l.current_delay_min for l in live_statuses]
    avg_delay = round(sum(delays) / max(len(delays), 1), 1) if delays else 0.0

    stops = db.query(StationStop).all()
    station_map = defaultdict(list)
    for s in stops:
        station_map[s.station_code].append(s)

    congested: list[StationCongestionInfo] = []
    high_risk_junctions = 0
    for code, stop_list in station_map.items():
        name = stop_list[0].station_name
        avg_s_delay = sum(s.section_avg_delay_min for s in stop_list) / len(stop_list)
        avg_s_cong = sum(s.platform_congestion for s in stop_list) / len(stop_list)
        count = len(stop_list)
        if avg_s_cong >= 0.35 or avg_s_delay >= 4.0:
            high_risk_junctions += 1
        congested.append(
            StationCongestionInfo(
                station_code=code,
                station_name=name,
                avg_delay_min=round(avg_s_delay, 1),
                platform_congestion=round(avg_s_cong, 2),
                active_trains_count=count,
            )
        )

    recent: list[ActiveTrainStatus] = []
    for t in trains:
        live = next((l for l in live_statuses if l.train_number == t.train_number), None)
        recent.append(
            ActiveTrainStatus(
                train_number=t.train_number,
                train_name=t.train_name,
                current_delay_min=live.current_delay_min if live else 0.0,
                last_station_code=live.last_station_code if live else "N/A",
            )
        )

    return NetworkStatusResponse(
        active_trains_count=total_trains,
        network_avg_delay_min=avg_delay,
        high_risk_junctions_count=high_risk_junctions,
        congested_stations=congested,
        recent_trains=recent,
        prediction_mode="ml" if predictor.is_ml_backed else "heuristic",
    )

