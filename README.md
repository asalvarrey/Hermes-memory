
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
  <img src="https://img.shields.io/badge/version-v1.2.1-orange?style=flat-square" alt="Version">
  <a href="https://github.com/asalvarrey/Hermes-memory"><img src="https://img.shields.io/badge/license-MIT-purple?style=flat-square" alt="License"></a>
  <a href="https://hermes-agent.nousresearch.com"><img src="https://img.shields.io/badge/for-Hermes_Agent-orange?style=flat-square" alt="Hermes"></a>
  <a href="https://buymeacoffee.com/asalvarrey"><img src="https://img.shields.io/badge/donate-☕_Buy_me_a_coffee-FFDD00?style=flat-square" alt="Buy me a coffee"></a>
</p>

---

## 🔔 What’s new in v1.2.1

- **Ollama embeddings** — the embedding provider can now run against any Ollama-compatible endpoint. The plugin keeps the vector path on `pgvector` and uses `nomic-embed-text:latest` by default for 768-dimension embeddings.
- **Ollama enhanced memory** — structured session summaries now use the same local/remote Ollama pattern through `/api/chat`, so no OpenAI key is required for enhanced memory.
- **Safer conflict handling** — profile and session writes use explicit conflict targets so repeated writes stay idempotent in Supabase.
- **Version sync** — the plugin manifest and runtime docs are aligned on the v1.2.1 release.

## 🔔 What’s new in v1.2.0

- **Dead-letter queue** — sync operations that fail 5+ times are moved to a local `dead_letter` table instead of retrying forever. `supabase_status` now reports the count.
- **Real user identity** — `user_id` is no longer hardcoded as `"default"`. The plugin reads it from Hermes session kwargs, `HERMES_USER_ID` env var, or falls back to `"default"`.
- **Enhanced Memory** (opt-in) — on session end, an LLM call produces a structured JSON summary (`topics`, `decisions`, `user_prefs`, `key_context`) stored in `hermes_sessions.metadata`. Disabled by default — costs tokens when active. See [Enhanced Memory](#-enhanced-memory-opt-in).

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
| 11 | 📬 **Dead-letter queue** — exhausted syncs archived locally, never retry-loop forever | ✅ |
| 12 | 🪪 **Real user identity** — `user_id` resolved from session context, not hardcoded | ✅ |
| 13 | 📝 **Enhanced Memory** — opt-in LLM session summaries stored as structured JSON | ✅ |

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
| `supabase_status` | Check connection health and pending sync count |

---

## 📝 Enhanced Memory (opt-in)

> ⚠️ **This feature consumes LLM tokens.** If your Ollama endpoint is remote or rate-limited, keep an eye on latency and throughput.

When enabled, the plugin calls an Ollama chat endpoint at the end of each session to produce a structured JSON summary — stored in `hermes_sessions.metadata` in Supabase. The same `summary_model` setting in `supabase_memory/plugin.yaml` controls which Ollama chat model is used. No OpenAI key is required for this path.

### When to use it

| Use case | Recommendation |
|---|---|
| Long-running personal assistant (e.g. Asteria) | ✅ Yes — rich sessions benefit from structured recall |
| Support agent with 3–5 message sessions | ⚠️ Maybe — summarization cost may exceed value |
| Ephemeral research sessions (e.g. Diana) | ❌ No — short sessions without continuity don't need persistent summaries |
| Multi-user deployment, hundreds of sessions/day | ❌ Not without monitoring costs first |

### Configuration

```yaml
# supabase_memory/plugin.yaml
embedding:
  enabled: true
  provider: ollama
  model: nomic-embed-text:latest
  dimension: 768
  base_url: https://<your-ollama-host>
  timeout_s: 30
  batch_size: 16
  strict_dimension: true

enhanced_memory:
  enabled: true                   # false by default — explicit opt-in
  max_messages_to_summarize: 20
  summary_model: qwen2.5:14b      # any Ollama chat model that can output JSON
  summary_fields:
    - topics
    - decisions
    - user_prefs
    - key_context
```

### Notes

- `embedding.base_url` must point to a reachable Ollama-compatible endpoint.
- `summary_model` should be a chat-capable Ollama model that can follow a JSON-only instruction.
- If the Ollama summary call fails for any reason, the plugin falls back to the basic session summary and shutdown continues normally.
- No API key is needed for embeddings or enhanced memory in the Ollama path.

### Output

Stored in `hermes_sessions.metadata` (JSONB):

```json
{
  "topics": ["Supabase setup", "pgvector embeddings"],
  "decisions": ["use nomic-embed-text", "enable RLS on all tables"],
  "user_prefs": {"language": "es", "timezone": "America/Mexico_City"},
  "key_context": ["user is a Python developer", "project in production since v1.1.0"]
}
```

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
