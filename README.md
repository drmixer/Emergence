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

You'll need API keys for OpenRouter or Groq to power the LLMs. See the `.env.example` files for what's required.

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL, Redis
- **Frontend:** React, Vite
- **LLMs:** OpenRouter, Groq
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
