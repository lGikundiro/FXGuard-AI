-- Support user-selected invoice payment dates from 1 to 100 days ahead.
alter table public.payment_checks
  drop constraint if exists payment_checks_horizon_days_check;

alter table public.payment_checks
  add constraint payment_checks_horizon_days_check
  check (horizon_days between 1 and 100);

alter table public.payment_checks
  add column if not exists payment_date date;

update public.payment_checks
set payment_date = (checked_at at time zone 'UTC')::date + horizon_days
where payment_date is null;

alter table public.payment_checks
  alter column payment_date set not null;

comment on column public.payment_checks.payment_date is
  'User-selected supplier invoice payment date, limited by the API to 1–100 days from the check date.';
