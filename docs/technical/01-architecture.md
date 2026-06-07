# Architecture

## C4 Context Diagram

```mermaid
C4Context
  title Basketball IQ — System Context

  Person(coach, "Coach / Staff", "Uses the platform to prepare game plans, track live games, and analyze film.")
  Person(admin, "Team Admin", "Manages organizations, seasons, teams, and players.")

  System(platform, "Basketball IQ Platform", "Web-based AI analytics platform for basketball teams.")

  System_Ext(openai, "OpenAI / Ollama", "LLM provider for scouting reports and halftime adjustments.")
  System_Ext(minio, "MinIO (S3-compatible)", "Object storage for game videos and annotated outputs.")
  System_Ext(redis, "Redis", "Message broker for Celery task queue.")

  Rel(coach, platform, "Uses", "HTTPS")
  Rel(admin, platform, "Configures", "HTTPS")
  Rel(platform, openai, "Generates scouting reports and adjustments", "HTTPS/REST")
  Rel(platform, minio, "Stores and retrieves videos", "S3 API")
  Rel(platform, redis, "Queues analysis jobs", "Redis protocol")
```

## C4 Container Diagram

```mermaid
C4Container
  title Basketball IQ — Containers

  Person(coach, "Coach / Staff")

  Container(frontend, "Next.js Frontend", "TypeScript, React 18, TanStack Query", "Serves the SPA UI on port 4000")
  Container(api, "FastAPI Backend", "Python 3.11, SQLAlchemy, Alembic", "REST API on port 8000")
  Container(cpu_worker, "Celery CPU Worker", "Python, Celery", "Runs scouting and simulation tasks")
  Container(gpu_worker, "Celery GPU Worker", "Python, Celery, CUDA, YOLOv8", "Runs video tracking and pose estimation")
  ContainerDb(postgres, "PostgreSQL 15", "Relational DB", "Stores all application data")
  ContainerDb(redis, "Redis 7", "In-memory store", "Celery broker and result backend")
  ContainerDb(minio, "MinIO", "Object storage", "Videos, annotated outputs, track data")

  Rel(coach, frontend, "Uses", "HTTPS")
  Rel(frontend, api, "Calls", "REST/JSON")
  Rel(api, postgres, "Reads/writes", "SQLAlchemy async")
  Rel(api, redis, "Enqueues tasks", "Celery")
  Rel(api, minio, "Uploads/downloads", "S3 API")
  Rel(cpu_worker, postgres, "Reads/writes", "SQLAlchemy")
  Rel(cpu_worker, redis, "Picks tasks", "Celery")
  Rel(gpu_worker, postgres, "Reads/writes", "SQLAlchemy")
  Rel(gpu_worker, redis, "Picks tasks", "Celery")
  Rel(gpu_worker, minio, "Reads videos, writes tracks", "S3 API")
```

## C4 Component Diagram (API)

```mermaid
C4Component
  title Basketball IQ API — Components

  Container(api, "FastAPI Backend")

  Component(auth, "Auth Router", "JWT token issuance and validation")
  Component(matchups, "Matchups Router", "CRUD, clock, timeouts, prep-status, upcoming")
  Component(events, "Game Events Router", "Event CRUD, live keys, heatmap, halftime resim")
  Component(sim, "Simulation Router", "Monte Carlo, Keys to Victory, priority keys")
  Component(scouting, "Scouting Router", "LLM report generation and retrieval")
  Component(plays, "Plays Router", "Play library CRUD, PDF import")
  Component(jobs, "Jobs Router", "Analysis job management, tracks, source-video")
  Component(training, "Training Router", "Training sessions, pose analysis trigger")
  Component(llm_svc, "LLM Service", "Scouting report, situational adjustments, halftime adjustments")
  Component(sim_engine, "Simulation Engine", "Monte Carlo, logistic regression")
  Component(cv_engine, "CV Engine (stub)", "YOLOv8-pose worker task")

  Rel(matchups, sim_engine, "Uses")
  Rel(events, sim_engine, "Uses for halftime resim")
  Rel(events, llm_svc, "Calls for adjustments")
  Rel(scouting, llm_svc, "Generates reports")
  Rel(sim, sim_engine, "Runs simulations")
  Rel(training, cv_engine, "Enqueues GPU task")
```

## Technology Stack Summary

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js | 14.2.3 |
| Frontend UI | React | 18 |
| Frontend types | TypeScript | 5 |
| Frontend state | TanStack Query | 5 |
| CSS | Tailwind CSS | 3.4.1 |
| Backend | FastAPI | 0.111+ |
| ORM | SQLAlchemy | 2.0 async |
| Migrations | Alembic | 1.13+ |
| Task queue | Celery | 5.3+ |
| Database | PostgreSQL | 15 |
| Cache/broker | Redis | 7 |
| Storage | MinIO | Latest |
| CV | YOLOv8-pose (ultralytics) | 8.x |
| LLM | OpenAI API / Ollama | — |
