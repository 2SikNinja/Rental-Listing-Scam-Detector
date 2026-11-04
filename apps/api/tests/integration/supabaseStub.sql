-- =====================================================================
-- Minimal stand-ins for the pieces of Supabase that our migrations
-- reference, so they can run on a plain Postgres in CI and locally.
-- Never run this against the real Supabase project.
-- =====================================================================

create schema if not exists extensions;
create schema if not exists auth;

create table if not exists auth.users (id uuid primary key);

create or replace function auth.uid() returns uuid
language sql stable
as $$ select null::uuid $$;

do $$
begin
    if not exists (select from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
end
$$;
