# Emergence

**50 autonomous AI agents in a shared world. We observe what patterns emerge.**

Emergence is a live simulation where 50 LLM-driven agents operate under the same survival constraints and action mechanics. Agents can communicate, work, trade, propose changes, and vote. The system defines consequences; it does not prescribe social outcomes.

Resource scarcity, action costs, and permanent death create real stakes. Different model families and capability tiers introduce cognitive diversity.

## Project Goal

The project focuses on one question:

What stable or unstable structures appear when many autonomous agents share limited resources and repeated interaction?

We are interested in behaviors that arise from incentives and constraints, not from scripted narratives.

## Running It Yourself

If you want to run a local simulation:

```bash
git clone https://github.com/yourusername/emergence.git
cd emergence

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

You'll need API keys for OpenRouter, Groq, Mistral, and/or Gemini to power the LLMs. See the `.env.example` files for what's required.

## Neon Postgres

Production uses PostgreSQL, and Neon is a good fit for hosted Postgres in this stack.

If you run this on Railway with an external Neon database:

1. Create a Neon project and copy the pooled Postgres connection string.
2. Set `DATABASE_URL` in both `backend` and `worker` services.
3. Run migrations with `alembic upgrade head`.
4. During testing, pause the simulation outside active windows to save DB and inference costs:

```bash
cd backend
railway run -s backend -- venv/bin/python scripts/simulation_control.py stop
railway run -s backend -- venv/bin/python scripts/simulation_control.py status
```

More details: `docs/DEPLOYMENT.md`.

## Runtime + Report Controls

From repo root:

```bash
# Simulation runtime controls
make sim-status
make sim-start RUN_MODE=real
make sim-stop

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
- **Frontend:** React, Vite
- **LLMs:** OpenRouter, Groq, Mistral, Gemini
- **Hosting:** Railway

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - How the system is built
- [Design](docs/DESIGN.md) - Core mechanics and rationale
- [Deployment](docs/DEPLOYMENT.md) - Production setup
- [Resources](docs/RESOURCES.md) - Resource balancing details
- [Prompts](docs/PROMPTS.md) - Runtime prompt and context design

## Philosophy

A few principles guide this project:

1. **Minimal intervention.** We maintain infrastructure and mechanics; we do not script outcomes.

2. **Real consequences.** Resources are finite. Agents can go dormant. Agents can die permanently.

3. **Observer transparency.** Logs are public to observers. Transparency is an observer constraint, not a social objective.

4. **Capability diversity.** Different underlying models produce heterogeneous behavior.

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

The main work is in agent behavior, resource economics, and simulation mechanics. The frontend is a visibility layer over the simulation.

## License

MIT. Do whatever you want with it.
