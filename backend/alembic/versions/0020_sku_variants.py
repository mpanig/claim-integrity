"""variant: rows move into sku.variants (JSON list); `variant` stays as a view with insert/delete triggers

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Filled by a table rewrite (ALTER ... USING), not an UPDATE, so sku rows keep their physical order.
    op.execute("""
        CREATE FUNCTION pg_temp.sku_variants(s integer) RETURNS jsonb LANGUAGE sql STABLE AS $$
            SELECT coalesce(jsonb_agg(jsonb_build_object('id', id, 'market', market, 'size', size,
                   'formula_version', formula_version, 'valid_from', valid_from, 'valid_to', valid_to) ORDER BY id), '[]'::jsonb)
            FROM variant WHERE sku_id = s $$""")
    op.execute("ALTER TABLE sku ADD COLUMN variants jsonb NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE sku ALTER COLUMN variants TYPE jsonb USING pg_temp.sku_variants(id)")
    op.execute("ALTER SEQUENCE variant_id_seq OWNED BY NONE")
    op.execute("DROP TABLE variant")
    op.execute("""
        CREATE VIEW variant AS
        SELECT (e->>'id')::int AS id, s.organisation_id, s.id AS sku_id, (e->>'market')::varchar(8) AS market,
               (e->>'size')::varchar(50) AS size, (e->>'formula_version')::varchar(50) AS formula_version,
               (e->>'valid_from')::date AS valid_from, (e->>'valid_to')::date AS valid_to
        FROM sku s CROSS JOIN LATERAL jsonb_array_elements(s.variants) AS e""")
    op.execute("ALTER VIEW variant ALTER COLUMN id SET DEFAULT nextval('variant_id_seq'::regclass)")
    op.execute("""
        CREATE FUNCTION variant_insert() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.id := coalesce(NEW.id, nextval('variant_id_seq'));
            IF NEW.id > coalesce(pg_sequence_last_value('variant_id_seq'), 0) THEN
                PERFORM setval('variant_id_seq', NEW.id);  -- a load with its own ids moves the counter past them
            END IF;
            IF NOT EXISTS (SELECT 1 FROM sku WHERE id = NEW.sku_id) THEN
                RAISE foreign_key_violation USING MESSAGE = 'no sku with id ' || NEW.sku_id;
            END IF;
            UPDATE sku SET variants = variants || jsonb_build_array(jsonb_build_object('id', NEW.id,
                'market', NEW.market, 'size', NEW.size, 'formula_version', NEW.formula_version,
                'valid_from', NEW.valid_from, 'valid_to', NEW.valid_to))
            WHERE id = NEW.sku_id AND NOT variants @> jsonb_build_array(jsonb_build_object('id', NEW.id));
            RETURN NEW;  -- an id already on the product is skipped, like ON CONFLICT DO NOTHING
        END $$""")
    op.execute("""
        CREATE FUNCTION variant_delete() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE sku SET variants = coalesce((SELECT jsonb_agg(e ORDER BY n) FROM jsonb_array_elements(variants)
                WITH ORDINALITY AS x(e, n) WHERE (e->>'id')::int <> OLD.id), '[]'::jsonb)
            WHERE id = OLD.sku_id;
            RETURN OLD;
        END $$""")
    op.execute("CREATE TRIGGER variant_insert INSTEAD OF INSERT ON variant FOR EACH ROW EXECUTE FUNCTION variant_insert()")
    op.execute("CREATE TRIGGER variant_delete INSTEAD OF DELETE ON variant FOR EACH ROW EXECUTE FUNCTION variant_delete()")


def downgrade() -> None:
    raise RuntimeError("0020 has no downgrade: restore the pg_dump taken before upgrading")
