-- FXGuard AI account storage
-- Apply this migration in the Supabase SQL editor before enabling accounts.

create extension if not exists pgcrypto;

create table if not exists public.payment_checks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  signature text not null,
  checked_at timestamptz not null default now(),
  currency text not null check (currency in ('USD', 'EUR', 'KES')),
  amount numeric not null check (amount > 0),
  horizon_days smallint not null check (horizon_days in (7, 14)),
  risk_level text not null check (risk_level in ('Low', 'Medium', 'High')),
  likelihood_probability numeric check (
    likelihood_probability is null
    or likelihood_probability between 0 and 1
  ),
  current_rate numeric not null,
  current_cost_rwf numeric not null,
  estimated_extra_cost_rwf numeric not null,
  rate_date date not null,
  model_version text,
  result jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, signature)
);

create index if not exists payment_checks_user_checked_at_idx
  on public.payment_checks (user_id, checked_at desc);

alter table public.payment_checks enable row level security;

drop policy if exists "Users can read their checks" on public.payment_checks;
create policy "Users can read their checks"
  on public.payment_checks for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can save their checks" on public.payment_checks;
create policy "Users can save their checks"
  on public.payment_checks for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update their checks" on public.payment_checks;
create policy "Users can update their checks"
  on public.payment_checks for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete their checks" on public.payment_checks;
create policy "Users can delete their checks"
  on public.payment_checks for delete
  to authenticated
  using ((select auth.uid()) = user_id);

create table if not exists public.consent_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  terms_version text not null,
  privacy_version text not null,
  contact_method text not null check (contact_method in ('email', 'phone')),
  accepted_at timestamptz not null,
  created_at timestamptz not null default now(),
  unique (user_id, terms_version, privacy_version)
);

alter table public.consent_records enable row level security;

drop policy if exists "Users can read their consent records" on public.consent_records;
create policy "Users can read their consent records"
  on public.consent_records for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can record their consent" on public.consent_records;
create policy "Users can record their consent"
  on public.consent_records for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update their consent records" on public.consent_records;
create policy "Users can update their consent records"
  on public.consent_records for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

grant select, insert, update, delete on public.payment_checks to authenticated;
grant select, insert, update on public.consent_records to authenticated;
revoke all on public.payment_checks from anon;
revoke all on public.consent_records from anon;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists payment_checks_set_updated_at on public.payment_checks;
create trigger payment_checks_set_updated_at
before update on public.payment_checks
for each row execute function public.set_updated_at();
