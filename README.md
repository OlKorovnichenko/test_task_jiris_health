# Jiris Health test task

## Run

Requires Docker and Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d
```

Migrations run automatically. Swagger is available at http://localhost:8000/docs.
The database starts empty. To add demo visits:

```bash
docker compose exec api python -m scripts.seed_visits
```

Complete an In Progress visit with `POST /api/visits/{id}/complete`.

## Tests

```bash
docker compose --profile test run --build --rm tests
```

This runs pytest against a separate PostgreSQL database. Kafka tests use
`TestKafkaBroker`, so a running Kafka broker is not needed.

## Migrations

To apply migrations manually and check that they match the models:

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic check
```

To roll back the last migration:

```bash
docker compose exec api alembic downgrade -1
```

## Architecture

The app is a modular monolith built with FastAPI, PostgreSQL and Kafka.
Visits and Billing have their own tables and communicate through events.
Visit completion uses a row lock and saves the event in an outbox in the same
transaction. A worker retries publication if Kafka is unavailable, and Billing
deduplicates events and allows only one active bill per visit.
