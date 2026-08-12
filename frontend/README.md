# Ferrox Product Intelligence UI

This is the Next.js + TypeScript frontend direction for Ferrox. It starts with a high-impact landing page and a small live backend check, while keeping the API contract visible for the future product UI.

## Why This Direction

The downloaded UI catalog is used only as visual reference. The actual Ferrox frontend lives here and is pushed to the Ferrox repo. The direction borrows from strong SaaS/product-intelligence landing pages: dark technical atmosphere, sharp product mockups, clear proof points, and a visible backend contract.

The page is designed to explain the platform before the fuller app is built:

- source ingestion across PDF, URL, and raw text
- category-aware extraction schemas
- explicit reconciliation for conflicts
- validation, enrichment, confidence, completeness, and review queue
- backend API readiness

## Run

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:3000`.

## Backend Contract

The UI is wired to the current Ferrox API shape:

- `GET /api/v1/health`
- `POST /api/v1/products/ingest/text`
- `POST /api/v1/products/{product_id}/pipeline`
- `GET /api/v1/reviews`
- `GET /api/v1/batches`
- `PATCH /api/v1/products/{product_id}/fields/{field_name}`

If `INTERNAL_API_KEY` is configured on the backend, enter it in the UI's Internal key field.
