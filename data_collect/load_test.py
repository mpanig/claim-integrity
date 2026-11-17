"""Load-test chunks into a THROWAWAY database (never the main one): create it, alembic upgrade head,
run each chunk's load_order.sql (\\copy lines via psycopg COPY FROM STDIN, the rest as SQL), load again,
compare row counts, drop the database.

Run with the backend venv from backend/:  python load_test.py CHUNK_DIR [CHUNK_DIR ...]
Credentials come from the backend settings and are never printed.
"""
import gzip
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from app.config import settings

TEST_DB = "claim_integrity_chunktest"
TABLES = ["organisation", "brand", "sku", "variant", "page", "snapshot", "extraction", "inferred_truth"]
main_url = make_url(settings.database_url)
assert main_url.database != TEST_DB
test_url = main_url.set(database=TEST_DB)
admin = main_url.set(drivername="postgresql").render_as_string(hide_password=False)
test_dsn = test_url.set(drivername="postgresql").render_as_string(hide_password=False)


def run_sql_file(conn, path: Path):
    d = path.parent
    text = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        buf = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("--") or s.startswith("\\set"):
                continue
            if s.startswith("\\copy"):
                if buf:
                    cur.execute("\n".join(buf))
                    buf = []
                m = re.match(r"\\copy\s+(\S+\([^)]*\))\s+FROM\s+(PROGRAM\s+)?'([^']+)'\s+WITH\s+\((.*)\)", s)
                target, prog, src, opts = m.groups()
                if prog:
                    data = subprocess.run(shlex.split(src), cwd=d, capture_output=True, check=True).stdout
                else:
                    data = (d / src).read_bytes()
                with cur.copy(f"COPY {target} FROM STDIN WITH ({opts})") as cp:
                    cp.write(data)
                continue
            buf.append(line)
            if s.endswith(";") and not s.upper().startswith("DO $$") or s.endswith("END $$;"):
                cur.execute("\n".join(buf))
                buf = []
        if buf:
            cur.execute("\n".join(buf))


def counts(conn):
    with conn.cursor() as cur:
        return {t: cur.execute(f"select count(*) from {t}").fetchone()[0] for t in TABLES}


def main(chunks):
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        a.execute(f"CREATE DATABASE {TEST_DB}")
    try:
        env = dict(os.environ, DATABASE_URL=test_url.render_as_string(hide_password=False))
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True,
                       capture_output=True)
        with psycopg.connect(test_dsn, autocommit=True) as c:
            print("empty", counts(c))
            for rnd in (1, 2):
                for ch in chunks:
                    run_sql_file(c, Path(ch) / "load_order.sql")
                    print(f"round {rnd} after {Path(ch).name}", counts(c))
            fk = c.execute("select count(*) from extraction e left join snapshot s on s.id=e.snapshot_id "
                           "where s.id is null").fetchone()[0]
            print("orphan extractions", fk)
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        print("test database dropped")


if __name__ == "__main__":
    main(sys.argv[1:])
