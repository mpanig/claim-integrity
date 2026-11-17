-- chunk_001: Aveeno/Listerine public data. Self-contained: loads alone into an empty claim_integrity DB
-- (alembic head, 0018) or on top of other chunks, in any order, and can be re-run: every table goes through a
-- staging table + INSERT ... ON CONFLICT DO NOTHING; inferred_truth upserts on sku_id when this chunk's row is newer.
-- Run from this directory:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f load_order.sql
\set ON_ERROR_STOP on
BEGIN;
DO $$ BEGIN IF to_regclass('public.inferred_truth') IS NULL THEN RAISE EXCEPTION 'inferred_truth missing: run alembic upgrade head (0018) first'; END IF; END $$;
CREATE TEMP TABLE s_organisation (LIKE organisation INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_organisation(id, name, created_at) FROM 'organisation.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO organisation (id, name, created_at) SELECT id, name, created_at FROM s_organisation ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_brand (LIKE brand INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_brand(id, organisation_id, name, aliases, positioning) FROM 'brand.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO brand (id, organisation_id, name, aliases, positioning) SELECT id, organisation_id, name, aliases, positioning FROM s_brand ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_sku (LIKE sku INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_sku(id, organisation_id, brand_id, gtin, name, line, last_checked_at, aliases) FROM 'sku.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO sku (id, organisation_id, brand_id, gtin, name, line, last_checked_at, aliases) SELECT id, organisation_id, brand_id, gtin, name, line, last_checked_at, aliases FROM s_sku ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_variant (LIKE variant INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_variant(id, organisation_id, sku_id, market, size, formula_version, valid_from, valid_to) FROM 'variant.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO variant (id, organisation_id, sku_id, market, size, formula_version, valid_from, valid_to) SELECT id, organisation_id, sku_id, market, size, formula_version, valid_from, valid_to FROM s_variant ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_page (LIKE page INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_page(id, organisation_id, url, source_type, retailer, country, weight) FROM 'page.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO page (id, organisation_id, url, source_type, retailer, country, weight) SELECT id, organisation_id, url, source_type, retailer, country, weight FROM s_page ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_snapshot (LIKE snapshot INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_snapshot(id, organisation_id, page_id, fetched_at, content_hash, html) FROM PROGRAM 'gzip -dc snapshot_part01.csv.gz' WITH (FORMAT csv, HEADER true)
\copy s_snapshot(id, organisation_id, page_id, fetched_at, content_hash, html) FROM PROGRAM 'gzip -dc snapshot_part02.csv.gz' WITH (FORMAT csv, HEADER true)
INSERT INTO snapshot (id, organisation_id, page_id, fetched_at, content_hash, html) SELECT id, organisation_id, page_id, fetched_at, content_hash, html FROM s_snapshot ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_extraction (LIKE extraction INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_extraction(id, organisation_id, snapshot_id, sku_id, fields, created_at) FROM 'extraction.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO extraction (id, organisation_id, snapshot_id, sku_id, fields, created_at) SELECT id, organisation_id, snapshot_id, sku_id, fields, created_at FROM s_extraction ON CONFLICT DO NOTHING;
CREATE TEMP TABLE s_inferred_truth (LIKE inferred_truth INCLUDING DEFAULTS) ON COMMIT DROP;
\copy s_inferred_truth(id, sku_id, fields, agreement, method, sources, source_hash, updated_at) FROM 'inferred_truth.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO inferred_truth (id, sku_id, fields, agreement, method, sources, source_hash, updated_at) SELECT id, sku_id, fields, agreement, method, sources, source_hash, updated_at FROM s_inferred_truth ON CONFLICT (sku_id) DO UPDATE SET fields = EXCLUDED.fields, agreement = EXCLUDED.agreement, method = EXCLUDED.method, sources = EXCLUDED.sources, source_hash = EXCLUDED.source_hash, updated_at = EXCLUDED.updated_at WHERE inferred_truth.updated_at <= EXCLUDED.updated_at;
SELECT setval(pg_get_serial_sequence('organisation', 'id'), GREATEST((SELECT max(id) FROM organisation), 1));
SELECT setval(pg_get_serial_sequence('brand', 'id'), GREATEST((SELECT max(id) FROM brand), 1));
SELECT setval(pg_get_serial_sequence('sku', 'id'), GREATEST((SELECT max(id) FROM sku), 1));
SELECT setval(pg_get_serial_sequence('variant', 'id'), GREATEST((SELECT max(id) FROM variant), 1));
SELECT setval(pg_get_serial_sequence('page', 'id'), GREATEST((SELECT max(id) FROM page), 1));
SELECT setval(pg_get_serial_sequence('snapshot', 'id'), GREATEST((SELECT max(id) FROM snapshot), 1));
SELECT setval(pg_get_serial_sequence('extraction', 'id'), GREATEST((SELECT max(id) FROM extraction), 1));
SELECT setval(pg_get_serial_sequence('inferred_truth', 'id'), GREATEST((SELECT max(id) FROM inferred_truth), 1));
COMMIT;
