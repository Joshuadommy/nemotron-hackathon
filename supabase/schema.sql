-- Compliance Copilot: private case history
-- Run this once in Supabase Dashboard → SQL Editor.

create table if not exists public.cases (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(title) between 1 and 140),
  scenario text not null,
  verdict jsonb,
  trace jsonb not null default '[]'::jsonb,
  usage jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.cases enable row level security;

create policy "Users can read their own cases"
  on public.cases for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their own cases"
  on public.cases for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their own cases"
  on public.cases for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their own cases"
  on public.cases for delete to authenticated
  using ((select auth.uid()) = user_id);

create or replace function public.set_updated_at()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace trigger set_cases_updated_at
  before update on public.cases
  for each row execute function public.set_updated_at();

create index if not exists cases_user_updated_idx
  on public.cases (user_id, updated_at desc);
