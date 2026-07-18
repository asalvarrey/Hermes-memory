
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/asalvarrey/Hermes-memory/main/assets/logo-dark.png">
    <img src="https://raw.githubusercontent.com/asalvarrey/Hermes-memory/main/assets/logo-light.png" alt="Hermes Supabase Memory" width="480">
  </picture>
</p>

<p align="center">
  <b>🧠 Memoria persistente en la nube para Hermes Agent</b><br>
  Impulsado por <a href="https://supabase.com">Supabase</a> + <a href="https://github.com/pgvector/pgvector">pgvector</a>
</p>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/📖-English-blue?style=flat-square" alt="English"></a>
  <a href="#-características"><img src="https://img.shields.io/badge/features-9_E2E-brightgreen?style=flat-square" alt="Features"></a>
  <a href="#-instalación"><img src="https://img.shields.io/badge/install-2_pasos-success?style=flat-square" alt="Install"></a>
  <a href="https://github.com/asalvarrey/Hermes-memory"><img src="https://img.shields.io/badge/license-MIT-purple?style=flat-square" alt="License"></a>
  <a href="https://buymeacoffee.com/asalvarrey"><img src="https://img.shields.io/badge/donar-☕_Cafecito-FFDD00?style=flat-square" alt="Cafecito"></a>
  <img src="https://img.shields.io/badge/version-v1.2.1-orange?style=flat-square" alt="Version">
</p>

---

## 🔔 Novedades en v1.2.1

- **Diagnóstico de memoria local-first** — `supabase_status` ahora reporta el project ref de
  Supabase, la ruta de la caché local, la edad de la cola y un resumen de salud del sync para que
  el backend siga siendo legible incluso sin conexión.
- **Punteros de identidad del backend** — el plugin guarda la identidad del backend en la caché
  local, dejando una pista auditable para cada sesión sobre qué proyecto de Supabase la sostuvo.
- **Compatibilidad de embeddings** — los vectores se normalizan al tamaño esperado por el esquema
  y las entradas de embedding se recortan con más cuidado para evitar payloads demasiado grandes.
- **Alineación del esquema** — los manifests y la documentación ahora reflejan el objetivo real de
  embeddings (`1536`) y el límite más corto de entrada (`2048` caracteres).

### 🛠️ Pase de mantenimiento actual

Este repositorio recibió una mejora operativa pequeña, pero importante, para que el backend de
Supabase sea más confiable y más fácil de depurar:

- **Identidad del backend en el status** — `supabase_status` ahora expone el project ref de
  Supabase, la ruta de la caché local, la edad de la cola y un resumen de salud del sync.
- **Diagnóstico local-first** — el plugin guarda la identidad del backend en la caché local, así
  que las sesiones offline siguen dejando una pista legible para auditar.
- **Compatibilidad de embeddings** — los vectores se normalizan al tamaño esperado por el esquema
  y las entradas de embedding se recortan con más cuidado para evitar payloads demasiado grandes.
- **Alineación del esquema** — el manifest ahora documenta el objetivo real de embeddings
  (`1536`) y el límite más corto de entrada (`2048` caracteres).

### 🏷️ Tags


`memory` · `supabase` · `pgvector` · `embeddings` · `semantic-search` · `fallback` · `hermes-agent`

> **Nota de diseño:** primero vector, luego keyword, y siempre con salida segura offline.

---

## 🧠 ¿Qué es esto?

