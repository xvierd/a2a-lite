# A2A Examples: Google SDK vs A2A Lite

> **Ejemplos COMPLETOS y FUNCIONALES comparando Google A2A SDK con A2A Lite.**
>
> Migrados a **A2A protocol v1.0**: Python `a2a-sdk 1.1.2`, TypeScript `@a2a-js/sdk 1.0.1`, Java `org.a2aproject.sdk 1.1.0.Final`.

## ⚠️ IMPORTANTE: Instalación Correcta

### Google A2A Python SDK (OFICIAL)

```bash
# Instalación CORRECTA (con soporte HTTP obligatorio)
pip install "a2a-sdk[http-server]>=1.1.2,<2.0"
```

**NOTA**: Sin `[http-server]` el servidor NO funcionará.

- **PyPI**: https://pypi.org/project/a2a-sdk/
- **GitHub**: https://github.com/a2aproject/a2a-python
- **Docs**: https://google.github.io/A2A/

### A2A Lite (Simplificado)

```bash
pip install a2a-lite
```

---

## 📊 Comparación Rápida

| Ejemplo | Google SDK (main.py) | A2A Lite (agent.py) | Reducción |
|---------|----------------------|---------------------|-----------|
| **Hello World** | ~203 líneas | ~35 líneas | **83%** |
| **Calculator** | ~343 líneas | ~69 líneas | **80%** |
| **File Handling** | ~354 líneas | ~116 líneas | **67%** |
| **Authentication** | ~249 líneas | ~123 líneas | **51%** |
| **Streaming** | ~267 líneas | ~146 líneas | **45%** |
| **LLM Integration** | ~377 líneas | ~105 líneas | **72%** |

---

## 📁 Estructura

```
examples/
├── README.md                          # Este archivo
├── python/                            # Ejemplos Python
│   ├── 01_hello_world_google/         # SDK Oficial v1.0
│   ├── 01_hello_world_lite/           # A2A Lite
│   ├── 02_calculator_google/          # SDK Oficial
│   ├── 02_calculator_lite/            # A2A Lite
│   ├── 03_file_handling_google/       # SDK Oficial
│   ├── 03_file_handling_lite/         # A2A Lite
│   ├── 05_auth_google/                # SDK Oficial - Auth
│   ├── 05_auth_lite/                  # A2A Lite - Auth
│   ├── 06_streaming_google/           # SDK Oficial - Streaming
│   ├── 06_streaming_lite/             # A2A Lite - Streaming
│   ├── 08_llm_integration_google/     # SDK Oficial - LLM
│   ├── 08_llm_integration_lite/       # A2A Lite - LLM
│   ├── 09_human_in_loop_lite/         # A2A Lite - Human-in-the-loop
│   ├── 10_persistence_lite/           # A2A Lite - TaskStore + Push
│   └── 11_battleship_lite/            # A2A Lite - Batalla naval (UI + arena)
├── typescript/                        # Ejemplos TypeScript
│   └── 10_persistence_lite/           # A2A Lite - Persistencia
└── java/                              # Ejemplos Java
    ├── 01_hello_world_google/         # (+ versiones _lite de 01, 02, 03,
    ├── ...                            #   05, 06, 08, 09, 10)
    └── 10_persistence_lite/
```

---

## 🎓 Ejemplos por Dificultad

### 🟢 BÁSICO
- **01_hello_world**: Agente simple, skills básicos
- **02_calculator**: Múltiples skills, validación, artifacts
- **03_file_handling**: Archivos, datos binarios (`Part` con `raw`/`url`/`data`)

### 🟡 MEDIO
- **05_auth**: API keys, Bearer tokens, RBAC
- **06_streaming**: SSE, respuestas en tiempo real (`TaskUpdater`)

### 🔴 AVANZADO
- **08_llm_integration**: OpenAI/Claude, memoria, tools
- **09_human_in_loop** (lite): Confirmaciones en dos fases
- **10_persistence** (lite): TaskStore pluggable + push notifications
- **11_battleship** (lite): Demo jugable multi-agente con UI (humano vs bot + arena)

---

## 🚀 Ejecución

### Showcase: Batalla naval (recomendado para “ver” A2A)

```bash
cd python/11_battleship_lite
pip install -e ../../packages/python   # checkout local
python agent.py    # humano vs bot → http://localhost:8790/
# python arena.py  # bot vs bot    → http://localhost:8793/?mode=arena
```

Docs: [python/11_battleship_lite/README.md](python/11_battleship_lite/README.md)

### Google SDK

```bash
cd python/01_hello_world_google
pip install "a2a-sdk[http-server]>=1.1.2,<2.0"
python main.py
```

### A2A Lite

```bash
cd python/01_hello_world_lite
pip install a2a-lite
python agent.py
```

---

## 📝 API Real del SDK Oficial (a2a-sdk 1.x, A2A v1.0)

```python
from starlette.applications import Starlette

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities, AgentCard, AgentInterface, AgentSkill,
)

# 1. Agent Card (v1.0: endpoints en supported_interfaces, sin `url` raíz)
agent_card = AgentCard(
    name="HelloAgent",
    description="...",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(
            url="http://localhost:8787/",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[AgentSkill(id="greet", name="greet", description="...", tags=["hello"])],
)

# 2. Implementar AgentExecutor (OBLIGATORIO)
class MyExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        # Non-streaming: UN SOLO Message (regla estricta del SDK)
        await event_queue.enqueue_event(new_text_message("Hello!"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        pass

# 3. Handler + app desde route factories
#    (A2AStarletteApplication/A2ARESTFastAPIApplication fueron eliminadas en 1.x)
handler = DefaultRequestHandler(
    agent_executor=MyExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)
app = Starlette(
    routes=create_agent_card_routes(agent_card)
    + create_jsonrpc_routes(handler, rpc_url="/")
    + create_rest_routes(handler)
)
```

**Streaming / tareas** (regla estricta: el PRIMER evento debe ser el Task):

```python
from a2a.helpers import new_task_from_user_message, new_text_part
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

task = context.current_task or new_task_from_user_message(context.message)
await event_queue.enqueue_event(task)                    # 1. Task primero
updater = TaskUpdater(event_queue, task.id, task.context_id)
await updater.start_work()
await updater.update_status(
    TaskState.TASK_STATE_WORKING,
    message=updater.new_agent_message([new_text_part("chunk...")]),
)
await updater.complete()                                 # o failed()/cancel()
```

---

## 🎯 Cuándo Usar Cada Uno

### Google A2A SDK Oficial Cuando:
- Necesitas control TOTAL del ciclo de vida de tareas
- Requieres personalización profunda de handlers
- Trabajas con streaming complejo o gRPC
- Necesitas integración enterprise completa

### A2A Lite Cuando:
- Quieres construir agentes RÁPIDAMENTE
- No quieres preocuparte por infraestructura
- Prefieres decoradores sobre clases abstractas
- Necesitas auth, streaming, LLMs sin boilerplate

---

## ✅ Validación

Todos los ejemplos han sido validados contra a2a-sdk 1.1.2:
- ✅ Sintaxis Python correcta (`py_compile`)
- ✅ Usan API real de `a2a-sdk` 1.x (route factories, helpers, tipos protobuf)
- ✅ Wire v1.0 verificado en vivo (agent card, SendMessage, SendStreamingMessage)
- ✅ Tests de los ejemplos lite en verde con `pytest`

---

## 📚 Recursos

- **A2A Protocol**: https://google.github.io/A2A/
- **Python SDK**: https://github.com/a2aproject/a2a-python
- **Instalación**: `pip install "a2a-sdk[http-server]>=1.1.2,<2.0"`
