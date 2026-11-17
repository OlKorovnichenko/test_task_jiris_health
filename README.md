# Jiris Health test task

## Run

Copy `.env.example` to `.env` if you don't have one, then run:

```bash
docker compose up -d db kafka
docker compose build
docker compose run --rm api alembic upgrade head
docker compose up -d api outbox billing
```

## API documentation

Open [Swagger UI](http://localhost:8000/docs).

## Tests

Requires Python 3.14 and Poetry. Create the test database once:

```bash
poetry install --with dev --no-root
docker compose up -d db
docker compose exec db psql -U postgres -d postgres -c 'CREATE DATABASE jiris_health_test'
```

Apply migrations and run the tests:

```bash
POSTGRES_DB=jiris_health_test poetry run alembic upgrade head
POSTGRES_DB=jiris_health_test poetry run pytest -v
```
