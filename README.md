
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
  <a href="#-features"><img src="https://img.shields.io/badge/features-8_E2E_blue?style=flat-square" alt="Features"></a>
  <a href="#-installation"><img src="https://img.shields.io/badge/install-2_steps-green?style=flat-square" alt="Install"></a>
  <a href="https://github.com/asalvarrey/Hermes-memory"><img src="https://img.shields.io/badge/license-MIT-purple?style=flat-square" alt="License"></a>
  <a href="https://hermes-agent.nousresearch.com"><img src="https://img.shields.io/badge/for-Hermes_Agent-orange?style=flat-square" alt="Hermes"></a>
  <a href="https://buymeacoffee.com/asalvarrey"><img src="https://img.shields.io/badge/donate-☕_Buy_me_a_coffee-FFDD00?style=flat-square" alt="Buy me a coffee"></a>
</p>

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
| 2 | 🔍 **Semantic search** via PostgreSQL `ilike` (pgvector coming soon) | ✅ |
| 3 | 👤 **User profiles** with JSONB storage | ✅ |
| 4 | 📋 **Session tracking** with auto-summarization | ✅ |
| 5 | 🧩 **Skills sync** across Hermes instances | ✅ |
| 6 | 🔄 **Auto-migration** — tables created on first `hermes memory setup` | ✅ |
| 7 | 🔐 **RLS policies** — service-role gated, anon-key ready | ✅ |
| 8 | ⏱️ **Auto-updated_at** triggers on all tables | ✅ |

---

## 🚀 Installation

### Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com) installed
- A [Supabase](https://supabase.com) project (free tier works)
- Python 3.10+

### Step 1: Deploy the database schema

Copy and run the migration SQL in your **Supabase Dashboard → SQL Editor**:

```sql
-- Copy from: migrations/001_supabase_memory_init.sql
-- Or run via supabase CLI:
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
│    → Searches past memory for relevant context│
│    → Injects into LLM system prompt           │
├──────────────────────────────────────────────┤
│ 2. LLM generates response                     │
├──────────────────────────────────────────────┤
│ 3. sync_turn(user_msg, asst_msg)              │
│    → Saves both to hermes_memory table        │
│    → Updates hermes_sessions                  │
└──────────────────────────────────────────────┘
```

### Available Tools

| Tool | Description |
|---|---|
| `supabase_search` | Search past memory entries by keyword |
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

- [ ] **pgvector semantic search** — embed text with OpenAI/Nous and search via vector similarity
- [ ] **`hermes memory setup` wizard** — interactive config with auto-migration
- [ ] **Multi-profile support** — isolated memory per Hermes profile
- [ ] **Session auto-summarization** — LLM-generated session summaries
- [ ] **Cron-based memory pruning** — TTL for old entries
- [ ] **Skills sync daemon** — automatically mirror skills across instances

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
