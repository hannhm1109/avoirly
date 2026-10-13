-- Run once against the Supabase database before the first Avoirly migration.
-- Keep application snapshots independent of Supabase's public/auth schemas.
CREATE SCHEMA IF NOT EXISTS avoirly AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA avoirly FROM PUBLIC, anon, authenticated;
