---
name: supabase-memory
description: "Persistent memory for Hermes Agent using Supabase (PostgreSQL + pgvector)"
version: 1.0.0
author: Antonov Salvarrey (@asalvarrey) + Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [memory, supabase, postgres, vector, persistent]
    homepage: https://github.com/asalvarrey/Hermes-memory
    related_plugins: [honcho, mem0, supermemory]
---

# Supabase Memory Plugin for Hermes Agent

A pluggable memory backend for Hermes Agent using **Supabase** (PostgreSQL + pgvector).

Replaces the built-in SQLite memory with a cloud-hosted PostgreSQL database, giving you:
- **Semantic search** via pgvector embeddings
- **Cross-instance memory** — share memory across machines
- **Persistent storage** — survives VM/container destruction
- **Structured queries** via SQL/JSONB
- **Row-Level Security** for multi-user setups

## Installation

### 1. Create Supabase tables

Run the SQL migration in your Supabase Dashboard SQL Editor:

```sql
-- Copy contents of migrations/001_supabase_memory_init.sql
```

### 2. Install the plugin

```bash
# From the hermes-agent source directory:
mkdir -p ~/.hermes/plugins/supabase

# Copy plugin files
cp -r supabase_memory/* ~/.hermes/plugins/supabase/

# Install Python dependency
pip install supabase
```

### 3. Configure

```yaml
# In config.yaml
memory:
  provider: supabase
  supabase:
    url: https://your-project.supabase.co
```

Set your Supabase credentials in `.env`:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_KEY=sb_secret_...
```

### 4. Activate

```bash
hermes memory setup
# or just start a new session — it auto-detects the config
```

## How It Works

1. **Each turn**: user message + assistant response are saved to `hermes_memory`
2. **Prefetch**: before each LLM call, relevant past entries are retrieved via pgvector search
3. **User profiles**: preferences and facts are stored in `hermes_users`
4. **Skills sync**: skills can be synced across instances via `hermes_skills`

## Tables

| Table | Purpose |
|-------|---------|
| `hermes_memory` | Memory entries with vector embeddings |
| `hermes_users` | User profiles and preferences |
| `hermes_sessions` | Session tracking with summaries |
| `hermes_skills` | Cross-instance skill mirroring |

## Requirements

- Supabase project with pgvector enabled (migration script handles this)
- `supabase` Python package (`pip install supabase`)

## License

MIT
