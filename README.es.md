
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
</p>

---

## 🔔 Novedades en v1.0.2

- **Flush en cierre limpio** — `shutdown()` ahora fuerza el vaciado de cualquier sync pendiente hacia Supabase antes de `/new`, `/reset` o al salir del proceso.
- **Sin pérdida por idle timeout** — las escrituras en cola se confirman antes, sin esperar a un cleanup tardío.

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
| 2 | 🔍 **Búsqueda semántica** vía PostgreSQL `ilike` (pgvector próximamente) | ✅ |
| 3 | 👤 **Perfiles de usuario** con almacenamiento JSONB | ✅ |
| 4 | 📋 **Seguimiento de sesiones** con auto-resumen | ✅ |
| 5 | 🧩 **Sincronización de skills** entre instancias de Hermes | ✅ |
| 6 | 🔄 **Auto-migración** — tablas creadas al ejecutar `hermes memory setup` | ✅ |
| 7 | 🔐 **Políticas RLS** — service-role para escritura, anon-key para lectura | ✅ |
| 8 | ⏱️ **Triggers de actualización** auto-updated_at en todas las tablas | ✅ |
| 9 | 🧹 **Flush en cierre limpio** — los sync pendientes se vacían en `/new` y `/reset` | ✅ |

---

## 🚀 Instalación

### Requisitos

- [Hermes Agent](https://hermes-agent.nousresearch.com) instalado
- Un proyecto de [Supabase](https://supabase.com) (el free tier funciona)
- Python 3.10+

### Paso 1: Despliega el esquema de base de datos

Copia y ejecuta el SQL de migración en tu **Supabase Dashboard → SQL Editor**:

```sql
-- Copia de: migrations/001_supabase_memory_init.sql
-- O ejecuta con el CLI de Supabase:
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
│    → Busca en la memoria pasada contexto      │
│    → Inyecta en el prompt del sistema         │
├──────────────────────────────────────────────┤
│ 2. El LLM genera una respuesta                │
├──────────────────────────────────────────────┤
│ 3. sync_turn(msg_usuario, msg_asistente)      │
│    → Guarda ambos en hermes_memory            │
│    → Actualiza hermes_sessions                │
└──────────────────────────────────────────────┘
```

### Herramientas disponibles

| Herramienta | Descripción |
|---|---|
| `supabase_search` | Busca entradas de memoria por palabra clave |
| `supabase_profile` | Lee o actualiza preferencias del usuario |

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

- [ ] **Búsqueda semántica pgvector** — embedding de texto con OpenAI/Nous y búsqueda por similitud vectorial
- [ ] **Asistente `hermes memory setup`** — configuración interactiva con auto-migración
- [ ] **Soporte multi-perfil** — memoria aislada por perfil de Hermes
- [ ] **Auto-resumen de sesiones** — resúmenes generados por LLM
- [ ] **Poda programada de memoria** — TTL para entradas viejas
- [ ] **Demonio de sincronización de skills** — mirror automático entre instancias

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
