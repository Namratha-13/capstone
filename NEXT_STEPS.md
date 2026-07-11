# 🚀 ObserveAI — What to Build Next (After Phase 3)

> **Who is this for?** Anyone joining the project who wants to know what's already done
> and what still needs to be built. No jargon — written in plain English.

---

## 📦 What's Already Built (Phases 1–3)

Think of the system like a **pipeline** where AI call data flows through multiple stages:

```
Your App (uses SDK)
     ↓
API Gateway (Go) ← security checkpoint, rate limiter
     ↓
Ingest API (Python/FastAPI) ← validates data, adds cost info
     ↓
Kafka ← message queue (holds data temporarily)
     ↓
Kafka Consumer (Python) ← reads from Kafka, writes to ClickHouse
     ↓
ClickHouse ← analytics database (fast queries on millions of rows)
PostgreSQL  ← regular database (tenants, API keys, pricing)
```

### ✅ Phase 1 — Infrastructure (Database & Plumbing)
- Set up PostgreSQL (stores users, API keys, pricing)
- Set up ClickHouse (stores all AI trace data for analytics)
- Set up Kafka (message queue between services)
- Set up Redis (for rate limiting)
- Docker Compose running all services locally

### ✅ Phase 2 — SDK & Ingestion API
- **Python SDK** — wraps OpenAI/Anthropic calls to auto-capture prompt, response, tokens, latency
- **JavaScript SDK** — same thing for Node.js apps
- **Ingest API** — receives data from SDK, calculates cost, publishes to Kafka
- **API Gateway (Go)** — sits in front, checks API keys, rate-limits requests

### ✅ Phase 3 — Stream Processing
- **Kafka Consumer** — reads AI trace events from Kafka
- Enriches and validates each event
- Writes batches of events to ClickHouse
- Handles retries and graceful shutdown

---

## 🔨 What Still Needs to Be Built (Phases 4–8)

---

## Phase 4 — Query & Analytics Service ⏳

**In plain English:** Right now data goes *into* the system but nothing can *read* it back out. This phase builds the API that lets the dashboard (and other tools) ask questions like "How much did we spend on GPT-4 today?" or "Show me the 10 slowest AI calls."

### What to build:
A new **FastAPI service** (call it `query-api`) that exposes these endpoints:

| Endpoint | What it does |
|---|---|
| `GET /v1/traces` | List traces with filters (model, project, date range, status) |
| `GET /v1/traces/{trace_id}` | Get full details of a single trace (prompt + response) |
| `GET /v1/analytics/cost` | Total cost grouped by model, project, or day |
| `GET /v1/analytics/tokens` | Token usage over time |
| `GET /v1/analytics/latency` | P50/P95/P99 latency per model |
| `GET /v1/analytics/errors` | Error rate and error messages |

### How it works:
1. Dashboard or user calls the query API
2. Query API reads from **ClickHouse** (for analytics) and **PostgreSQL** (for metadata)
3. Returns JSON the dashboard can display

### Files to create:
```
services/query-api/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py          ← FastAPI app with all the routes
│   ├── config.py        ← env vars (ClickHouse host, etc.)
│   ├── models.py        ← Pydantic response schemas
│   ├── clickhouse.py    ← query functions for ClickHouse
│   └── auth.py          ← same API key validation as ingest-api
└── tests/
    └── test_query.py
```

### Add to docker-compose.yml:
```yaml
query-api:
  build: ./services/query-api
  ports:
    - "8002:8002"
  environment:
    CLICKHOUSE_HOST: clickhouse
    POSTGRES_HOST: postgres
```

---

## Phase 5 — Evaluation Engine (AI Quality Scoring) ⏳

**In plain English:** This is the "quality checker." After a trace is saved to ClickHouse, a background worker analyses it and gives it scores — did the AI hallucinate? Was the response toxic? Did it leak personal info?

The database tables for this already exist (`evaluations` table in ClickHouse, `project_eval_config` in PostgreSQL). Now we need the code that actually fills them.

### What to build:
A new **Python worker service** (`eval-engine`) — the folder exists but is empty.

### How it works:
1. Worker polls ClickHouse for traces that haven't been evaluated yet
2. For each trace, it runs these checks:

| Check | What it does | How |
|---|---|---|
| **Hallucination Score** | Did the AI make things up? | Compare response against known facts or a reference answer |
| **Toxicity Score** | Is the response harmful/offensive? | Use a classifier model (e.g., Detoxify library) |
| **PII Detection** | Did the response leak names, emails, phone numbers? | Use regex + a NLP library like Presidio |
| **Answer Relevancy** | Is the answer actually about the question? | Semantic similarity (cosine similarity of embeddings) |
| **RAG Context Quality** | If using RAG, did it retrieve the right context? | Context precision & recall metrics |

