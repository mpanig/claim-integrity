"""Fold several tables into one flat table, keeping every old table name as a view.

Used by migrations 0021-0026. Do not change its behaviour: those migrations depend on it.

flatten(conn, "traffic", {"upload": "log_upload", "crawler": "crawler_hit", ...}) does:

- one table `traffic` with `row_type` (which old table a row came from) and `id` (the old id),
  primary key (row_type, id), so ids never clash and nothing is renumbered.
- the old columns side by side. A column name shared by several old tables is one column when its
  type matches (varchar widths may differ) and so does its foreign key; otherwise each old table gets
  its own `<table>_<column>`.
- old NOT NULL rules as per-row_type CHECKs; old indexes as partial indexes (WHERE row_type = ...).
- links: an old foreign key to another table stays on the flat column. A foreign key *to* one of the old
  tables (from outside, or between the folded tables) becomes (<col>_type, <col>) -> (row_type, id), with
  <col>_type a constant column, same ON DELETE action. ON DELETE SET NULL only clears <col>.
- each old id sequence is kept and becomes the id default of its view.
- each old table name becomes `SELECT <old columns>, row_type FROM <flat> WHERE row_type = ...
  WITH LOCAL CHECK OPTION`, with the old column defaults. Postgres writes through such a view by
  itself, so the app keeps reading and writing the old names unchanged.
"""

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import text

_ACTION = {"c": "CASCADE", "n": "SET NULL", "a": "NO ACTION", "r": "RESTRICT", "d": "SET DEFAULT"}


def _rows(conn, sql: str, **params: Any) -> list[Any]:
    return conn.execute(text(sql), params).all()


def _columns(conn, table: str) -> list[Any]:
    return _rows(conn, """
        SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS notnull,
               pg_get_expr(d.adbin, d.adrelid) AS dflt
        FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = CAST(:t AS regclass) AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum""", t=table)


def _fks(conn, where: str, **params: Any) -> list[Any]:
    return _rows(conn, f"""
        SELECT c.conname, c.conrelid::regclass::text AS src, sa.attname AS col,
               c.confrelid::regclass::text AS target, ta.attname AS target_col, c.confdeltype AS action
        FROM pg_constraint c
        JOIN pg_attribute sa ON sa.attrelid = c.conrelid AND sa.attnum = c.conkey[1]
        JOIN pg_attribute ta ON ta.attrelid = c.confrelid AND ta.attnum = c.confkey[1]
        WHERE c.contype = 'f' AND {where}""", **params)


def _indexes(conn, table: str) -> list[Any]:
    return _rows(conn, """
        SELECT i.indisunique AS uniq,
               array_agg(a.attname ORDER BY k.n) AS cols
        FROM pg_index i
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, n)
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
        WHERE i.indrelid = CAST(:t AS regclass) AND NOT i.indisprimary
        GROUP BY i.indexrelid, i.indisunique""", t=table)


def _merge_type(types: set[str]) -> str | None:
    if len(types) == 1:
        return next(iter(types))
    widths = [re.fullmatch(r"character varying\((\d+)\)", t) for t in types]
    if all(widths):
        return f"character varying({max(int(w.group(1)) for w in widths)})"
    return None


