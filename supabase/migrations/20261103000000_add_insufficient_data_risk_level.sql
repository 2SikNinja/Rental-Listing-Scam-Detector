-- =====================================================================
-- Add 'insufficient_data' to the risk_level enum.
--
-- Used when no red flags were found but too few checks could run to call
-- a listing low risk (for example, no rent or ZIP code was entered).
--
-- Safe to run on a live database: adding an enum value does not rewrite
-- the table or block reads, and "if not exists" makes it re-runnable.
-- =====================================================================

alter type public.risk_level add value if not exists 'insufficient_data';
