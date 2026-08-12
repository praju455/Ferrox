# Ferrox Product Intelligence UI

This is the selected UI/UX direction for the Ferrox backend: an operational SaaS dashboard for catalog operations teams.

It is placed inside the UI catalog repo as a dedicated project so the original template catalog remains untouched.

## Why This Direction

The catalog contains several relevant dashboard/SaaS references, especially AI admin, developer dashboard, operational SaaS, infrastructure dashboard, and cyber/security dashboard styles. For Ferrox, the strongest fit is not a marketing landing page or a neon game-style UI. The product needs a dense, calm, high-trust command center where users can:

- ingest source evidence
- run extraction
- see pipeline progress
- inspect source conflicts
- correct fields
- monitor batches
- understand backend API state

## Run

```bash
npm run dev
```

Open `http://127.0.0.1:5173`.

## Backend Contract

The UI is wired to the current Ferrox API shape:

- `GET /api/v1/health`
- `POST /api/v1/products/ingest/text`
- `POST /api/v1/products/{product_id}/pipeline`
- `GET /api/v1/reviews`
- `GET /api/v1/batches`
- `PATCH /api/v1/products/{product_id}/fields/{field_name}`

If `INTERNAL_API_KEY` is configured on the backend, enter it in the UI’s Internal key field.