def flatten(conn, flat: str, parts: dict[str, str]) -> None:
    tables = list(parts.values())
    row_type_of = {t: rt for rt, t in parts.items()}
    cols = {t: [c for c in _columns(conn, t) if c.name != "id"] for t in tables}
    out_fk = {(f.src, f.col): f for f in _fks(conn, "c.conrelid::regclass::text = ANY(:t)", t=tables)}
    in_fk = _fks(conn, "c.confrelid::regclass::text = ANY(:t)", t=tables)
    seqs = {t: conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": t}).scalar() for t in tables}
    indexes = {t: _indexes(conn, t) for t in tables}

    # Which flat column each old column goes to.
    by_name: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for t in tables:
        for c in cols[t]:
            by_name[c.name].append((t, c))
    flat_col: dict[tuple[str, str], str] = {}
    flat_type: dict[str, str] = {}
    for name, uses in by_name.items():
        merged = _merge_type({c.type for _, c in uses})
        fk_sig = {(out_fk[(t, name)].target, out_fk[(t, name)].action) if (t, name) in out_fk else None for t, _ in uses}
        if merged and len(fk_sig) == 1 and name not in ("row_type",):
            flat_type[name] = merged
            for t, _ in uses:
                flat_col[(t, name)] = name
        else:
            for t, c in uses:
                flat_col[(t, name)] = f"{t}_{name}"
                flat_type[f"{t}_{name}"] = c.type

    col_sql = ",\n".join(f'    "{n}" {ty}' for n, ty in flat_type.items())
    conn.execute(text(f"""CREATE TABLE {flat} (
    id integer NOT NULL,
    row_type varchar(30) NOT NULL,
{col_sql},
    PRIMARY KEY (row_type, id))"""))
    for t in tables:
        names = [c.name for c in cols[t]]
        conn.execute(text(
            f"INSERT INTO {flat} (id, row_type, {', '.join(chr(34) + flat_col[(t, n)] + chr(34) for n in names)}) "
            f"SELECT id, '{row_type_of[t]}', {', '.join(chr(34) + n + chr(34) for n in names)} FROM {t} ORDER BY ctid"))
        conn.execute(text(f"ALTER SEQUENCE {seqs[t]} OWNED BY NONE"))

    # Old tables out (CASCADE drops the foreign keys pointing at them; they are re-made below).
    conn.execute(text(f"DROP TABLE {', '.join(tables)} CASCADE"))

    # Old NOT NULL rules, per row type.
    for t in tables:
        for c in cols[t]:
            if c.notnull:
                fc = flat_col[(t, c.name)]
                name = f"ck_{flat}_{row_type_of[t]}_{c.name}"[:63]
                conn.execute(text(f"""ALTER TABLE {flat} ADD CONSTRAINT "{name}"
                    CHECK (row_type <> '{row_type_of[t]}' OR "{fc}" IS NOT NULL)"""))

    def link(src: str, col: str, target_row_type: str, action: str) -> None:
        type_col = f"{col}_type"
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
            {"t": src, "c": type_col}).first()
        if not exists:
            conn.execute(text(f"""ALTER TABLE {src} ADD COLUMN "{type_col}" varchar(30) NOT NULL DEFAULT '{target_row_type}'
                CHECK ("{type_col}" = '{target_row_type}')"""))
        on_delete = f'SET NULL ("{col}")' if action == "n" else _ACTION[action]
        conn.execute(text(f"""ALTER TABLE {src} ADD FOREIGN KEY ("{type_col}", "{col}")
            REFERENCES {flat} (row_type, id) ON DELETE {on_delete}"""))

    # Foreign keys out of the old tables (one per flat column).
    done: set[str] = set()
    for (t, name), f in out_fk.items():
        fc = flat_col[(t, name)]
        if fc in done:
            continue
        done.add(fc)
        if f.target in row_type_of:
            link(flat, fc, row_type_of[f.target], f.action)
        else:
            conn.execute(text(f"""ALTER TABLE {flat} ADD FOREIGN KEY ("{fc}") REFERENCES {f.target} ({f.target_col})
                ON DELETE {_ACTION[f.action]}"""))
    # Foreign keys into the old tables from other tables.
    for f in in_fk:
        if f.src in row_type_of:
            continue  # between folded tables: handled above
        link(f.src, f.col, row_type_of[f.target], f.action)

    # Old indexes, per row type.
    for t in tables:
        for ix in indexes[t]:
            fcs = [flat_col[(t, c)] for c in ix.cols]
            name = f"ix_{flat}_{row_type_of[t]}_{'_'.join(ix.cols)}"[:63]
            unique = "UNIQUE " if ix.uniq else ""
            conn.execute(text(f"""CREATE {unique}INDEX "{name}" ON {flat} ({', '.join(chr(34) + c + chr(34) for c in fcs)})
                WHERE row_type = '{row_type_of[t]}'"""))

    # Old names back, as views with the old columns and defaults.
    for t in tables:
        rt = row_type_of[t]
        select = ", ".join(["id"] + [f'"{flat_col[(t, c.name)]}" AS "{c.name}"' for c in cols[t]] + ["row_type"])
        conn.execute(text(f"CREATE VIEW {t} AS SELECT {select} FROM {flat} WHERE row_type = '{rt}' WITH LOCAL CHECK OPTION"))
        conn.execute(text(f"ALTER VIEW {t} ALTER COLUMN id SET DEFAULT nextval('{seqs[t]}'::regclass)"))
        conn.execute(text(f"ALTER VIEW {t} ALTER COLUMN row_type SET DEFAULT '{rt}'"))
        for c in cols[t]:
            if c.dflt is not None:
                conn.execute(text(f'ALTER VIEW {t} ALTER COLUMN "{c.name}" SET DEFAULT {c.dflt}'))
