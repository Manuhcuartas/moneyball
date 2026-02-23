# Moneyball Backend

This is the Python/FastAPI backend for the Moneyball application.

## Prerequisites

- Python 3.10+
- Docker (for running the database)

## Setup

1.  **Clone the repository** (if you haven't already).
2.  **Create a virtual environment**:
    ```bash
    python -m venv venv
    ```
3.  **Activate the virtual environment**:
    - Windows: `venv\Scripts\activate`
    - Mac/Linux: `source venv/bin/activate`
4.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Database

We use PostgreSQL running in Docker. To start just the database:

```bash
# From the project root (where docker-compose.yml is)
docker compose up -d db
```

This will expose Postgres on port `5432`.

## Running the API

1.  **Ensure the database is running**.
2.  **Start the server**:
    ```bash
    uvicorn app.main:app --reload
    ```
3.  The API will be available at `http://localhost:8000`.
4.  Documentation (Swagger UI) is at `http://localhost:8000/docs`.

## Environment Variables

Make sure you have a `.env` file or export these variables:

- `DATABASE_URL`: `postgresql://postgres:admin@localhost:5432/moneyball`
- `FEDERATION_BASE_URL`: (Data source URL)
- `FEDERATION_ID_DISPOSITIVO`: ...
