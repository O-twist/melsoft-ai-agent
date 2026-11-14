-- LabLess tables. Run this in the Supabase SQL editor, then run supabase/seed.sql.
-- Do not put keys in this file. The server reads SUPABASE_URL, SUPABASE_ANON_KEY
-- and SUPABASE_SERVICE_ROLE_KEY from the environment.

create table if not exists public.learners (
  id text primary key,
  name text not null,
  email text,
  previous integer
);

create table if not exists public.marks (
  learner_id text not null references public.learners (id) on delete cascade,
  kind text not null check (kind in ('theory', 'practical', 'overall')),
  week integer not null default 1 check (week in (1, 2)),
  percent integer,
  score integer,
  max_score integer,
  result text,
  primary key (learner_id, kind, week)
);

create table if not exists public.practical_outcomes (
  learner_id text not null references public.learners (id) on delete cascade,
  outcome_id text not null check (outcome_id in ('H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'S1', 'S2', 'S3', 'S4')),
  week integer not null default 1 check (week in (1, 2)),
  percent integer not null,
  detail text,
  primary key (learner_id, outcome_id, week)
);

create table if not exists public.risk_scores (
  learner_id text not null references public.learners (id) on delete cascade,
  week integer not null default 1 check (week in (1, 2)),
  risk integer not null,
  band text not null check (band in ('High', 'Medium', 'Low')),
  overall integer not null,
  result text not null,
  reason text,
  primary key (learner_id, week)
);

create table if not exists public.rescue_plans (
  id bigint generated always as identity primary key,
  learner_id text not null references public.learners (id) on delete cascade,
  summary text,
  risk_before integer,
  risk_after integer,
  band_before text,
  band_after text,
  overall_before integer,
  overall_after integer,
  result_before text,
  result_after text,
  created_at timestamptz not null default now()
);

create table if not exists public.score_reports (
  learner_id text not null references public.learners (id) on delete cascade,
  week integer not null default 1 check (week in (1, 2)),
  report jsonb not null,
  primary key (learner_id, week)
);

create table if not exists public.week_runs (
  id integer primary key,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.learners enable row level security;
drop policy if exists learners_read on public.learners;
create policy learners_read on public.learners for select to anon, authenticated using (true);
revoke insert, update, delete on public.learners from anon, authenticated;
grant select on public.learners to anon, authenticated;
grant select, insert, update, delete on public.learners to service_role;
alter table public.marks enable row level security;
drop policy if exists marks_read on public.marks;
create policy marks_read on public.marks for select to anon, authenticated using (true);
revoke insert, update, delete on public.marks from anon, authenticated;
grant select on public.marks to anon, authenticated;
grant select, insert, update, delete on public.marks to service_role;
alter table public.practical_outcomes enable row level security;
drop policy if exists practical_outcomes_read on public.practical_outcomes;
create policy practical_outcomes_read on public.practical_outcomes for select to anon, authenticated using (true);
revoke insert, update, delete on public.practical_outcomes from anon, authenticated;
grant select on public.practical_outcomes to anon, authenticated;
grant select, insert, update, delete on public.practical_outcomes to service_role;
alter table public.risk_scores enable row level security;
drop policy if exists risk_scores_read on public.risk_scores;
create policy risk_scores_read on public.risk_scores for select to anon, authenticated using (true);
revoke insert, update, delete on public.risk_scores from anon, authenticated;
grant select on public.risk_scores to anon, authenticated;
grant select, insert, update, delete on public.risk_scores to service_role;
alter table public.rescue_plans enable row level security;
drop policy if exists rescue_plans_read on public.rescue_plans;
create policy rescue_plans_read on public.rescue_plans for select to anon, authenticated using (true);
revoke insert, update, delete on public.rescue_plans from anon, authenticated;
grant select on public.rescue_plans to anon, authenticated;
grant select, insert, update, delete on public.rescue_plans to service_role;
alter table public.score_reports enable row level security;
drop policy if exists score_reports_read on public.score_reports;
create policy score_reports_read on public.score_reports for select to anon, authenticated using (true);
revoke insert, update, delete on public.score_reports from anon, authenticated;
grant select on public.score_reports to anon, authenticated;
grant select, insert, update, delete on public.score_reports to service_role;
alter table public.week_runs enable row level security;
drop policy if exists week_runs_read on public.week_runs;
create policy week_runs_read on public.week_runs for select to anon, authenticated using (true);
revoke insert, update, delete on public.week_runs from anon, authenticated;
grant select on public.week_runs to anon, authenticated;
grant select, insert, update, delete on public.week_runs to service_role;
grant usage, select on all sequences in schema public to service_role;
