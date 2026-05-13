# HireSense AI

Production-grade AI Hiring Intelligence Platform for resume screening, recruiter search, explainable scoring, and fairness-aware candidate ranking.

[FastAPI](https://fastapi.tiangolo.com) · React + Vite · PyTorch · PostgreSQL · Redis · Celery · Ollama · FAISS · Prometheus · Grafana

## What It Does

HireSense AI turns unstructured resumes into structured hiring intelligence.

- JWT authentication with refresh tokens and role-based access control
- Semantic resume-job matching using SentenceTransformers embeddings when available, with a deterministic fallback
- Vector search for candidate discovery and similarity search
- Retrieval-augmented explanations grounded in resume evidence
- Real resume parsing for skills, projects, education, certifications, and contact data
- Realtime screening updates over WebSockets
- Premium recruiter dashboard with live analytics and fairness insights
- Production deployment with Docker Compose, Nginx, metrics, and CI

## Architecture

```text
┌────────────────────────────── HireSense AI ──────────────────────────────┐
│                                                                         │
│  React + Vite UI                                                        │
│  ├─ recruiter dashboard                                                 │
│  ├─ analytics and candidate detail views                                │
│  └─ realtime WebSocket updates                                          │
│                                                                         │
│  FastAPI API                                                            │
│  ├─ auth, RBAC, refresh tokens                                          │
│  ├─ resume/job CRUD                                                     │
│  ├─ screening orchestration                                             │
│  └─ health + metrics                                                    │
│                                                                         │
│  Celery workers                                                         │
│  ├─ resume parsing                                                      │
│  ├─ hybrid scoring                                                      │
│  └─ LLM explanation generation                                          │
│                                                                         │
│  AI layer                                                               │
│  ├─ PyTorch classifier                                                  │
│  ├─ SentenceTransformers embeddings with fallback hashing              │
│  ├─ FAISS vector store                                                  │
│  └─ Mistral-7B via Ollama                                               │
│                                                                         │
│  PostgreSQL  ·  Redis  ·  Prometheus  ·  Grafana  ·  Nginx              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Features

### Authentication & Security

- JWT access tokens and refresh tokens
- Recruiter and admin RBAC
- Password hashing with PBKDF2-HMAC-SHA256
- Protected API routes and websocket auth
- Redis-backed rate limiting
- Environment-driven configuration

### AI & Matching

- SentenceTransformers semantic embeddings when installed, with a fallback hashing index
- FAISS-backed vector search with memory fallback
- Hybrid scoring across skills, experience, education, and semantic similarity
- Candidate similarity search
- Natural-language recruiter search, for example:
  - `Find candidates with FastAPI + PyTorch + Docker experience`

### RAG Explainability

- Retrieve supporting candidate context before generating explanations
- Ground LLM output in resume evidence
- Score breakdowns and confidence values
- Bias keyword detection and fairness flags

### Resume Parsing

- PDF, DOCX, and plain-text extraction
- Skills, education, certifications, projects, experience duration
- Email, phone, GitHub, and LinkedIn extraction
- Semantic summary generation for downstream retrieval

### Frontend

- Dark/light mode
- Recruiter dashboard
- Analytics and candidate leaderboard
- Responsive cards, tables, and charts
- Loading states and realtime progress

### DevOps

- Docker Compose production stack
- Isolated Flower monitoring image with only broker and Celery tooling
- Nginx reverse proxy
- Health checks
- Prometheus metrics and Grafana dashboards
- GitHub Actions CI with backend checks and frontend build

## Folder Structure

```text
hiresense-ai/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── workers/
│   ├── tasks/
│   ├── celery_app.py
│   ├── Dockerfile
│   └── requirements.txt
├── flower/
│   ├── Dockerfile
│   └── requirements.txt
├── ai_models/
│   ├── inference/
│   ├── trainer/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── vite.config.js
│   └── package.json
├── monitoring/
├── nginx/
├── scripts/
├── constraints.txt
└── docker-compose.yml
```

## Step-by-Step Runbook

### 1) Configure environment

```bash
cp .env.example .env
```

Set at minimum:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `INITIAL_ADMIN_PASSWORD`
- `VITE_API_URL`

### 2) Start the stack

```bash
docker compose up --build
```

Optional monitoring profile:

```bash
docker compose --profile monitoring up --build
```

### 3) Pull the LLM model

If you want Mistral-based explanations:

```bash
docker compose exec ollama ollama pull mistral:7b
```

### 4) Open the app

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/api/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`
- Flower: `http://localhost:5555`

## Local Development

### Backend

```bash
cd backend
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Workers

```bash
cd workers
celery -A celery_app worker --loglevel=info
```

## API Overview

### Auth

- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/auth/bootstrap`

### Jobs

- `POST /api/jobs/`
- `GET /api/jobs/`
- `GET /api/jobs/{id}`
- `PATCH /api/jobs/{id}`
- `DELETE /api/jobs/{id}`

### Resumes

- `POST /api/resumes/upload`
- `POST /api/resumes/upload-batch`
- `GET /api/resumes/`
- `GET /api/resumes/{id}`
- `DELETE /api/resumes/{id}`

### Screening

- `POST /api/screening/`
- `GET /api/screening/{job_id}/results`
- `GET /api/screening/result/{screening_id}`
- `GET /api/screening/stats/{job_id}`
- `GET /api/screening/similarity/{resume_id}`
- `POST /api/screening/search`

### Realtime

- `WS /ws/screening/{job_id}`
- `WS /ws/notifications`

## Database Model

### `users`

- recruiter/admin identity
- password hash
- active/verified flags

### `refresh_tokens`

- hashed refresh token storage
- revocation and expiration tracking

### `jobs`

- role description, required skills, preferred skills
- semantic summary and searchable document
- recruiter ownership

### `resumes`

- parsed contact data
- extracted skills, education, certifications, projects
- semantic summary and parse confidence

### `screenings`

- hybrid score breakdown
- semantic score and confidence score
- retrieved context for RAG
- explainability payload and fairness flags

## AI Pipeline

1. Resume upload lands in FastAPI
2. Celery parses PDF/DOCX content and extracts structured fields
3. Resume and job are embedded with SentenceTransformers when available, otherwise a deterministic hashing fallback is used
4. Vector store retrieves similar candidates and context
5. Hybrid scorer combines semantic, skill, education, and experience signals
6. Ollama/Mistral generates a grounded explanation
7. Results stream to the dashboard over WebSockets

## Deployment Notes

- Backend container exposes `/health` and `/metrics`
- Nginx proxies API, websockets, Flower, Grafana, and the SPA
- Redis powers Celery, rate limiting, and realtime pub/sub
- PostgreSQL persists users, jobs, resumes, screenings, and tokens
- `app_data` persists vector index files and other semantic search artifacts
- Monitoring services can be enabled with the `monitoring` profile

## CI

GitHub Actions runs:

- backend compile and lint checks
- backend tests
- frontend build

## Environment Example

See [.env.example](./.env.example) for the full set of supported configuration values.

## Resume-Worthy Highlights

- Built a fairness-aware AI hiring platform with semantic retrieval and RAG explanations
- Added JWT auth, refresh tokens, RBAC, and rate limiting for production readiness
- Implemented realtime candidate screening updates with WebSockets and Celery
- Designed a modern SaaS recruiter UI with charts, analytics, and dark/light themes
- Containerized the full stack with observability and CI

## License

MIT
