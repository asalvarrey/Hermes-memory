
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/asalvarrey/Hermes-memory/main/assets/logo-dark.png">
    <img src="https://raw.githubusercontent.com/asalvarrey/Hermes-memory/main/assets/logo-light.png" alt="Hermes Supabase Memory" width="480">
  </picture>
</p>

<p align="center">
  <b>Persistent, cloud-native memory for Hermes Agent</b><br>
  Powered by <a href="https://supabase.com">Supabase</a> + <a href="https://github.com/pgvector/pgvector">pgvector</a>
</p>

<p align="center">
  <a href="#-features"><img src="https://img.shields.io/badge/features-9_E2E_blue?style=flat-square" alt="Features"></a>
  <a href="#-installation"><img src="https://img.shields.io/badge/install-2_steps-green?style=flat-square" alt="Install"></a>
  <img src="https://img.shields.io/badge/version-v1.1.1-orange?style=flat-square" alt="Version">
  <a href="https://github.com/asalvarrey/Hermes-memory"><img src="https://img.shields.io/badge/license-MIT-purple?style=flat-square" alt="License"></a>
  <a href="https://hermes-agent.nousresearch.com"><img src="https://img.shields.io/badge/for-Hermes_Agent-orange?style=flat-square" alt="Hermes"></a>
  <a href="https://buymeacoffee.com/asalvarrey"><img src="https://img.shields.io/badge/donate-☕_Buy_me_a_coffee-FFDD00?style=flat-square" alt="Buy me a coffee"></a>
</p>

---

## 🔔 What’s new in v1.1.1

- **Patch release, same shape** — no schema or workflow changes; this bump is about stabilizing the already-merged Supabase memory path.
- **Safer persistence writes** — profile/session sync now uses explicit conflict targets so the plugin can write cleanly in live Supabase projects.
- **Loader resilience** — the plugin stays usable in stripped Hermes environments thanks to vendored dependencies and a minimal YAML fallback.
- **Smoke-tested** — the release was verified with real read/write calls against Supabase before this note was added.

## 🔔 What’s new in v1.1.0

- **Vector memory, finally** — `sync_turn()` now writes embeddings when configured, and `prefetch()` / `supabase_search` can use `match_hermes_memory` for semantic retrieval.
- **Provider-agnostic embeddings** — the plugin owns a local `EmbedProvider` abstraction, with OpenAI on day one and VoyageAI documented as the next supported provider.
- **Safe fallback ladder** — if embeddings, the RPC, or the backend are unavailable, the plugin falls back to `ilike` and then local SQLite cache.
- **Release note** — this README reflects the new version bump for the embedding/vector-search release branch.

---

### 🏷️ Tags

`memory` · `supabase` · `pgvector` · `embeddings` · `semantic-search` · `fallback` · `hermes-agent`

> **Design note:** vector-first when available, keyword-fallback when needed, offline-safe always.

---

## 🧠 What is this?

