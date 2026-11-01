-- =====================================================================
-- Rental Scam Detector: initial schema
-- Postgres 15 (Supabase). All writes go through the FastAPI backend
-- using the service role key. The browser only ever gets read access
-- to the user's own results, enforced by Row Level Security.
-- =====================================================================

-- Trigram matching for near-duplicate listing descriptions.
create extension if not exists pg_trgm with schema extensions;

-- ---------------------------------------------------------------------
-- Enums: constrain values at the database level, not just in code.
-- ---------------------------------------------------------------------
create type public.listing_source  as enum ('paste', 'extension');
create type public.check_type      as enum ('price', 'text', 'photo', 'address', 'contact');
create type public.signal_severity as enum ('info', 'low', 'medium', 'high');
create type public.risk_level      as enum ('low', 'medium', 'high');
create type public.contact_kind    as enum ('email', 'phone', 'name');
create type public.analysis_status as enum ('pending', 'complete', 'failed');

-- ---------------------------------------------------------------------
-- market_rents: reference data for the price check.
-- Loaded from HUD Small Area Fair Market Rents (ZIP level, 0 to 4 BR).
-- ---------------------------------------------------------------------
create table public.market_rents (
    zip_code            text        not null check (zip_code ~ '^[0-9]{5}$'),
    bedrooms            smallint    not null check (bedrooms between 0 and 4),
    monthly_rent_cents  integer     not null check (monthly_rent_cents > 0),
    data_source         text        not null default 'hud_safmr',
    fiscal_year         smallint    not null check (fiscal_year between 2000 and 2100),
    loaded_at           timestamptz not null default now(),
    primary key (zip_code, bedrooms, data_source, fiscal_year)
);

-- ---------------------------------------------------------------------
-- listings: one row per submitted listing.
-- Contact info is stripped from the description before insert
-- (description_redacted). The full source URL is never stored.
-- ---------------------------------------------------------------------
create table public.listings (
    id                      uuid        primary key default gen_random_uuid(),
    submitted_by            uuid        references auth.users (id) on delete set null,
    source                  public.listing_source not null default 'paste',
    source_domain           text        check (char_length(source_domain) <= 255),
    title                   text        check (char_length(title) <= 300),
    description_redacted    text        not null
                                        check (char_length(description_redacted) between 1 and 20000),
    description_fingerprint text        not null check (description_fingerprint ~ '^[0-9a-f]{64}$'),
    monthly_rent_cents      integer     check (monthly_rent_cents > 0 and monthly_rent_cents < 100000000),
    bedrooms                smallint    check (bedrooms between 0 and 20),
    bathrooms               numeric(3,1) check (bathrooms >= 0),
    street_address          text        check (char_length(street_address) <= 300),
    city                    text        check (char_length(city) <= 100),
    state_code              char(2),
    zip_code                text        check (zip_code ~ '^[0-9]{5}$'),
    latitude                double precision check (latitude between -90 and 90),
    longitude               double precision check (longitude between -180 and 180),
    geocode_confidence      real        check (geocode_confidence between 0 and 1),
    created_at              timestamptz not null default now(),
    purge_after             timestamptz not null default (now() + interval '180 days')
);

create index listings_fingerprint_idx  on public.listings (description_fingerprint);
create index listings_description_trgm on public.listings
    using gin (description_redacted extensions.gin_trgm_ops);
create index listings_zip_idx          on public.listings (zip_code);
create index listings_submitted_by_idx on public.listings (submitted_by);
create index listings_purge_after_idx  on public.listings (purge_after);

-- ---------------------------------------------------------------------
-- listing_contacts: contact info stored only as keyed hashes.
-- value_hmac = HMAC-SHA256(normalized value, server-side secret).
-- A plain SHA-256 of a phone number can be reversed by brute force
-- (only ~10 billion possibilities), so a secret key is required.
-- ---------------------------------------------------------------------
create table public.listing_contacts (
    id               uuid        primary key default gen_random_uuid(),
    listing_id       uuid        not null references public.listings (id) on delete cascade,
    kind             public.contact_kind not null,
    value_hmac       text        not null check (value_hmac ~ '^[0-9a-f]{64}$'),
    email_domain     text        check (char_length(email_domain) <= 255),
    phone_line_type  text        check (phone_line_type in ('mobile', 'landline', 'voip', 'unknown')),
    created_at       timestamptz not null default now(),
    constraint email_domain_only_for_email check (kind = 'email' or email_domain is null),
    constraint line_type_only_for_phone    check (kind = 'phone' or phone_line_type is null),
    unique (listing_id, kind, value_hmac)
);

