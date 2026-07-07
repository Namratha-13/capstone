# ObserveAI — LLM Observability Platform

> A production-grade platform that intercepts LLM calls, tracks prompts/responses/
> latency/cost, evaluates quality automatically (hallucination, RAG retrieval, toxicity),
> and provides a real-time dashboard for monitoring AI application health.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Node](https://img.shields.io/badge/Node.js-20-green)

## What it does
- **Trace ingestion** — intercept any LLM call via SDK, stream to Kafka
- **Quality evaluation** — hallucination scoring, RAG retrieval quality, PII detection
- **Cost tracking** — real-time cost per model/project/day with budget alerts
- **Live dashboard** — latency percentiles, cost breakdown, trace explorer

## Tech Stack
| Layer | Technology |
|---|---|
| Ingest API | FastAPI (Python 3.11) |
| Event streaming | Apache Kafka |
| Analytics DB | ClickHouse |
| Relational DB | PostgreSQL |
| Cache | Redis |
| API Gateway | Go (net/http) |
| Frontend | React + Recharts |
| Infrastructure | Docker + Kubernetes |

## Local Setup (full guide coming in Phase 8)
```bash
git clone https://github.com/Namratha-13/observeAi.git
cd observeAi
cp .env.example .env
docker compose up
```

## Status
🚧 Active development — 8-phase build, currently Phase 2

| Phase | Description | Status |
|---|---|---|
| 01 | Infrastructure Setup | ✅ Done |
| 02 | SDK & Ingestion API | ✅ Done |
| 03 | Stream Processing | ✅ Done |
| 04 | Query & Analytics Service | ⏳ Pending |
| 05 | Anomaly Detection | ⏳ Pending |
| 06 | Alerting & Notification | ⏳ Pending |
| 07 | Dashboard Frontend | ⏳ Pending |
| 08 | Load Testing & Hardening | ⏳ Pending |
