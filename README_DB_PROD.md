# Production-Ready Database Setup (FastAPI + PostgreSQL)

To make your database production-ready for CrashGuard, we cannot rely on running raw SQL commands manually. You need a setup that gives you version control over your database schema, prevents SQL injection, encrypts sensitive data, and connects securely.

Here is the exact production-ready plan and technology choices for your database layer:

## 1. The Core Stack
*   **Database Host**: **Supabase** or **Neon.tech**. Both provide serverless PostgreSQL which is excellent for scaling. Supabase also gives you Auth out-of-the-box.
*   **Driver**: `asyncpg` (Asynchronous Postgres driver for Python, maximizing FastAPI's performance).
*   **ORM**: `SQLAlchemy 2.0` (Modern, async-compatible Python ORM).
*   **Migrations**: `Alembic` (Database migration tool maintained by the SQLAlchemy authors).
*   **Config Management**: `pydantic-settings` (Type-safe loading of your `.env` variables).

## 2. Security & Token Encryption
Since you are storing OAuth tokens (like YouTube refresh tokens) in the `platform_connections` table, **these must be encrypted at rest in the database.**
*   **Tool**: Python's `cryptography` library (`Fernet` symmetric encryption).
*   **Strategy**: You will keep a master `ENCRYPTION_KEY` in your production environment variables. Before saving a token to Postgres via SQLAlchemy, you encrypt it. When reading it out to make an API request on behalf of the creator, you decrypt it.

## 3. Implementation Plan (Step-by-Step)

### Step A: Initialize the Database ORM & Migrations
Instead of raw SQL, we represent tables as Python classes. 
1. We will create `backend/app/models/` and define our `User`, `Creator`, and `DailyMetric` models using SQLAlchemy declarative base.
2. We run `alembic init alembic` to create the migrations directory.
3. We configure `alembic.ini` to read the database URL from your `.env` file.
4. We run `alembic revision --autogenerate -m "init"` to auto-generate the Python migration script matching our models.
5. We run `alembic upgrade head` to safely apply the tables to your cloud PostgreSQL.

### Step B: Database Connection Pooling
In production, your FastAPI app needs to maintain a pool of connections to the database to handle concurrent requests efficiently without overwhelming Postgres.
*   SQLAlchemy handles this natively using `create_async_engine(DATABASE_URL, pool_size=20, max_overflow=10)`.
*   *Note: If using Supabase, you'll connect using their "Transaction Pooler" connection string (usually port 6543) so you don't exhaust connections.*

### Step C: Environment Configuration (`.env`)
You will need a securely stored `.env` file that **is never committed to git**. It will contain:
```env
DATABASE_URL=postgresql+asyncpg://user:password@your-supabase-url.supabase.co:6543/postgres
ENCRYPTION_KEY=your-32-byte-base64-fernet-key
```

### Step D: The "Repository" Pattern
To keep the FastAPI routes clean, we will implement the Repository pattern.
*   Instead of writing `session.execute(select(User).where(...))` directly in your `main.py`, you will create `backend/app/crud/user_crud.py`.
*   This isolates your database logic and makes it incredibly easy to mock the database during automated tests.

---

## Action: Let's Build It
Since you need this now, we can scaffold this entire structure immediately.

**Should I execute the commands to install SQLAlchemy/Alembic, initialize the migration folder, and generate the SQLAlchemy `models.py` file with the schema we discussed earlier?**
