# Thrumsense — Real-Time IoT Sensor Monitoring System

> A NoSQL-backed monitoring prototype that stores sensor readings in MongoDB, detects anomalies **and broken sensors**, caches hot data in Redis, and shows everything on a dark/light Plotly Dash dashboard, with a built-in **replay engine** and **Benchmark Lab**.

**Course:** Microproject (E1CSA 363) · **Institution:** Alliance School of Advanced Computing, Alliance University · **Batch:** 2024–2028 · **Review:** II
**Mentor:** _to be added_

## 👥 Team
| Name | Suggested ownership |
|---|---|
| Akshaya R | Ingestion, data model, MongoDB indexes |
| Bibi Sufiya Shariff | Detection engine, alerts, health score |
| Pooja G | Dashboard UI/UX, theming, charts |
| Likhitha Devan M | Redis caching, replay engine, benchmark lab, docs |

(Ownership is a suggestion — adjust freely.)

---

## 1. Why this project
IoT sensors emit constant streams. Manual monitoring is slow, failures go unnoticed, and many studies focus on detection accuracy while ignoring **schema design, indexing, caching and query speed**. Thrumsense puts storage, detection and visualisation in one small prototype and **measures** the database choices.

## 2. What's novel
1. **Replay engine** — streams the historical CSV as a live feed (speed control + time-travel scrubber), so "real-time" works without hardware.
2. **Hybrid, explainable detection** — percentile thresholds + adaptive robust z-score + **sensor-fault rules** (dropout, flatline). Separates "the world changed" from "the sensor broke".
3. **Sensor Health Score (0–100)** per sensor and for the fleet.
4. **Benchmark Lab** — one-click latency comparison: no index vs index, cache miss vs hit.
5. **Raw vs reference awareness** — UCI raw sensor responses are never mistaken for true concentrations.

## 3. Features
- Clean and bulk-load UCI Air Quality into MongoDB
- Time-window and per-sensor queries; hourly/daily min/max/avg
- Alerts with rule, value, expected range and severity
- Redis cache-aside with hit/miss KPI (and fallback if Redis is offline)
- Dashboard: KPI strip, time-series with threshold band & anomaly markers, alert feed, health grid, comparisons, filters
- Dark/light theme, subtle animations (respect reduced-motion)

## 4. Architecture

```
 UCI CSV ─► ingest.py ─► MongoDB (readings, alerts, benchmarks)
                              ▲
   replay.py (sim clock) ─► detect.py ─► alerts + Redis counters
                              │
 Dash UI ─► services.py ─► cache.py (Redis, cache-aside) ─► MongoDB on miss
```

| Layer | Component | Responsibility |
|---|---|---|
| L0 | CSV dataset | Public source data |
| L1 | `ingest.py` | Parse, clean, timestamp, bulk insert |
| L2 | MongoDB, Redis | Persistent storage; cache/counters/sim clock |
| L3 | `detect.py`, `aggregate.py`, `health.py`, `replay.py` | Processing |
| L4 | `cache.py` | Cache-aside with TTL |
| L5 | `services.py` | UI-facing functions |
| L6 | Dash app | Visualisation and controls |

Full details: [TECHNICAL.md](TECHNICAL.md). Requirements: [PRD.md](PRD.md). Look & feel: [DESIGN.md](DESIGN.md).

## 5. Tech stack
Python 3.11+ · MongoDB 7 · Redis 7 · Plotly Dash + dash-bootstrap-components · pandas/numpy · PyMongo · redis-py · PyYAML · pytest · Docker Compose.

## 6. Dataset — UCI Air Quality
- 9,358 hourly rows, 15 columns, March 2004 – February 2005
- 5 metal-oxide sensor responses + certified reference pollutant values + T / RH / AH
- Collected by a chemical multisensor device at road level in a polluted Italian city (De Vito et al., 2008; UCI ML Repository)
- Missing values are `-200` → stored as `null`
- Raw `PT08.*` columns are sensor responses, **not** concentrations
- Download from the UCI repository and place it at `data/AirQualityUCI.csv` (file uses `;` separators and decimal commas — the loader handles this)

Other candidate datasets (not implemented): Intel Berkeley Lab, Beijing air quality.

## 7. User workflow