A pluggable **memory backend** for [Hermes Agent](https://hermes-agent.nousresearch.com) that replaces the built-in SQLite storage with **cloud-hosted PostgreSQL** via Supabase.

Instead of local files that disappear when your VM dies, your agent's memory lives in the cloud — persisted, searchable, and accessible from any instance.

### Why Supabase?

| vs | Built-in (SQLite) | Honcho | **Supabase (this plugin)** |
|---|---|---|---|
| **Persistent** | ❌ Local files | ✅ Remote | ✅ **Your own DB** |
| **Semantic search** | ❌ FTS5 only | ✅ | ✅ **pgvector** |
| **Multi-instance** | ❌ | ✅ | ✅ **Any machine** |
| **Your data** | ✅ Your machine | ❌ Their servers | ✅ **Your DB, your rules** |
| **Cost** | ✅ Free | 💰 Paid tier | ✅ **Supabase free tier** |
| **RLS / Auth** | ❌ | ❌ | ✅ **PostgreSQL RLS** |
| **Real-time** | ❌ | ❌ | ✅ **Supabase Realtime** |

---

## ✨ Features

| # | Feature | Status |
|---|---|---|
| 1 | 🗄️ **Persistent memory** across sessions — survives VM resets | ✅ |
| 2 | 🔍 **Hybrid search** — pgvector vector search + PostgreSQL `ilike` fallback | ✅ |
| 3 | 👤 **User profiles** with JSONB storage | ✅ |
| 4 | 📋 **Session tracking** with auto-summarization | ✅ |
| 5 | 🧩 **Skills sync** across Hermes instances | ✅ |
| 6 | 🔄 **Auto-migration** — tables created on first `hermes memory setup` | ✅ |
| 7 | 🔐 **RLS policies** — service-role gated, anon-key ready | ✅ |
| 8 | ⏱️ **Auto-updated_at** triggers on all tables | ✅ |
| 9 | 🧠 **Embeddings pipeline** — provider-agnostic `EmbedProvider` with local config | ✅ |
| 10 | 🧹 **Clean shutdown flush** — pending syncs are flushed on `/new` and `/reset` | ✅ |

---

## 🚀 Installation

### Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com) installed
- A [Supabase](https://supabase.com) project (free tier works)
- Python 3.10+

### Step 1: Deploy the database schema

Copy and run the migration SQL in your **Supabase Dashboard → SQL Editor**:

```sql
-- Apply the schema migration first:
--   migrations/001_supabase_memory_init.sql
-- Then apply the RPC migration:
--   migrations/002_match_hermes_memory.sql
-- Or run via supabase CLI:
-- supabase db push
supabase db query --linked --file migrations/001_supabase_memory_init.sql
```

This creates:
| Table | Purpose |
|---|---|
| `hermes_memory` | Memory entries with vector embeddings |
| `hermes_users` | User profiles and preferences |
| `hermes_sessions` | Session tracking with summaries |
| `hermes_skills` | Cross-instance skill synchronization |

### Step 2: Install the plugin

```bash
# 1. Copy plugin files to Hermes user plugins directory
mkdir -p ~/.hermes/plugins/supabase
cp supabase_memory/* ~/.hermes/plugins/supabase/

# 2. Install Python dependencies
pip install supabase

# 3. Add credentials to your .env
cat >> ~/.hermes/.env << 'EOF'
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_...
SUPABASE_ANON_KEY=sb_publishable_...
EOF
```

### Step 3: Configure Hermes

```yaml
# ~/.hermes/config.yaml
memory:
  provider: supabase
```

### Step 4: Activate

```bash
hermes memory setup    # Interactive setup
# or just start a new session — auto-detects config
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                 Hermes Agent                     │
│  ┌───────────────────────────────────────────┐  │
│  │        AIAgent (run_agent.py)             │  │
│  │         ┌──────────────────┐              │  │
│  │         │   MemoryManager  │              │  │
│  │         └────────┬─────────┘              │  │
│  └──────────────────┼────────────────────────┘  │
│                     │                            │
│                     ▼                            │
│  ┌───────────────────────────────────────────┐  │
│  │    SupabaseMemoryProvider (this plugin)    │  │
│  │         ┌──────────────────────┐          │  │
│  │         │   supabase-py SDK    │          │  │
│  │         │   + EmbedProvider     │          │  │
│  │         └──────────┬───────────┘          │  │
│  └────────────────────┼──────────────────────┘  │
└───────────────────────┼─────────────────────────┘
                        │
                   🌐 HTTPS / REST
                        │
┌───────────────────────┼─────────────────────────┐
│          Supabase Project                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ PostgREST│ │  pgvector │ │   RLS    │         │
│  │   API    │ │          │ │ Policies │         │
│  └──────────┘ └──────────┘ └──────────┘         │
│  ┌──────────────────────────────────────────┐   │
│  │          PostgreSQL 16                     │   │
│  │  ┌──────────┐ ┌────────┐ ┌───────────┐   │   │
│  │  │ hermes_  │ │ hermes │ │ hermes_   │   │   │
│  │  │ memory   │ │ _users │ │ sessions  │   │   │
│  │  └──────────┘ └────────┘ └───────────┘   │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## 🔧 How it works

Every conversation turn flows through the plugin:

```
User: "Hola, soy Antonov"
  │
  ▼
┌──────────────────────────────────────────────┐
│ 1. prefetch(query)                            │
│    → Tries vector search first                 │
│    → Falls back to ilike + local cache         │
│    → Injects into LLM system prompt            │
├──────────────────────────────────────────────┤
│ 2. LLM generates response                     │
├──────────────────────────────────────────────┤
│ 3. sync_turn(user_msg, asst_msg)              │
│    → Saves both to hermes_memory table        │
│    → Writes embeddings when configured        │
│    → Updates hermes_sessions                  │
└──────────────────────────────────────────────┘
```

### Available Tools

| Tool | Description |
|---|---|
| `supabase_search` | Search by keyword or vector similarity |
| `supabase_profile` | Read or update user preferences |

---

## 🔒 Security

- **Service role key** is used for write operations (bypasses RLS)
- **Anon key** can be used for read-only public access
- All tables have **Row Level Security** enabled
- Connection is always **HTTPS/SSL**
- Credentials stored in `.env` (never in code)

---

## 🧪 Development

```bash
# Clone
git clone https://github.com/asalvarrey/Hermes-memory.git
cd Hermes-memory

# Create a local supabase project for testing
supabase init
supabase start

# Run migrations
supabase db push

# Test the plugin
python -c "
import sys; sys.path.insert(0, '.')
from supabase_memory import SupabaseMemoryProvider
p = SupabaseMemoryProvider()
print(f'Provider: {p.name}')
print(f'Available: {p.is_available()}')
"
```

---

## 🗺️ Roadmap

- [ ] **`hermes memory setup` wizard** — interactive config with auto-migration
- [ ] **Multi-profile support** — isolated memory per Hermes profile
- [ ] **Session auto-summarization** — LLM-generated session summaries
- [ ] **Cron-based memory pruning** — TTL for old entries
- [ ] **Skills sync daemon** — automatically mirror skills across instances
- [ ] **VoyageAI support** — next provider for the Anthropic route

---

## 🐐 Credits

Built by [@asalvarrey](https://github.com/asalvarrey) and [Hermes Agent](https://hermes-agent.nousresearch.com).

Inspired by the Hermes plugin ecosystem — Honcho, Mem0, Hindsight, and Supermemory showed the way, Supabase provides the foundation.

---

## ☕ Support

If this plugin helps you, consider buying me a coffee:

[![\uf0c1 Buy me a coffee](https://img.shields.io/badge/Buy_me_a_coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/asalvarrey)

---

<p align="center">
  <sub>Made with 🐙, ☕, and 🔥 between México and wherever the VPN says we are</sub>
</p>
