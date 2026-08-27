"""
YatraFlux AI — Demo seed data
================================

Populates the SQLite DB with a handful of trains that share a junction
station (BRC = Vadodara) so you can immediately exercise all three
endpoints: /eta, /connections/risk, and /simulate/what-if.

Run:
    python -m app.seed_data
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.main import Base, LiveStatus, SessionLocal, StationStop, Train, engine

Base.metadata.create_all(bind=engine)


def today_at(hour: int, minute: int = 0) -> datetime:
    now = datetime.utcnow()
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def seed() -> None:
    db = SessionLocal()
    try:
        # Wipe existing demo data for a clean re-run
        db.query(LiveStatus).delete()
        db.query(StationStop).delete()
        db.query(Train).delete()
        db.commit()

        # --- Train 1: primary train the passenger is riding ---------------
        t1 = Train(train_number="12951", train_name="Mumbai Rajdhani", train_type="SF")
        db.add(t1)
        db.flush()

        t1_stops = [
            ("BCT", "Mumbai Central", 1, today_at(6, 0), today_at(6, 0), 0, 0, 0.1, 0.1),
            ("BRC", "Vadodara Jn", 2, today_at(9, 30), today_at(9, 35), 392, 5, 8.0, 0.55),
            ("RTM", "Ratlam Jn", 3, today_at(11, 20), today_at(11, 25), 566, 5, 4.0, 0.2),
            ("NDLS", "New Delhi", 4, today_at(20, 0), today_at(20, 0), 1384, 0, 6.0, 0.4),
        ]
        for code, name, seq, arr, dep, dist, halt, avg_delay, cong in t1_stops:
            db.add(
                StationStop(
                    train_id=t1.id,
                    station_code=code,
                    station_name=name,
                    sequence=seq,
                    scheduled_arrival=arr,
                    scheduled_departure=dep,
                    distance_km=dist,
                    halt_min=halt,
                    section_avg_delay_min=avg_delay,
                    platform_congestion=cong,
                )
            )

        # Live status: currently running 22 min late, last seen before BRC
        db.add(
            LiveStatus(
                train_number="12951",
                last_station_code="ST",  # Surat, upstream of BRC
                current_delay_min=22.0,
                reported_at=datetime.utcnow(),
            )
        )

        # --- Train 2: the connecting train at BRC --------------------------
        t2 = Train(train_number="12009", train_name="Shatabdi Express", train_type="SF")
        db.add(t2)
        db.flush()

        t2_stops = [
            ("BRC", "Vadodara Jn", 1, today_at(9, 40), today_at(9, 55), 0, 15, 3.0, 0.3),
            ("ADI", "Ahmedabad Jn", 2, today_at(11, 0), today_at(11, 5), 113, 5, 2.0, 0.15),
        ]
        for code, name, seq, arr, dep, dist, halt, avg_delay, cong in t2_stops:
            db.add(
                StationStop(
                    train_id=t2.id,
                    station_code=code,
                    station_name=name,
                    sequence=seq,
                    scheduled_arrival=arr,
                    scheduled_departure=dep,
                    distance_km=dist,
                    halt_min=halt,
                    section_avg_delay_min=avg_delay,
                    platform_congestion=cong,
                )
            )

        # --- Train 3 & 4: extra trains through BRC, for the what-if sim ----
        t3 = Train(train_number="19033", train_name="Firozpur Janta Express", train_type="EXP")
        db.add(t3)
        db.flush()
        db.add(
            StationStop(
                train_id=t3.id,
                station_code="BRC",
                station_name="Vadodara Jn",
                sequence=1,
                scheduled_arrival=today_at(9, 45),
                scheduled_departure=today_at(9, 55),
                distance_km=0,
                halt_min=10,
                section_avg_delay_min=6.0,
                platform_congestion=0.5,
            )
        )

        t4 = Train(train_number="59441", train_name="BRC-ST MEMU", train_type="MEMU")
        db.add(t4)
        db.flush()
        db.add(
            StationStop(
                train_id=t4.id,
                station_code="BRC",
                station_name="Vadodara Jn",
                sequence=1,
                scheduled_arrival=today_at(10, 30),
                scheduled_departure=today_at(10, 40),
                distance_km=0,
                halt_min=10,
                section_avg_delay_min=4.0,
                platform_congestion=0.35,
            )
        )

        db.commit()
        print("Seeded 4 trains (12951, 12009, 19033, 59441) sharing station BRC.")
        print("Try: GET /api/trains/12951/eta")
        print(
            "Try: POST /api/connections/risk "
            '{"primary_train_number": "12951", "connecting_train_number": "12009", '
            '"connection_station_code": "BRC", "buffer_min": 20}'
        )
        print(
            "Try: POST /api/simulate/what-if "
            '{"train_number": "12951", "delay_station_code": "BRC", '
            '"injected_delay_min": 30, "propagation_horizon_min": 120}'
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
