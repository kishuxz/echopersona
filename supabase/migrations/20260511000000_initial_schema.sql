create extension if not exists "uuid-ossp";

create table public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  full_name text,
  avatar_url text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table public.personas (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  name text not null,
  stories text[] not null default '{}',
  personality_traits text[] not null default '{}',
  speaking_style text not null default '',
  voice_id text,
  did_avatar_url text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table public.conversations (
  id uuid default uuid_generate_v4() primary key,
  persona_id uuid references public.personas(id) on delete cascade not null,
  user_id uuid references auth.users(id) on delete cascade not null,
  messages jsonb not null default '[]',
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create index personas_user_id_idx on public.personas(user_id);
create index conversations_persona_id_idx on public.conversations(persona_id);
create index conversations_user_id_idx on public.conversations(user_id);

alter table public.profiles enable row level security;
alter table public.personas enable row level security;
alter table public.conversations enable row level security;

create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

create policy "Users can insert own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

create policy "Users can view own personas"
  on public.personas for select
  using (auth.uid() = user_id);

create policy "Users can create own personas"
  on public.personas for insert
  with check (auth.uid() = user_id);

create policy "Users can update own personas"
  on public.personas for update
  using (auth.uid() = user_id);

create policy "Users can delete own personas"
  on public.personas for delete
  using (auth.uid() = user_id);

create policy "Users can view own conversations"
  on public.conversations for select
  using (auth.uid() = user_id);

create policy "Users can create own conversations"
  on public.conversations for insert
  with check (auth.uid() = user_id);

create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data->>'full_name');
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

create or replace function public.handle_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger personas_updated_at
  before update on public.personas
  for each row execute procedure public.handle_updated_at();

create trigger conversations_updated_at
  before update on public.conversations
  for each row execute procedure public.handle_updated_at();
