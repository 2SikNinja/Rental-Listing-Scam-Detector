-- =====================================================================
-- Least-privilege database role for the daily data retention job.
--
-- A scheduled GitHub Actions workflow (.github/workflows/retention.yml)
-- connects as "retention_job" once a day and calls
-- public.purge_expired_listings(), which deletes listings older than
-- their 180-day purge_after date.
--
-- The role can do exactly one thing: run that function. It cannot read
-- or change any table directly. The function is "security definer", so
-- the delete runs with the function owner's rights, limited to the one
-- statement inside it. If this role's password leaked, the worst an
-- attacker could do is delete data that was already due for deletion.
--
-- The role is created without login. A password is set separately (never
-- committed to Git):
--   alter role retention_job with login password '...';
-- =====================================================================

do $$
begin
    if not exists (select from pg_roles where rolname = 'retention_job') then
        create role retention_job nologin noinherit;
    end if;
end
$$;

grant usage on schema public to retention_job;

grant execute on function public.purge_expired_listings() to retention_job;
