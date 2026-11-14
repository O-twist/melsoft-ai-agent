-- LabLess teacher accounts. Apply after 20261113233000_lablest.sql (Supabase SQL editor, or `supabase db push`).
-- Every row below belongs to one teacher (owner_id = auth.uid()) and row level security keeps it that way.
-- The server never uses a service role key for these tables: it calls PostgREST with the teacher's own token.
-- The seeded demo tables from the first migration are left as they are, readable as the template class.

-- Profiles: one per teacher, created on sign-up.
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null default '',
  school text not null default '',
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_teacher()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name, school)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', ''), coalesce(new.raw_user_meta_data ->> 'school', ''))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_labless on auth.users;
create trigger on_auth_user_created_labless after insert on auth.users
  for each row execute function public.handle_new_teacher();

-- Classes a teacher owns. template = 'sample-grade12-cat' marks a copy of the sample class.
create table if not exists public.classes (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name text not null,
  template text,
  class_list jsonb,
  rubric jsonb,
  outcomes jsonb,
  created_at timestamptz not null default now(),
  unique (owner_id, template)
);

-- Learners in a teacher's own classes.
create table if not exists public.class_learners (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  class_id bigint not null references public.classes (id) on delete cascade,
  learner_key text not null,
  name text not null,
  email text,
  previous integer,
  unique (class_id, learner_key)
);

-- Work handed in: typed essays, transcripts and practical attempt logs.
create table if not exists public.submissions (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  class_id bigint references public.classes (id) on delete cascade,
  learner_key text not null,
  kind text not null default 'essay' check (kind in ('essay', 'script', 'practical')),
  body text not null default '',
  created_at timestamptz not null default now()
);

-- Runs: one summary row per finished run. run_key is the run id the server gave it.
create table if not exists public.runs (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  run_key text not null,
  summary jsonb not null,
  created_at timestamptz not null default now(),
  unique (owner_id, run_key)
);

-- The live log of a run, line by line, so any server instance can show it.
create table if not exists public.run_events (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  run_key text not null,
  seq integer not null,
  event jsonb not null,
  unique (owner_id, run_key, seq)
);

-- Messages the Messenger wrote.
create table if not exists public.messages (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  run_key text not null,
  learner_key text not null,
  subject text not null default '',
  body text not null default '',
  status text not null default 'outbox' check (status in ('outbox', 'delivered', 'held')),
  created_at timestamptz not null default now()
);

-- Uploaded batches of photographed pages. The photos themselves live in the private "scripts" bucket.
create table if not exists public.uploads (
  id bigint generated always as identity primary key,
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  batch text not null,
  pages jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (owner_id, batch)
);

-- Row level security: a teacher sees and changes only their own rows.
do $$
declare t text;
begin
  foreach t in array array['classes', 'class_learners', 'submissions', 'runs', 'run_events', 'messages', 'uploads'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists %I on public.%I', t || '_own', t);
    execute format('create policy %I on public.%I for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid())', t || '_own', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end;
$$;

alter table public.profiles enable row level security;
drop policy if exists profiles_own on public.profiles;
create policy profiles_own on public.profiles for all to authenticated using (id = auth.uid()) with check (id = auth.uid());
revoke all on public.profiles from anon;
grant select, insert, update on public.profiles to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- Private storage for photographed scripts, one folder per teacher: {uid}/...
insert into storage.buckets (id, name, public) values ('scripts', 'scripts', false)
  on conflict (id) do nothing;

drop policy if exists scripts_own_read on storage.objects;
create policy scripts_own_read on storage.objects for select to authenticated
  using (bucket_id = 'scripts' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists scripts_own_write on storage.objects;
create policy scripts_own_write on storage.objects for insert to authenticated
  with check (bucket_id = 'scripts' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists scripts_own_delete on storage.objects;
create policy scripts_own_delete on storage.objects for delete to authenticated
  using (bucket_id = 'scripts' and (storage.foldername(name))[1] = auth.uid()::text);
