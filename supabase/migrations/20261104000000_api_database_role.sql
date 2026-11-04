-- =====================================================================
-- Least-privilege database role for the FastAPI backend.
--
-- The API never connects as the all-powerful "postgres" owner. It uses
-- "scam_api", which can only:
--   - read the market rent reference data
--   - insert and read listings, contacts, photo hashes, analyses, signals
--     (reads are needed for duplicate detection)
-- It cannot update or delete anything, change the schema, or read auth
-- data. If the API's database password ever leaked, an attacker could not
-- wipe or rewrite stored results.
--
-- The role is created without login. A password is set separately (never
-- committed to Git):
--   alter role scam_api with login password '...';
-- =====================================================================

do $$
begin
    if not exists (select from pg_roles where rolname = 'scam_api') then
        create role scam_api nologin noinherit;
    end if;
end
$$;

grant usage on schema public to scam_api;

grant select on public.market_rents to scam_api;

grant select, insert on
    public.listings,
    public.listing_contacts,
    public.listing_photos,
    public.analyses,
    public.signals
to scam_api;

-- Row Level Security still applies to this role (it is not the table
-- owner), so it needs explicit policies. These are scoped to scam_api
-- only and do not change what browser users (anon, authenticated) see.
create policy "api reads listings"        on public.listings         for select to scam_api using (true);
create policy "api inserts listings"      on public.listings         for insert to scam_api with check (true);
create policy "api reads contacts"        on public.listing_contacts for select to scam_api using (true);
create policy "api inserts contacts"      on public.listing_contacts for insert to scam_api with check (true);
create policy "api reads photos"          on public.listing_photos   for select to scam_api using (true);
create policy "api inserts photos"        on public.listing_photos   for insert to scam_api with check (true);
create policy "api reads analyses"        on public.analyses         for select to scam_api using (true);
create policy "api inserts analyses"      on public.analyses         for insert to scam_api with check (true);
create policy "api reads signals"         on public.signals          for select to scam_api using (true);
create policy "api inserts signals"       on public.signals          for insert to scam_api with check (true);
create policy "api reads market rents"    on public.market_rents     for select to scam_api using (true);
