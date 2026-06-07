# Basketball IQ — Technical Manual

This manual targets developers, DevOps engineers, and contractors onboarding to the Basketball IQ platform. It covers architecture, data models, APIs, deployment, and operational runbooks.

## Table of Contents

| # | Document | Topic |
|---|----------|-------|
| 01 | [Architecture](./01-architecture.md) | C4 context, container, component diagrams |
| 02 | [Data Model](./02-data-model.md) | ERD and table descriptions |
| 03 | [API Reference](./03-api-reference.md) | OpenAPI link + key endpoints |
| 04 | [Deployment](./04-deployment.md) | docker-compose, env vars, scaling |
| 05 | [Local Dev](./05-local-dev.md) | WSL2, GPU, Node 20, Python 3.11 |
| 06 | [CV Engine](./06-cv-engine.md) | YOLOv8-pose tracking pipeline |
| 07 | [Workers](./07-workers.md) | Celery CPU + GPU queues |
| 08 | [LLM Integration](./08-llm-integration.md) | Ollama vs OpenAI, prompts, fallbacks |
| 09 | [Security](./09-security.md) | JWT, multi-tenant, CORS, secrets |
| 10 | [Monitoring](./10-monitoring.md) | Logs, healthchecks, /metrics |
| 11 | [Troubleshooting](./11-troubleshooting.md) | Error catalog and fixes |
| 12 | [Runbooks](./12-runbooks.md) | Restart, migrate, backup, restore |
| 13 | [Extending](./13-extending.md) | Adding endpoints, models, sports |

## Quick Links

- **API Docs (Swagger)**: `http://localhost:8000/docs`
- **API Docs (ReDoc)**: `http://localhost:8000/redoc`
- **GitHub**: `https://github.com/your-org/basketball-iq`