Un **backend de memoria conectable** para [Hermes Agent](https://hermes-agent.nousresearch.com) que reemplaza el almacenamiento SQLite local con **PostgreSQL en la nube** vía Supabase.

En lugar de archivos locales que desaparecen si la VM muere, la memoria de tu agente vive en la nube — persistida, buscable y accesible desde cualquier instancia.

### ¿Por qué Supabase?

| vs | SQLite (built-in) | Honcho | **Supabase (este plugin)** |
|---|---|---|---|
| **Persistente** | ❌ Archivos locales | ✅ Remoto | ✅ **Tu propia DB** |
| **Búsqueda semántica** | ❌ Solo FTS5 | ✅ | ✅ **pgvector** |
| **Multi-instancia** | ❌ | ✅ | ✅ **Cualquier máquina** |
| **Tus datos** | ✅ Tu máquina | ❌ Sus servidores | ✅ **Tu DB, tus reglas** |
| **Costo** | ✅ Gratis | 💰 Plan pago | ✅ **Free tier de Supabase** |
| **RLS / Auth** | ❌ | ❌ | ✅ **PostgreSQL RLS** |
| **Tiempo real** | ❌ | ❌ | ✅ **Supabase Realtime** |

---

## ✨ Características

| # | Característica | Estado |
|---|---|---|
| 1 | 🗄️ **Memoria persistente** entre sesiones — sobrevive reseteos de VM | ✅ |
| 2 | 🔍 **Búsqueda híbrida** — vector search con pgvector + fallback `ilike` | ✅ |
| 3 | 👤 **Perfiles de usuario** con almacenamiento JSONB | ✅ |
| 4 | 📋 **Seguimiento de sesiones** con auto-resumen | ✅ |
| 5 | 🧩 **Sincronización de skills** entre instancias de Hermes | ✅ |
| 6 | 🔄 **Auto-migración** — tablas creadas al ejecutar `hermes memory setup` | ✅ |
| 7 | 🔐 **Políticas RLS** — service-role para escritura, anon-key para lectura | ✅ |
| 8 | ⏱️ **Triggers de actualización** auto-updated_at en todas las tablas | ✅ |
| 9 | 🧠 **Pipeline de embeddings** — `EmbedProvider` agnóstico con config local | ✅ |
| 10 | 🧹 **Flush en cierre limpio** — los sync pendientes se vacían en `/new` y `/reset` | ✅ |
| 11 | 📬 **Cola de dead-letter** — los syncs agotados se archivan, sin bucles de reintento | ✅ |
| 12 | 🪪 **Identidad real de usuario** — `user_id` resuelto desde el contexto, no hardcodeado | ✅ |
| 13 | 📝 **Enhanced Memory** — resúmenes de sesión con LLM, guardados como JSON estructurado | ✅ |

---

## 🚀 Instalación

### Requisitos

- [Hermes Agent](https://hermes-agent.nousresearch.com) instalado
- Un proyecto de [Supabase](https://supabase.com) (el free tier funciona)
- Python 3.10+

### Paso 1: Despliega el esquema de base de datos

Copia y ejecuta el SQL de migración en tu **Supabase Dashboard → SQL Editor**:

```sql
-- Aplica primero la migración de esquema:
--   migrations/001_supabase_memory_init.sql
-- Luego aplica la RPC:
--   migrations/002_match_hermes_memory.sql
-- O ejecuta con el CLI de Supabase:
-- supabase db push
supabase db query --linked --file migrations/001_supabase_memory_init.sql
```

Esto crea:
| Tabla | Propósito |
|---|---|
| `hermes_memory` | Entradas de memoria con vectores |
| `hermes_users` | Perfiles de usuario y preferencias |
| `hermes_sessions` | Seguimiento de sesiones con resúmenes |
| `hermes_skills` | Sincronización de skills entre instancias |

### Paso 2: Instala el plugin

```bash
# 1. Copia los archivos al directorio de plugins de Hermes
mkdir -p ~/.hermes/plugins/supabase
cp supabase_memory/* ~/.hermes/plugins/supabase/

# 2. Instala dependencias de Python
pip install supabase

# 3. Agrega las credenciales a tu .env
cat >> ~/.hermes/.env << 'EOF'
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_...
SUPABASE_ANON_KEY=sb_publishable_...
EOF
```

### Paso 3: Configura Hermes

```yaml
# ~/.hermes/config.yaml
memory:
  provider: supabase
```

### Paso 4: Activa

```bash
hermes memory setup    # Configuración interactiva
# O simplemente inicia una nueva sesión — detecta la config automáticamente
```

---

## 🏗️ Arquitectura

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
│  │    SupabaseMemoryProvider (este plugin)    │  │
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
│          Proyecto Supabase                        │
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

## 🔧 ¿Cómo funciona?

Cada turno de la conversación fluye a través del plugin:

```
Usuario: "Hola, soy Antonov"
  │
  ▼
┌──────────────────────────────────────────────┐
│ 1. prefetch(query)                            │
│    → Prueba búsqueda vectorial primero        │
│    → Luego cae a `ilike` + caché local        │
│    → Inyecta en el prompt del sistema         │
├──────────────────────────────────────────────┤
│ 2. El LLM genera una respuesta                │
├──────────────────────────────────────────────┤
│ 3. sync_turn(msg_usuario, msg_asistente)      │
│    → Guarda ambos en hermes_memory            │
│    → Escribe embeddings cuando aplica         │
│    → Actualiza hermes_sessions                │
└──────────────────────────────────────────────┘
```

### Herramientas disponibles

| Herramienta | Descripción |
|---|---|
| `supabase_search` | Busca por palabra clave o similitud vectorial |
| `supabase_profile` | Lee o actualiza preferencias del usuario |
| `supabase_status` | Revisa el estado de la conexión y syncs pendientes |

---

## 📝 Enhanced Memory (opt-in)

> ⚠️ **Esta feature consume tokens del LLM.** Cada sesión que cierra con `enhanced_memory`
> activo genera una llamada adicional a `gpt-4o-mini`. El costo es mínimo (~$0.0002 por
> sesión típica) pero se acumula con muchos usuarios o sesiones cortas frecuentes.

Cuando está activo, el plugin llama a la API de OpenAI al cerrar cada sesión para producir
un resumen JSON estructurado — guardado en `hermes_sessions.metadata` en Supabase. Sin
dependencias nuevas: se reutiliza la misma API key del embedder, y la llamada HTTP usa
`urllib` (solo stdlib).

### ¿Cuándo usarlo?

| Caso de uso | Recomendación |
|---|---|
| Asistente personal de largo plazo (ej. Asteria) | ✅ Sí — sesiones ricas se benefician del recall estructurado |
| Agente de soporte con sesiones de 3–5 mensajes | ⚠️ Evalúa — el costo puede superar el valor |
| Sesiones efímeras de investigación (ej. Diana) | ❌ No — sesiones cortas sin continuidad no necesitan resumen persistente |
| Multi-usuario, cientos de sesiones por día | ❌ No sin monitorear costos primero |

### Configuración

```yaml
# supabase_memory/plugin.yaml
enhanced_memory:
  enabled: true                   # false por defecto — opt-in explícito
  max_messages_to_summarize: 20
  summary_model: gpt-4o-mini
  summary_fields:
    - topics
    - decisions
    - user_prefs
    - key_context
```

### Resultado

Se guarda en `hermes_sessions.metadata` (JSONB):

```json
{
  "topics": ["configuración de Supabase", "embeddings con pgvector"],
  "decisions": ["usar text-embedding-3-small", "activar RLS en todas las tablas"],
  "user_prefs": {"language": "es", "timezone": "America/Mexico_City"},
  "key_context": ["usuario es desarrollador Python", "proyecto en producción desde v1.1.0"]
}
```

Si la llamada al LLM falla por cualquier motivo, el plugin vuelve al resumen básico — el cierre nunca se bloquea.

---

## 🔒 Seguridad

- **Service role key** se usa para escritura (bypassea RLS)
- **Anon key** puede usarse para solo lectura pública
- Todas las tablas tienen **Row Level Security** activado
- La conexión es siempre **HTTPS/SSL**
- Credenciales almacenadas en `.env` (nunca en código)

---

## 🧪 Desarrollo

```bash
# Clonar
git clone https://github.com/asalvarrey/Hermes-memory.git
cd Hermes-memory

# Crear un proyecto local de Supabase para pruebas
supabase init
supabase start

# Ejecutar migraciones
supabase db push

# Probar el plugin
python -c "
import sys; sys.path.insert(0, '.')
from supabase_memory import SupabaseMemoryProvider
p = SupabaseMemoryProvider()
print(f'Provider: {p.name}')
print(f'Available: {p.is_available()}')
"
```

---

## 🗺️ Hoja de Ruta

- [ ] **Asistente `hermes memory setup`** — configuración interactiva con auto-migración
- [ ] **Soporte multi-perfil** — memoria aislada por perfil de Hermes
- [ ] **Poda programada de memoria** — TTL para entradas viejas
- [ ] **Demonio de sincronización de skills** — mirror automático entre instancias
- [ ] **Soporte VoyageAI** — siguiente provider para la ruta Anthropic

---

## 🐐 Créditos

Construido por [@asalvarrey](https://github.com/asalvarrey) y [Hermes Agent](https://hermes-agent.nousresearch.com).

Inspirado por el ecosistema de plugins de Hermes — Honcho, Mem0, Hindsight y Supermemory mostraron el camino, Supabase puso los cimientos.

---

## ☕ Apoya el proyecto

Si este plugin te sirve, invítame un cafecito — la renta de la cafetera no se paga sola 😂

[![☕ Cafecito](https://img.shields.io/badge/Invitame_un_cafecito-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/asalvarrey)

---

<p align="center">
  <sub>Hecho con 🐙, ☕ y 🔥 entre México y donde sea que el VPN diga que estamos</sub>
</p>
