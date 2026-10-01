"""Verify the Neon connection configured in the adjacent .env file."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().with_name(".env"))
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is missing. Set it in .env or the environment.")

    try:
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            result = conn.execute("SELECT 1").fetchone()
            if result != (1,):
                raise SystemExit("The database returned an unexpected result.")
    except psycopg.Error:
        raise SystemExit(
            "Neon connection failed. Check DATABASE_URL, its SSL settings, "
            "and network access. Credentials have not been printed."
        ) from None

    print("Connected to Neon successfully.")


if __name__ == "__main__":
    main()
