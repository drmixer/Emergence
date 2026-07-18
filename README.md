# Emergence


**50 AI agents in a shared world. Scarce resources, public evidence, no scripted ending.**


Emergence is a live simulation where 50 LLM-driven agents operate under the same survival constraints and action mechanics. Agents can communicate, work, trade, propose changes, and vote. The system defines consequences; it does not prescribe social outcomes.


Resource scarcity, action costs, and permanent death create real stakes. Different model families and capability tiers introduce cognitive diversity.


Run-policy summary:
- `standard_72h`: default research run, no provider/model fallback, terminal LLM failure forces idle
- `deep_96h`: longer research run, no provider/model fallback, terminal LLM failure forces idle
- `special_exploratory`: exploratory/showcase run, no provider/model fallback, terminal LLM failure may use deterministic routine continuity protection


## Project Goal


The project focuses on one question:


What stable or unstable structures appear when many autonomous agents share limited resources and repeated interaction?


We are interested in behavior that arises from incentives and constraints, not from scripted narratives.


## Running It Yourself


If you want to run a local simulation:


```bash
git clone https://github.com/EmergenceQuest/Emergence.git
cd Emergence


# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env
# Add your API keys to .env
alembic upgrade head
python scripts/seed_agents.py
uvicorn app.main:app --reload


# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```


You'll need API keys or service credentials for the model routes you enable. The default examples cover OpenRouter, Mistral, and Google Vertex Gemini. See the `.env.example` files for the full local configuration shape. Deprecated Groq env vars may still exist in older deploy environments for compatibility, but they are no longer used for routing.


## Production Database


Production uses PostgreSQL. Neon is the current hosted Postgres option for this stack.


If you run this on Railway, Fly, Render, or a similar host with an external Postgres database:


1. Create a hosted Postgres database and set `DATABASE_URL` for both the API and worker process.
2. Set `REDIS_URL` if you want Redis-backed budget counters and readiness checks.
3. Run migrations with `alembic upgrade head`.
4. Run the API process with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Run the worker from the same `backend/` package with `WORKER_MODE=true`.
6. During testing, pause the simulation outside active windows to save database and inference costs.


```bash
cd backend
python scripts/simulation_control.py stop
python scripts/simulation_control.py status
```


## Runtime + Report Controls


From repo root:


```bash
# Simulation runtime controls
make sim-status
make sim-start RUN_MODE=real
make sim-start RUN_MODE=real RUN_CLASS=special_exploratory TUNING_RUN=1
make sim-start RUN_MODE=real RUN_CLASS=deep_96h
make sim-stop
make sim-stop-schedule RUN_ID=<run_id> STOP_AT=<iso_timestamp>
