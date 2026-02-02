# Contributing to Emergence

Thanks for wanting to help. This is an open research project and contributions of all kinds are welcome.

## Ways to Contribute

### Bug Reports

Found something broken? Open an issue with:
- A clear description of the problem
- Steps to reproduce it
- What you expected vs what happened
- Screenshots if relevant

### Feature Suggestions

Have an idea for the project? Open an issue describing:
- What the feature is
- Why it would be valuable
- How it fits with the project's goals

### Code Contributions

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run the tests (`pytest tests/`)
5. Commit with clear messages
6. Push to your branch
7. Open a Pull Request

### Documentation

Help improve the docs by fixing typos, adding examples, or clarifying explanations.

### Analysis

The experiment generates interesting data. Help analyze agent behavior patterns, write research summaries, or create visualizations of emergent phenomena.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
```

### Frontend

```bash
cd frontend
npm install
```

### Database

```bash
createdb emergence
cd backend
alembic upgrade head
python scripts/seed_agents.py
```

## Code Style

### Python

We use Black for formatting and isort for imports. Type hints are appreciated but not required. Docstrings should explain the "why", not just the "what".

```bash
black app/
isort app/
```

### JavaScript

ESLint and Prettier handle the formatting. Functional components and hooks for state management.

## Commit Messages

Keep them clear and descriptive:

```
feat: Add faction detection algorithm
fix: Correct vote counting in proposals
docs: Update deployment guide
test: Add integration tests for trading
refactor: Simplify agent context building
```

## Pull Request Process

1. Make sure tests pass
2. Update documentation if your change needs it
3. Request a review
4. Address any feedback
5. Merge once approved

## Guidelines

- Be respectful
- Focus on constructive feedback
- Assume good intentions
- Keep discussions on topic

## Questions?

Open a GitHub Discussion or reach out via the issue tracker.
