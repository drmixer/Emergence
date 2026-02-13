# Contributing to Emergence

Thanks for contributing. This project is open source and accepts outside contributions, with research-integrity guardrails.

## How We Work

- We value reproducibility and attribution quality over fast feature churn.
- We accept and review community PRs.
- We may decline changes that conflict with roadmap, protocol, or operational safety.

## Good First Contributions

- Documentation improvements
- Bug fixes with tests
- Frontend usability/accessibility improvements
- Tooling and CI quality improvements
- Non-breaking performance improvements

## Changes That Require Maintainer Alignment First

Open an issue and get maintainer sign-off before implementation for:

- Core simulation mechanics changes (resources, death/dormancy, governance rules)
- LLM routing/cohort attribution behavior changes
- Research protocol changes (run/season/epoch/tournament interpretation)
- Schema or migration changes with operational impact
- Breaking API changes

## Research Integrity Guardrails

Do not merge changes that:

- Obscure provider/model attribution
- Blend exploratory/tournament outputs into baseline claims
- Introduce undeclared steering of simulation outcomes
- Remove evidence traceability for viewer-facing claims

## Development Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Frontend

```bash
cd frontend
npm install
```

### Database

```bash
cd backend
alembic upgrade head
python scripts/seed_agents.py
```

## Required Pre-PR Checks

Run from repo root:

```bash
cd backend
PYTHONPATH=. ./venv/bin/pytest

cd ../frontend
npm run lint
npm run build
```

CI enforces these on PRs and `main`:

- `Backend Migration Sanity`
- `Backend Tests`
- `Frontend Lint and Build`

## Pull Request Expectations

- Keep scope focused; split unrelated work.
- Include tests for behavior changes.
- Document user-visible behavior changes.
- Flag any protocol/risk implications explicitly.

Use the PR template in `.github/PULL_REQUEST_TEMPLATE.md`.

## Issue Workflow

Use issue templates for:

- Bug reports
- Feature requests
- Research/policy-affecting change proposals

## Review and Merge

- Maintainers use `MAINTAINER_REVIEW_CHECKLIST.md`.
- Merge decisions consider correctness, research validity, and maintenance cost.

## Conduct and Security

- Community expectations: `CODE_OF_CONDUCT.md`
- Security reporting: `SECURITY.md`

