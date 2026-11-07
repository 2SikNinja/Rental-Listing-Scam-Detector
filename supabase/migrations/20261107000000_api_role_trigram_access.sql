-- =====================================================================
-- Let the API role use pg_trgm (installed in the "extensions" schema)
-- for near-duplicate description matching.
--
-- USAGE on a schema only allows referring to objects in it, such as the
-- similarity() function and the % operator. It grants no access to any
-- table, and scam_api still cannot create objects there.
-- =====================================================================

grant usage on schema extensions to scam_api;