3. Writes evaluation scores to ClickHouse `evaluations` table
4. Respects per-project settings in `project_eval_config` (you can turn off checks per project)

### Files to create:
```
services/eval-engine/
├── Dockerfile
├── requirements.txt      ← include: detoxify, presidio-analyzer, sentence-transformers
├── main.py               ← polling loop
├── config.py             ← env vars
├── evaluators/
│   ├── hallucination.py  ← hallucination scorer
│   ├── toxicity.py       ← toxicity scorer
│   ├── pii.py            ← PII detector
│   └── relevancy.py      ← answer relevancy scorer
└── clickhouse_client.py  ← read unscored traces, write scores
```

---

## Phase 6 — Alerting & Notifications ⏳

**In plain English:** This phase makes the system "talk back" when something goes wrong. For example: "You've spent $500 today" or "Error rate jumped above 10%" or "Someone's prompt contained PII."

The `alert_rules` table in PostgreSQL already has the schema for this — now we need the code that checks those rules and fires alerts.

### What to build:
A **lightweight scheduler/worker** that runs every few minutes and checks alert rules.

### Alert types to support:
| Rule Type | Example Trigger | Where to find the data |
|---|---|---|
| `cost_budget` | Daily cost > $X | ClickHouse `hourly_cost_by_model` |
| `error_rate` | Error % > threshold | ClickHouse `traces` |
| `latency_spike` | P95 latency > X ms | ClickHouse `hourly_latency` |
| `hallucination` | Hallucination score > 0.8 | ClickHouse `evaluations` |
| `pii_detected` | Any trace with PII | ClickHouse `evaluations` |

### Notification channels to support:
- **Webhook** — POST a JSON payload to a URL (e.g., Slack, PagerDuty)
- **Email** — SMTP email (use `smtplib` or SendGrid API)
- *(Optional)* Slack direct integration

### Files to create:
```
services/alert-engine/
├── Dockerfile
├── requirements.txt      ← include: httpx, schedule
├── main.py               ← runs every N minutes
├── config.py
├── rule_checker.py       ← queries ClickHouse, compares against thresholds
├── notifiers/
│   ├── webhook.py        ← HTTP POST to webhook URL
│   └── email.py          ← sends email
└── pg_client.py          ← reads alert_rules from PostgreSQL
```

---

## Phase 7 — Dashboard Frontend ⏳

**In plain English:** This is the visual part — the website where you log in and see charts, tables, and alerts. Right now the `dashboard/` folder is empty. The README says it should use React + Recharts.

### What to build:
A **React application** that talks to the Query API (Phase 4) and shows:

### Pages to build:

#### 1. Overview Dashboard (homepage)
- Total cost this month (big number card)
- Total traces today
- Average latency
- Error rate
- Line chart: cost over the last 7 days
- Bar chart: usage by model

#### 2. Trace Explorer
- Searchable table of all traces
- Filters: model, status (success/error), date range, project
- Click any row → see full prompt, response, latency, cost, evaluation scores

#### 3. Analytics Page
- Cost breakdown by model (pie chart or bar chart)
- Token usage over time (area chart)
- Latency percentiles P50/P95/P99 (line chart)

#### 4. Alerts Page
- List current alert rules
- Form to create a new alert rule (pick type, threshold, channel)
- History of recent alert triggers

#### 5. Settings Page
- Manage API keys (create, revoke)
- Per-project evaluation settings (enable/disable hallucination check, etc.)

### Tech stack:
- **React** (with Vite for build)
- **Recharts** for all charts
- **React Router** for navigation
- **Axios** or `fetch` for API calls

### Files to create:
```
dashboard/
├── package.json
├── vite.config.js
├── index.html
└── src/
    ├── App.jsx
    ├── main.jsx
    ├── api/
    │   └── client.js         ← all calls to query-api
    ├── components/
    │   ├── StatCard.jsx       ← number cards at the top
    │   ├── TraceTable.jsx     ← searchable trace list
    │   └── CostChart.jsx      ← recharts wrapper
    └── pages/
        ├── Overview.jsx
        ├── Traces.jsx
        ├── Analytics.jsx
        ├── Alerts.jsx
        └── Settings.jsx
```

---

## Phase 8 — Load Testing & Hardening ⏳

**In plain English:** Before calling this "production ready," we need to stress-test it — send thousands of fake AI calls and make sure nothing breaks, slows down, or loses data.

The `scripts/` folder already has placeholder files for this.

### What to build:

