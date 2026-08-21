-- One-time migration: move app-pic's Postgres tables from suffix-based
-- naming in `public` (users_staging/users_prod, policy_staging/policy_prod)
-- to proper schema-based environment isolation (staging.users, prod.users,
-- etc). See plan.md section 7.
--
-- Staging and prod share the same Postgres instance AND database (`pic`),
-- so both blocks below run against the same database connection — just run
-- the whole file once, in one shot, as the `pic` Postgres user (the owner of
-- the existing tables), so the new schemas are owned by the same role and
-- need no extra GRANTs.
--
-- ALTER TABLE ... SET SCHEMA and RENAME TO are metadata-only operations in
-- Postgres — no data is copied, this is effectively instant regardless of
-- table size. Still, take a snapshot/backup before running against prod data
-- if you want a rollback safety net beyond the DROP SCHEMA below.
--
-- Run with: psql "<connection string>" -f scripts/migrate_schema_isolation.sql

-- Note: auto-generated constraint/index names (e.g. `users_staging_pkey`,
-- `policy_staging_subject_fkey`) are NOT renamed by `RENAME TO` in Postgres —
-- they keep referencing the old table name. This is purely cosmetic (they
-- still work correctly, and don't collide since they're schema-namespaced
-- too) and left as-is here; only `uq_policy_*_grant` is renamed below
-- because it's explicitly named in models.py and asserted by name elsewhere.

BEGIN;

-- ---------------------------------------------------------------------------
-- Staging
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS staging;

ALTER TABLE public.users_staging SET SCHEMA staging;
ALTER TABLE staging.users_staging RENAME TO users;

ALTER TABLE public.policy_staging SET SCHEMA staging;
ALTER TABLE staging.policy_staging RENAME TO policy;

-- Constraint name is namespaced per-schema now, so the old
-- uq_policy_staging_grant name is no longer needed for collision-avoidance —
-- rename it to match the fixed name models.py now declares (uq_policy_grant).
ALTER TABLE staging.policy RENAME CONSTRAINT uq_policy_staging_grant TO uq_policy_grant;

-- Alembic's own version-tracking table moves too, so `alembic upgrade head`
-- with APP_PIC_PG_SCHEMA=staging keeps seeing this environment's history.
ALTER TABLE public.alembic_version_staging SET SCHEMA staging;
ALTER TABLE staging.alembic_version_staging RENAME TO alembic_version;

-- ---------------------------------------------------------------------------
-- Prod
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS prod;

ALTER TABLE public.users_prod SET SCHEMA prod;
ALTER TABLE prod.users_prod RENAME TO users;

ALTER TABLE public.policy_prod SET SCHEMA prod;
ALTER TABLE prod.policy_prod RENAME TO policy;

ALTER TABLE prod.policy RENAME CONSTRAINT uq_policy_prod_grant TO uq_policy_grant;

ALTER TABLE public.alembic_version_prod SET SCHEMA prod;
ALTER TABLE prod.alembic_version_prod RENAME TO alembic_version;

COMMIT;

-- ---------------------------------------------------------------------------
-- Verification (run manually after commit)
-- ---------------------------------------------------------------------------
-- \dt staging.*
-- \dt prod.*
-- SELECT * FROM staging.alembic_version;
-- SELECT * FROM prod.alembic_version;
-- SELECT count(*) FROM staging.users;
-- SELECT count(*) FROM prod.users;
