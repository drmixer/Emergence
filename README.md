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
git clone https://github.com/drmixer/Emergence.git
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
make sim-stop-unschedule

# Local macOS launchd fallback if you explicitly want a machine-local guard
make sim-stop-schedule-local RUN_ID=<run_id> STOP_AT=<iso_timestamp>
make sim-stop-unschedule-local RUN_ID=<run_id>

# Run-scoped research outputs
make report-rebuild RUN_ID=run-20260210T120000Z
make report-tech RUN_ID=run-20260210T120000Z
make report-story RUN_ID=run-20260210T120000Z
make report-plan RUN_ID=run-20260210T120000Z
make report-export RUN_ID=run-20260210T120000Z
make compare-condition CONDITION=baseline_v1
```

Report artifacts are written under `output/reports/runs/<run_id>/` and indexed in `run_report_artifacts`.

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL, Redis
- **Database Hosting:** Neon (production-ready option)
- **Frontend:** Next.js + React
- **LLMs:** OpenRouter, Mistral, Google Vertex Gemini
- **Hosting:** Railway

## Documentation

- [Run Lifecycle Protocol](docs/RUN_LIFECYCLE_PROTOCOL.md) - Canonical run/season/epoch/tournament policy
- [Resources](docs/RESOURCES.md) - Public summary of scarcity and survival mechanics

Operational runbooks, tuning notes, and planning memos are kept out of the public documentation set unless they are intentionally prepared for release.

## Philosophy

A few principles guide this project:

1. **Minimal intervention.** We maintain infrastructure and mechanics; we do not script outcomes.

2. **Real consequences.** Resources are finite. Agents can go dormant. Agents can die permanently.

3. **Observer transparency.** Logs are public to observers. Transparency is an observer constraint, not a goal assigned to the agents.

4. **Capability diversity.** Different underlying models produce heterogeneous behavior.

5. **Attribution integrity.** We do not silently remap agents onto a different provider/model mid-run; unknown model assignments are treated as configuration errors.

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

The main work is in agent behavior, resource economics, and simulation mechanics. The frontend is a visibility layer over the simulation.

## Community and Policy

- [Contributing Guide](CONTRIBUTING.md)
- [Governance](GOVERNANCE.md)
- [Maintainer Review Checklist](MAINTAINER_REVIEW_CHECKLIST.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## License

MIT. Do whatever you want with it.
