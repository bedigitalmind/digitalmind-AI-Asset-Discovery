# AI Asset Discovery Tool

**Digital Mind** — Sprint 1 MVP

Plataforma multi-tenant para descoberta e mapeamento de assets de IA na infraestrutura de clientes.

## Quick Start

1. **Clone e configure**
   ```bash
   cp .env.example .env
   # Edite .env conforme necessário
   ```

2. **Suba a stack**
   ```bash
   docker compose up --build
   ```

3. **Crie o admin e o workspace demo**
   ```bash
   docker compose exec backend python seed.py
   ```

4. **Acesse**
   - Frontend: http://localhost:3000
   - API (Swagger): http://localhost:8000/docs
   - MinIO Console: http://localhost:9001 (minioadmin / minioadmin)

5. **Login**
   - Email: `admin@digitalmind.com.vc`
   - Senha: `changeme123`

## Arquitetura

Ver documento: `AI_Asset_Discovery_Arquitetura_v1.0.docx`

## Stack (Sprint 1)

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) |
| Banco de dados | PostgreSQL 16 (schema-per-tenant) |
| File storage | MinIO (S3-compatible) |
| Auth | JWT (python-jose + bcrypt) |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Container | Docker Compose |

## Estrutura do Projeto

```
ai-discovery/
├── backend/          # FastAPI application
│   ├── app/
│   │   ├── core/     # Config, DB, Security, Tenant
│   │   ├── models/   # SQLAlchemy models
│   │   ├── schemas/  # Pydantic schemas
│   │   ├── routers/  # API endpoints
│   │   └── services/ # Business logic
│   └── alembic/      # Database migrations
├── frontend/         # Next.js 14 application
│   └── src/
│       ├── app/      # Pages (App Router)
│       ├── components/
│       └── lib/      # API client, auth utils
├── infra/
│   └── postgres/     # Init SQL
└── docker-compose.yml
```

## Próximas Sprints

- **Sprint 2**: Dashboard de clientes, conectores cloud (AWS/Azure), taxonomy de IA
- **Sprint 3**: Detecção de IA conversacional e APIs
- **Sprint 4**: IA em ERP/CRM, scoring de risco
