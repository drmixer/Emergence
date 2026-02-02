# Railway Deployment Guide

## Architecture on Railway

```
┌─────────────────────────────────────────────────────────┐
│                    Railway Project                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Backend    │  │   Frontend   │  │   Worker     │  │
│  │   (FastAPI)  │  │   (Vite)     │  │   (Agents)   │  │
│  │   Port 8000  │  │   Port 3000  │  │   No Port    │  │
│  └──────┬───────┘  └──────────────┘  └──────┬───────┘  │
│         │                                    │          │
│         └──────────────┬─────────────────────┘          │
│                        │                                 │
│         ┌──────────────┴──────────────┐                 │
│         │                             │                 │
│  ┌──────▼──────┐              ┌───────▼─────┐          │
│  │  PostgreSQL │              │    Redis    │          │
│  │  (Database) │              │   (Cache)   │          │
│  └─────────────┘              └─────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Project Structure for Railway

```
emergence/
├── backend/
│   ├── app/
│   ├── alembic/
│   ├── requirements.txt
│   ├── Procfile           # Railway process file
│   └── railway.json       # Backend config
├── frontend/
│   ├── src/
│   ├── package.json
│   └── railway.json       # Frontend config
├── worker/
│   ├── main.py
│   ├── requirements.txt
│   └── railway.json       # Worker config
└── railway.json           # Root project config
```

---

## Environment Variables

### Backend Service
```bash
# Database (auto-provided by Railway PostgreSQL)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (auto-provided by Railway Redis)
REDIS_URL=${{Redis.REDIS_URL}}

# LLM APIs
OPENROUTER_API_KEY=sk-or-...
GROQ_API_KEY=gsk_...

# App settings
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info
SECRET_KEY=<generate-random-64-char-string>

# CORS
FRONTEND_URL=https://your-frontend.up.railway.app
```

### Worker Service
```bash
# Same database and redis
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

# LLM APIs
OPENROUTER_API_KEY=sk-or-...
GROQ_API_KEY=gsk_...

# Worker settings
WORKER_MODE=true
AGENT_LOOP_DELAY=150
SIMULATION_ACTIVE=true
```

### Frontend Service
```bash
VITE_API_URL=https://your-backend.up.railway.app
```

---

## Configuration Files

### Backend Procfile (`backend/Procfile`)
```
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Backend railway.json (`backend/railway.json`)
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Worker railway.json (`worker/railway.json`)
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10,
    "startCommand": "python main.py"
  }
}
```

### Frontend railway.json (`frontend/railway.json`)
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "npm run build"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE"
  }
}
```

---

## Step-by-Step Deployment

### 1. Create Railway Project
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Create new project
railway init
```

### 2. Add PostgreSQL
```bash
# Add PostgreSQL database
railway add --database postgres

# This automatically sets DATABASE_URL
```

### 3. Add Redis
```bash
# Add Redis cache
railway add --database redis

# This automatically sets REDIS_URL
```

### 4. Deploy Backend
```bash
cd backend

# Link to Railway
railway link

# Set environment variables
railway variables set OPENROUTER_API_KEY=sk-or-...
railway variables set GROQ_API_KEY=gsk_...
railway variables set SECRET_KEY=$(openssl rand -hex 32)
railway variables set ENVIRONMENT=production

# Deploy
railway up
```

### 5. Run Database Migrations
```bash
# Run migrations on Railway
railway run alembic upgrade head

# Seed agents
railway run python scripts/seed_agents.py
```

### 6. Deploy Worker
```bash
cd ../worker

# Create new service in same project
railway link

# Set same environment variables
railway variables set OPENROUTER_API_KEY=sk-or-...
railway variables set GROQ_API_KEY=gsk_...
railway variables set WORKER_MODE=true
railway variables set SIMULATION_ACTIVE=false  # Start paused

# Deploy
railway up
```

### 7. Deploy Frontend
```bash
cd ../frontend

# Link to Railway
railway link

# Set API URL (get from backend service)
railway variables set VITE_API_URL=https://your-backend.up.railway.app

# Deploy
railway up
```

### 8. Configure Domain
```bash
# For backend API
railway domain add api.emergence.quest

# For frontend
railway domain add emergence.quest
```

---

## Monitoring

### View Logs
```bash
# Backend logs
railway logs -s backend

# Worker logs
railway logs -s worker
```

### Health Checks

Backend health endpoint:
```
GET https://api.emergence.quest/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "active_agents": 100,
  "simulation": "running"
}
```

---

## Scaling

### Increase Worker Replicas
```json
// worker/railway.json
{
  "deploy": {
    "numReplicas": 2  // Run 2 worker instances
  }
}
```

### Database Connection Pooling
```python
# backend/app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)
```

---

## Backup Strategy

### Automatic Backups
Railway PostgreSQL includes automatic daily backups.

### Manual Backup
```bash
# Export database
railway run pg_dump -Fc > backup_$(date +%Y%m%d).dump

# Restore
railway run pg_restore -d $DATABASE_URL backup_20250201.dump
```

---

## Cost Estimation

| Service | Estimated Cost/Month |
|---------|---------------------|
| Backend | $5-10 |
| Worker | $5-10 |
| Frontend | $0-5 |
| PostgreSQL | $5-10 |
| Redis | $5-10 |
| **Total** | **$20-45** |

With higher traffic:
- Scale backend to 2 replicas: +$5-10
- Larger database: +$10-20
- **Peak estimate**: $50-75/month
