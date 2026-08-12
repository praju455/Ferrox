# Ferrox Frontend

The Ferrox frontend is a Next.js + TypeScript landing experience for the Industrial Product Intelligence Platform. It explains the product through the actual workflow: source ingestion, evidence-backed extraction, reconciliation, validation, human review, and the existing backend contract.

## Design Direction

The local `front/` repository is used only as a design catalog. No catalog code or remote history is included in Ferrox, and nothing is pushed to the catalog repository.

The current visual system combines the most relevant ideas from these catalog entries:

- `DFZ9GE6` - AI Factory: product-led hero composition and dark inspection surfaces.
- `SD3TBY5` - Autonomous Data Dashboard: dense technical information and operational status language.
- `U4FIIUM` - Interactive Database Schema: visible data relationships and system structure.
- `7SZDVGF` - Audit Results Dashboard: evidence-first review patterns and clear issue hierarchy.

The result is specific to Ferrox: graphite machinery photography, safety-orange action color, off-white catalog surfaces, source authority labels, field-level evidence, and a working review comparison. The original pump hero image was generated for this project and lives in `public/ferrox-industrial-pump.jpg`.

## Experience Map

```mermaid
flowchart LR
    Hero["Landing hero\nindustrial pump + live source inspector"] --> Platform["Platform workflow\ningest to validate"]
    Platform --> Evidence["Canonical record\nconfidence + field evidence"]
    Evidence --> Review["Human review\ncompare conflicting values"]
    Review --> Contract["Developer contract\ncurrent backend endpoints"]
    Contract --> Connect["Live connection check\nAPI base + optional internal key"]

    Inspector["PDF / URL / text tabs"] --> Hero
    Backend["FastAPI /api/v1/health"] --> Connect
```

## Run

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:3000`.

## Backend Contract

The landing page uses the current Ferrox API shape:

- `GET /api/v1/health`
- `POST /api/v1/products/ingest/text`
- `POST /api/v1/products/{product_id}/pipeline`
- `GET /api/v1/reviews`
- `GET /api/v1/batches`
- `PATCH /api/v1/products/{product_id}/fields/{field_name}`

The connection check stores its API base and optional internal key in browser-local storage only.