#### 1. Load Test Script (`scripts/load_test.js`)
Use **k6** (a load testing tool) to simulate real traffic:
- Send 100 traces per second for 5 minutes
- Ramp up to 1000 traces per second
- Record: error rate, p99 latency, throughput

#### 2. Seed Data Script (`scripts/seed_traces.py`)
Generate realistic fake trace data for development and testing:
- Mix of models (GPT-4, Claude, etc.)
- Mix of statuses (success, error)
- Spread over 30 days of history

#### 3. Kubernetes Manifests (`k8s/` folder — already has placeholder folders)
Write deployment YAML files for each service so the app can run on Kubernetes:
```
k8s/
├── api-gateway/
│   └── deployment.yaml
├── ingest-api/
│   └── deployment.yaml
├── kafka-consumer/
│   └── deployment.yaml
└── eval-engine/
    └── deployment.yaml
```

#### 4. Monitoring Setup (`monitoring/` folder)
- **Prometheus** config to scrape metrics from each service
- **Grafana** dashboards for infrastructure health (CPU, memory, Kafka lag)

#### 5. Hardening checklist:
- [ ] Add structured logging (JSON format) to all services
- [ ] Add `/metrics` Prometheus endpoint to ingest-api and query-api
- [ ] Test Kafka consumer crash recovery (kill it mid-run, make sure no data is lost)
- [ ] Add database connection pooling limits
- [ ] Set up health check endpoints on all services
- [ ] Write an end-to-end smoke test (full flow: SDK → Kafka → ClickHouse → Query API)

---

## 📋 Summary Checklist

| Phase | What to build | Key files | Status |
|---|---|---|---|
| **4** | Query & Analytics API | `services/query-api/app/main.py` | ⏳ Not started |
| **5** | Eval Engine (AI scoring) | `services/eval-engine/main.py` | ⏳ Not started |
| **6** | Alerting & Notifications | `services/alert-engine/main.py` | ⏳ Not started |
| **7** | React Dashboard | `dashboard/src/App.jsx` | ⏳ Not started |
| **8** | Load Testing & K8s | `scripts/load_test.js`, `k8s/*.yaml` | ⏳ Not started |

---

## 🔗 How the Phases Connect

```
Phase 4 (Query API)
   ↑ reads from ClickHouse (data written by Phase 3)
   ↑ also needed by Phase 7 (dashboard uses it)

Phase 5 (Eval Engine)
   ↑ reads traces from ClickHouse
   ↓ writes scores back to ClickHouse evaluations table
   ↑ scores shown in Phase 7 dashboard

Phase 6 (Alerting)
   ↑ reads from ClickHouse (costs, latency, evals)
   ↑ reads alert_rules from PostgreSQL
   ↓ sends webhooks/emails when rules trigger

Phase 7 (Dashboard)
   ↑ calls Phase 4 (Query API) for all data
   ↑ shows evaluation scores from Phase 5
   ↑ shows alerts from Phase 6

Phase 8 (Hardening)
   ↑ validates all of the above under load
```

**Recommended order:** 4 → 5 → 6 → 7 → 8

Phase 4 is the most important to do first because Phase 7 (the dashboard) depends entirely on it.

---

## 📁 Directory Map (Current State)

```
Capstone/
├── db/
│   ├── clickhouse/init.sql   ✅ All tables defined (traces, evaluations, MVs)
│   └── postgres/init.sql     ✅ All tables defined (tenants, api_keys, alerts)
├── services/
│   ├── api-gateway/          ✅ Phase 2 — Done
│   ├── ingest-api/           ✅ Phase 2 — Done
│   ├── kafka-consumer/       ✅ Phase 3 — Done
│   └── eval-engine/          ❌ Phase 5 — Empty, needs code
├── sdk/
│   ├── python/               ✅ Phase 2 — Done
│   └── javascript/           ✅ Phase 2 — Done
├── dashboard/                ❌ Phase 7 — Empty, needs React app
├── scripts/
│   ├── verify_ingestion.py   ✅ Phase 3 — Done
│   ├── seed_traces.py        ❌ Phase 8 — Empty placeholder
│   └── load_test.js          ❌ Phase 8 — Empty placeholder
├── monitoring/
│   ├── prometheus/           ❌ Phase 8 — Empty placeholder
│   └── grafana/              ❌ Phase 8 — Empty placeholder
├── k8s/                      ❌ Phase 8 — All empty placeholders
└── docker-compose.yml        ✅ Runs all Phase 1–3 services
```

---

*Last updated: July 2026 — after Phase 3 completion*
*Project: ObserveAI — LLM Observability Platform*
