import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

url = os.getenv("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL is missing from .env")

with psycopg.connect(url, connect_timeout=15) as conn:
    result = conn.execute("SELECT 1").fetchone()
    assert result == (1,)

print("Connected to Neon successfully.")