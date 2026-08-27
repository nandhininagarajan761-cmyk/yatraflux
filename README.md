# YatraFlux AI — SIH26028

Predictive Railway Intelligence & Delay Management Platform. This package
is fully built, trained, and tested end-to-end — not just scaffolding.

## What's included

```
yatraflux/
├── ml_pipeline/train_eta.py     # LightGBM ETA model + SHAP explainability
├── data/
│   ├── generate_synthetic_data.py  # synthetic training data generator
│   └── section_events.csv          # 3,399 rows, already generated
├── models/                       # ALREADY TRAINED — real .pkl artifacts
│   ├── eta_point_model.pkl
│   ├── eta_lower_model.pkl       # P10 quantile (confidence interval)
│   ├── eta_upper_model.pkl       # P90 quantile (confidence interval)
│   ├── eta_shap_explainer.pkl
│   ├── feature_manifest.json
│   └── metrics.json              # MAE 2.71 min, R² 0.79 on held-out test set
├── app/
│   ├── main.py                   # FastAPI app: /eta, /connections/risk, /simulate/what-if
│   ├── seed_data.py               # populates SQLite with 4 demo trains at BRC junction
│   └── __init__.py
├── components/ConnectionChecker.tsx   # standalone copy of the component
├── frontend/                     # full working Next.js 14 app
│   ├── app/ (layout.tsx, page.tsx, globals.css)
│   ├── components/ConnectionChecker.tsx
│   ├── package.json, tsconfig.json, tailwind.config.ts, next.config.js
│   └── .env.local.example
└── requirements.txt
```

The model in `models/` was trained on the included synthetic dataset and
verified live against all three API endpoints before packaging — MAE 2.71
minutes, R² 0.79, P10–P90 interval coverage 67%. This is synthetic data, so
treat these as a working proof of concept, not production accuracy — retrain
on real historical section-delay data before deploying (see step 3 below).

## 1. Backend — run it now

```bash
cd yatraflux
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

python -m app.seed_data                # creates yatraflux.db with demo trains
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs and try:
- `GET /api/trains/12951/eta`
- `POST /api/connections/risk` — `{"primary_train_number":"12951","connecting_train_number":"12009","connection_station_code":"BRC","buffer_min":20}`
- `POST /api/simulate/what-if` — `{"train_number":"12951","delay_station_code":"BRC","injected_delay_min":30,"propagation_horizon_min":120}`

Check `GET /api/health` — it should report `"prediction_mode": "ml"` since
trained model artifacts are already in `models/`. If you ever delete
`models/`, the API automatically falls back to a rule-based heuristic
instead of crashing.

## 2. Frontend — run it now

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 — enter train `12951`, connecting train `12009`,
station `BRC`, and submit. It calls your live FastAPI backend and renders
the probability gauge, risk badge, and alternatives using the seeded data.
`.env.local` is already set to point at `http://localhost:8000`.

This was verified with `npm run build` — it compiles and type-checks clean.

## 3. Retrain on real data (when you have it)

Replace `data/section_events.csv` with real historical section-event data
matching the schema documented at the top of `ml_pipeline/train_eta.py`,
then:

```bash
python -m ml_pipeline.train_eta --data data/section_events.csv --out models/
```

This overwrites the model artifacts in place — restart `uvicorn` afterward.

To regenerate more/different synthetic data instead:
```bash
python data/generate_synthetic_data.py --n-trains 800 --out data/section_events.csv
```

## Known limitations to flag to your teammates

- **Seed data is illustrative**, not real IR schedules — 4 trains through a
  single junction (Vadodara/BRC). Swap in real train/station data by writing
  directly to the `Train` / `StationStop` / `LiveStatus` tables (see
  `app/seed_data.py` for the pattern).
- **`section_avg_delay_min` and `platform_congestion`** on each `StationStop`
  are treated as precomputed inputs. In production these should come from a
  separate rolling-aggregation job over historical run data, not be
  hand-entered.
- **SQLite is for the MVP/demo only** — set `DATABASE_URL` to a Postgres
  connection string for anything beyond a local demo.
