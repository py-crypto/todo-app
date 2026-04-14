-- Run in Supabase SQL Editor before using the app.

create extension if not exists "pgcrypto";

create table if not exists public.todos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null,
  is_done boolean not null default false,
  created_at timestamptz not null default now(),
  completed_at timestamptz null
);

create index if not exists todos_user_id_created_at_idx
  on public.todos (user_id, created_at desc);

alter table public.todos enable row level security;
alter table public.todos force row level security;

drop policy if exists "todos_select_own" on public.todos;
drop policy if exists "todos_insert_own" on public.todos;
drop policy if exists "todos_update_own" on public.todos;
drop policy if exists "todos_delete_own" on public.todos;

create policy "todos_select_own"
  on public.todos for select
  using (auth.uid() = user_id);

create policy "todos_insert_own"
  on public.todos for insert
  with check (auth.uid() = user_id);

create policy "todos_update_own"
  on public.todos for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "todos_delete_own"
  on public.todos for delete
  using (auth.uid() = user_id);

-- Enable Realtime for this table (ignore error if already added).
alter publication supabase_realtime add table public.todos;