create index listing_contacts_lookup_idx on public.listing_contacts (kind, value_hmac);

-- ---------------------------------------------------------------------
-- listing_photos: perceptual hashes only. Original images are never
-- stored; they are hashed in memory and discarded.
-- Reuse lookup: bit_count(phash # :candidateHash) <= threshold
-- ---------------------------------------------------------------------
create table public.listing_photos (
    id              uuid        primary key default gen_random_uuid(),
    listing_id      uuid        not null references public.listings (id) on delete cascade,
    content_sha256  text        not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    phash           bit(64)     not null,
    dhash           bit(64)     not null,
    width_px        integer     check (width_px > 0),
    height_px       integer     check (height_px > 0),
    created_at      timestamptz not null default now(),
    unique (listing_id, content_sha256)
);

create index listing_photos_sha_idx     on public.listing_photos (content_sha256);
create index listing_photos_listing_idx on public.listing_photos (listing_id);

-- ---------------------------------------------------------------------
-- analyses: one scoring run for a listing. Separate from listings so a
-- listing can be re-scored when weights change, and every result
-- records which config version produced it.
-- ---------------------------------------------------------------------
create table public.analyses (
    id                     uuid        primary key default gen_random_uuid(),
    listing_id             uuid        not null references public.listings (id) on delete cascade,
    status                 public.analysis_status not null default 'pending',
    total_points           integer     check (total_points >= 0),
    risk_level             public.risk_level,
    scoring_config_version text        not null,
    llm_used               boolean     not null default false,
    duration_ms            integer     check (duration_ms >= 0),
    error_code             text,
    created_at             timestamptz not null default now(),
    completed_at           timestamptz,
    constraint complete_has_result check (
        status <> 'complete'
        or (total_points is not null and risk_level is not null and completed_at is not null)
    )
);

create index analyses_listing_idx on public.analyses (listing_id, created_at desc);

-- ---------------------------------------------------------------------
-- signals: every red flag behind a score, with its explanation.
-- points is a snapshot, so old results stay explainable after tuning.
-- ---------------------------------------------------------------------
create table public.signals (
    id           uuid        primary key default gen_random_uuid(),
    analysis_id  uuid        not null references public.analyses (id) on delete cascade,
    check_name   public.check_type not null,
    signal_code  text        not null check (signal_code ~ '^[A-Z][A-Z0-9_]{2,63}$'),
    severity     public.signal_severity not null,
    points       integer     not null check (points >= 0),
    explanation  text        not null check (char_length(explanation) between 1 and 1000),
    evidence     jsonb       not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);

create index signals_analysis_idx on public.signals (analysis_id);
create index signals_code_idx     on public.signals (signal_code);

-- ---------------------------------------------------------------------
-- Row Level Security. Enabled on every table. There are no insert,
-- update, or delete policies, so only the backend (service role) can
-- write. Contacts and photos have no policies at all: the browser
-- never needs hashes, and exposing them would help enumeration.
-- ---------------------------------------------------------------------
alter table public.market_rents     enable row level security;
alter table public.listings         enable row level security;
alter table public.listing_contacts enable row level security;
alter table public.listing_photos   enable row level security;
alter table public.analyses         enable row level security;
alter table public.signals          enable row level security;

create policy "market rents are public reference data"
    on public.market_rents for select
    to anon, authenticated
    using (true);

create policy "users read their own listings"
    on public.listings for select
    to authenticated
    using ((select auth.uid()) = submitted_by);

create policy "users read analyses of their own listings"
    on public.analyses for select
    to authenticated
    using (
        exists (
            select 1 from public.listings l
            where l.id = analyses.listing_id
              and l.submitted_by = (select auth.uid())
        )
    );

create policy "users read signals of their own analyses"
    on public.signals for select
    to authenticated
    using (
        exists (
            select 1
            from public.analyses a
            join public.listings l on l.id = a.listing_id
            where a.id = signals.analysis_id
              and l.submitted_by = (select auth.uid())
        )
    );

-- ---------------------------------------------------------------------
-- Data retention. Deletes listings past purge_after; cascades remove
-- their contacts, photos, analyses, and signals. Schedule with pg_cron
-- later. Not callable by anon or authenticated users.
-- ---------------------------------------------------------------------
create or replace function public.purge_expired_listings()
returns integer
language sql
security definer
set search_path = ''
as $$
    with deleted as (
        delete from public.listings
        where purge_after < now()
        returning 1
    )
    select count(*)::integer from deleted;
$$;

revoke execute on function public.purge_expired_listings() from public, anon, authenticated;