```
Open dashboard ─► sees KPI strip: sensors OK / active alerts / data quality / fleet health
      │
      ├─ Press ▶ Replay (1×, 10×, 60×) ─► data "arrives" hour by hour, alerts slide in
      │
      ├─ Red/amber tile in Health Grid? ─► click ─► chart + alert feed filter to that sensor
      │        └─ read the explanation: rule fired, value vs expected range, severity
      │
      ├─ Change Sensor / Time-range filters ─► trends, hourly/daily summaries, comparisons
      │
      ├─ Drag the scrubber ─► time-travel to any moment in 2004–05
      │
      └─ Benchmark Lab tab ─► Run ─► latency chart: no-index vs index, cache miss vs hit
```

## 8. Quick start

### Prerequisites
Python 3.11+, Docker (for MongoDB + Redis), 8 GB RAM.

### Steps
```bash
git clone <your-repo-url> thrumsense && cd thrumsense

# 1) services
docker compose up -d

# 2) python env
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# 3) data: put AirQualityUCI.csv in ./data/

# 4) load + index
python -m app.ingest --reset

# 5) run (dashboard + in-process replay worker)
python -m app.main
# open http://127.0.0.1:8050
```

### Tests
```bash
pytest -q
```

## 9. Developer guide

### Conventions
- Type hints on public functions; keep functions small and pure where possible.
- No business logic in Dash callbacks: call `services.py`.
- All thresholds/windows live in `config/thresholds.yaml`, never hard-coded.
- Always bound queries by the **sim clock**.
- Cache keys follow `latest:{sensor}` and `stats:{sensor}:{gran}:{from}:{to}`.
- Never reuse `-200`; use `None` after ingestion.

### Common tasks
| Task | Where |
|---|---|
| Add a sensor/variable | `ingest.py` variable map + thresholds override |
| Add a detection rule | `detect.py`, register in `evaluate()`; add test |
| Change colours/fonts | `assets/style.css` tokens (see DESIGN.md) |
| Change cache TTL | `.env` `CACHE_TTL_SECONDS` |
| Add benchmark query | `benchmark.py` queries dict |

### Git workflow
Branch per feature (`feat/detect`, `feat/ui`), small PRs, one reviewer, merge to `main` only when `pytest` passes.

### Troubleshooting
| Symptom | Fix |
|---|---|
| Mongo connection refused | `docker compose ps`; check `MONGO_URI` |
| Dashboard empty | Run `python -m app.ingest --reset`; check the replay clock is not at the start with replay paused |
| "cache offline" badge | Redis is down; the app still works, just slower |
| All values look like numbers like 1,3 | CSV decimal comma not parsed — use `decimal=","` |
| Charts show -200 | Ingestion step skipped or failed |

## 10. Two-day build plan
| When | Who | Goal |
|---|---|---|
| Day 1 AM | All | Repo, docker-compose, ingestion, indexes |
| Day 1 PM | Detect + Cache owners | Detectors, alerts, aggregation, Redis cache |
| Day 2 AM | UI + Replay owners | Layout, theme, replay controls, health grid |
| Day 2 PM | All | Benchmark Lab, tests, screenshots, rehearsal |

**AI-assisted tip:** feed Claude one module at a time using TECHNICAL.md §5 as the spec (e.g. "implement `detect.py` per §5.2–5.5 with pytest tests"), then wire together.

## 11. Evaluation plan
Performance numbers are **not** pre-filled. They come from the Benchmark Lab: queries Q1–Q3 × conditions (no index, index, index without cache, index with cache), 50 runs after warm-up, reporting mean/median/p95 and dataset size. Detection is validated with injected spike/dropout/flatline tests.

## 12. Limitations
- Single node, no multi-node cluster
- Historical hourly data replayed as "live"; no physical hardware
- Rule-based detection, no trained ML
- Thresholds, TTLs and health-score weights are tunable defaults chosen by the team
- Benchmark differences on ~9k rows may be small; a clearly labelled scaled copy can be used

## 13. Future work
MQTT live ingestion · Cassandra comparison · ML detectors · Telegram/email alerts · MongoDB native time-series collections · authentication.

## 14. References
- De Vito, S. et al. (2008). *On field calibration of an electronic nose for benzene estimation in an urban pollution monitoring scenario.* Sensors and Actuators B. UCI ML Repository — Air Quality dataset. (Verify the full citation and URL before final submission.)
- *IoT Sensor Monitoring Review II* presentation (project material).

## 15. License
For academic use. Add a license (e.g. MIT) if publishing the repo.
