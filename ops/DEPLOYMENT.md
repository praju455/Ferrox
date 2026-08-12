# Ferrox Deployment Runbook

## Release

1. Provide `POSTGRES_PASSWORD`, a random 32+ character `JWT_SECRET`, and private S3 credentials through the deployment secret manager.
2. Set provider keys only for enabled providers. Keep `LLM_PROVIDER_ORDER=gemini,groq,openai`.
3. Run `docker compose -f docker-compose.production.yml up -d --build`.
4. Confirm `/api/v1/health/live`, `/api/v1/health/ready`, and the Prometheus target at port 9090.
5. Bootstrap the first admin from the API image, then remove the bootstrap password from the environment.

```bash
docker compose -f docker-compose.production.yml exec api python -m app.bootstrap_admin
```

Use a TLS reverse proxy or managed ingress in front of ports 3000 and 8000. Do not expose PostgreSQL, MinIO, or the Prometheus endpoint publicly. For a managed deployment, replace the included PostgreSQL and MinIO services with managed PostgreSQL and private S3-compatible storage.

## Monitoring

Prometheus scrapes request rate/latency and LLM calls, latency, tokens, errors, and configured cost estimates. Alert on readiness failure, worker restarts, batch/pipeline failures, elevated HTTP 5xx responses, LLM fallback/error rate, and backup job failures. Ship container logs to the deployment log platform and retain request IDs.

## Backups

The `backup` service runs `pg_dump` every `BACKUP_INTERVAL_SECONDS`, uploads the custom-format dump through the configured object storage backend, and keeps `BACKUP_RETENTION_COUNT` newest objects. S3 encryption remains enabled by `S3_SERVER_SIDE_ENCRYPTION`.

Run an immediate backup:

```bash
docker compose -f docker-compose.production.yml exec backup python -m app.backup
```

Restore only into an isolated recovery database first. The command requires an explicit confirmation phrase and runs `pg_restore --clean --if-exists`:

```bash
docker compose -f docker-compose.production.yml exec api python -m app.restore \
  --key backups/postgres/ferrox-YYYYMMDDTHHMMSSZ.dump \
  --confirm RESTORE_DATABASE
```

Perform a restore drill at least monthly. For managed PostgreSQL, also enable provider-native point-in-time recovery and cross-region snapshot retention; the application dump is a portable second recovery path.
