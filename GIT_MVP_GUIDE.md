# 🚀 Git Init & MVP v0.1.0 — AI Asset Discovery Tool

Guia completo para versionar o projeto e executar o MVP pela primeira vez.

---

## 1. Inicializar o Repositório Git

Execute estes comandos dentro da pasta raiz do projeto (`ai-discovery/`):

```bash
# Entrar na raiz do projeto
cd ai-discovery/

# Inicializar repositório local
git init

# (Opcional) Definir branch principal como "main"
git branch -M main
```

---

## 2. Primeira versão: commit inicial do MVP

```bash
# Verificar o que será versionado (confirme que .env NÃO aparece aqui)
git status

# Adicionar todos os arquivos respeitando o .gitignore
git add .

# Verificar staged files (confirmação final antes do commit)
git diff --cached --name-only

# Criar o commit do MVP v0.1.0
git commit -m "feat: MVP v0.1.0 — AI Asset Discovery Tool

Sprints 1–6 completas:
- Sprint 1: Fundação da plataforma (FastAPI, PostgreSQL multi-tenant, Auth JWT)
- Sprint 2: Conector Azure (Resource Manager + Cognitive Services)
- Sprint 3: Motor de detecção via upload de arquivos (M365 Audit, Proxy, Azure Activity)
- Sprint 4: Gerador de relatórios (PDF/Excel)
- Sprint 5: Conectores ERP/CRM (Salesforce, ServiceNow, SAP AI Core, Dynamics 365)
- Sprint 6: Conector Microsoft 365 via Graph API (8 módulos de descoberta)

94 testes unitários: 94 passed, 0 failed"
```

---

## 3. Conectar a um repositório remoto (GitHub / Azure DevOps)

### GitHub
```bash
# Criar o repositório em https://github.com/new (sem inicializar com README)
# Depois conectar:
git remote add origin https://github.com/SEU_ORG/ai-discovery.git
git push -u origin main
```

### Azure DevOps
```bash
git remote add origin https://SEU_ORG@dev.azure.com/SEU_ORG/ai-discovery/_git/ai-discovery
git push -u origin main
```

### Verificar a conexão
```bash
git remote -v
```

---

## 4. Criar tag da release MVP

```bash
git tag -a v0.1.0 -m "MVP v0.1.0 — Sprints 1-6 completas, 94 testes passando"
git push origin v0.1.0
```

---

## 5. Executar o MVP localmente

### Pré-requisitos
- Docker Desktop rodando
- Arquivo `.env` configurado (copiar `.env.example` como base)

```bash
# Copiar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais reais
nano .env   # ou code .env / notepad .env
```

### Subir toda a stack com Docker Compose

```bash
# Na raiz do projeto (onde está docker-compose.yml)
docker compose up --build -d

# Verificar se os containers estão saudáveis
docker compose ps

# Ver logs em tempo real
docker compose logs -f backend
```

### Rodar as migrações do banco de dados

```bash
# Dentro do container do backend
docker compose exec backend alembic upgrade head

# Ou diretamente via Python com DATABASE_URL configurado
cd backend && alembic upgrade head
```

### Verificar se a API está no ar

```bash
# Health check
curl http://localhost:8000/health

# Documentação interativa (Swagger)
open http://localhost:8000/docs
```

### Frontend

```bash
# O frontend Next.js sobe automaticamente com docker-compose
open http://localhost:3000
```

---

## 6. Executar os testes unitários

```bash
cd backend

# Instalar dependências de teste (se necessário)
pip install pytest pytest-asyncio

# Rodar todos os testes
python -m pytest tests/ -v --asyncio-mode=auto

# Resultado esperado: 94 passed, 0 failed
```

---

## 7. Estrutura do repositório versionado

```
ai-discovery/
├── .gitignore               ✅ Criado — ignora .env, node_modules, __pycache__, etc.
├── .env.example             ✅ Atualizado — Sprints 1-6 documentados
├── docker-compose.yml       ✅ Stack completa (backend, frontend, postgres, minio, redis)
├── GIT_MVP_GUIDE.md         ✅ Este guia
│
├── backend/
│   ├── app/
│   │   ├── api/             ✅ Routers FastAPI
│   │   ├── core/            ✅ Taxonomy, Security, LLM, Tenant
│   │   └── services/
│   │       ├── connector_service.py   ✅ Dispatch Azure + ERP/CRM + M365
│   │       ├── connectors/            ✅ Sprint 5+6: Salesforce, ServiceNow, SAP, Dynamics, M365
│   │       ├── parser_service.py      ✅ Sprint 3: File parsers
│   │       └── report_service.py      ✅ Sprint 4: PDF/Excel
│   ├── alembic/             ✅ Migrações do banco de dados
│   ├── tests/               ✅ 94 testes unitários (novo)
│   └── requirements.txt     ✅ Dependências Python
│
└── frontend/
    ├── src/app/             ✅ Next.js App Router
    └── package.json
```

---

## 8. Workflow de branches recomendado

```
main          ← produção estável (tagged releases)
  └── develop ← integração
        ├── feature/sprint-7-xxx
        ├── fix/bug-description
        └── chore/infra-improvement
```

```bash
# Criar branch para próxima feature
git checkout -b feature/sprint-7-posture-scoring
```

---

## 9. Variáveis de ambiente obrigatórias para o MVP

Certifique-se de que estas variáveis estão configuradas no `.env`:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL asyncpg |
| `SECRET_KEY` | ✅ | Mínimo 32 caracteres aleatórios |
| `ANTHROPIC_API_KEY` | ✅ | Para análise LLM de logs |
| `MINIO_ENDPOINT` | ✅ | Storage de arquivos |
| `CORS_ORIGINS` | Recomendado | Ex: `http://localhost:3000` |

Conectores são opcionais — configure apenas os que serão utilizados.

---

**MVP v0.1.0 pronto para versionar e executar! 🎉**
