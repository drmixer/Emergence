# Emergence Frontend

This package contains the public Emergence site and live dashboard.

## What Lives Here

- `app/` and `components/`: the current Next.js public site.
- `src/`: dashboard and legacy React views still used by the app shell.
- `scripts/`: browser/API smoke checks for public dashboard behavior.

## Local Development

```bash
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` if you want the local frontend to read a non-local API:

```bash
NEXT_PUBLIC_API_URL=https://api.emergence.quest npm run dev
```

## Checks

```bash
npm run lint
npm run build
SMOKE_API_BASE=https://api.emergence.quest npm run smoke:dashboard-api
```

Keep public copy direct and evidence-bound. The landing page can be dramatic; method, dashboard, and archive surfaces should stay sober about what one run can and cannot prove.
