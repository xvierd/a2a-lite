# A2A Examples: Google SDK vs A2A Lite

> **Ejemplos COMPLETOS y FUNCIONALES comparando Google A2A SDK con A2A Lite.**

## ⚠️ IMPORTANTE: Instalación Correcta

### Google A2A Python SDK (OFICIAL)

```bash
# Instalación CORRECTA (con soporte HTTP obligatorio)
pip install "a2a-sdk[http-server]"
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

| Ejemplo | Google SDK | A2A Lite | Reducción |
|---------|------------|----------|-----------|
| **Hello World** | ~120 líneas | ~25 líneas | **79%** |
| **Calculator** | ~250 líneas | ~67 líneas | **73%** |
| **File Handling** | ~200 líneas | ~50 líneas | **75%** |
| **Authentication** | ~400 líneas | ~92 líneas | **77%** |
| **Streaming** | ~350 líneas | ~77 líneas | **78%** |
| **LLM Integration** | ~720 líneas | ~154 líneas | **79%** |

---

## 📁 Estructura

```
examples/
├── README.md                          # Este archivo
├── python/                            # Ejemplos Python
│   ├── 01_hello_world_google/         # SDK Oficial (~120 líneas)
│   ├── 01_hello_world_lite/           # A2A Lite (~25 líneas)
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
│   └── 09_human_in_loop_lite/         # A2A Lite - Human-in-the-loop
└── java/                              # Ejemplos Java
    ├── 01_hello_world_google/
    ├── 01_hello_world_lite/
    ├── 02_calculator_google/
    └── 02_calculator_lite/
```

---

## 🎓 Ejemplos por Dificultad

### 🟢 BÁSICO
- **01_hello_world**: Agente simple, skills básicos
- **02_calculator**: Múltiples skills, validación
- **03_file_handling**: Archivos, datos binarios

### 🟡 MEDIO
- **05_auth**: API keys, Bearer tokens, RBAC
- **06_streaming**: SSE, respuestas en tiempo real

### 🔴 AVANZADO
- **08_llm_integration**: OpenAI/Claude, memoria, tools
- **09_human_in_loop**: Confirmaciones, pausas para input

---

## 🚀 Ejecución

### Google SDK

```bash
cd python/01_hello_world_google
pip install "a2a-sdk[http-server]"
python main.py
```

### A2A Lite

```bash
cd python/01_hello_world_lite
pip install a2a-lite
python agent.py
```

---

## 📝 API Real del SDK Oficial

```python
from a2a.server.apps.rest import A2ARESTFastAPIApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler

# 1. Agent Card (con TODOS los campos requeridos)
agent_card = AgentCard(
    name="HelloAgent",
    capabilities=AgentCapabilities(),
    default_input_modes=["text"],
    default_output_modes=["text"],
    skills=[AgentSkill(id="greet", name="greet", tags=["hello"])]
)

# 2. Implementar AgentExecutor (OBLIGATORIO)
class MyExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        # Lógica del skill
        pass
    
    async def cancel(self, context, event_queue):
        # Cancelación
        pass

# 3. Crear infraestructura
task_store = InMemoryTaskStore()
queue_manager = InMemoryQueueManager()
agent_executor = MyExecutor()

# 4. Crear handler y app
handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=task_store,
    queue_manager=queue_manager
)
app = A2ARESTFastAPIApplication(
    agent_card=agent_card,
    http_handler=handler
).build()
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

Todos los ejemplos han sido validados:
- ✅ Sintaxis Python correcta
- ✅ Usan API real de `a2a-sdk`
- ✅ Incluyen `[http-server]` en requirements
- ✅ Funcionan con `python main.py`

---

## 📚 Recursos

- **A2A Protocol**: https://google.github.io/A2A/
- **Python SDK**: https://github.com/a2aproject/a2a-python
- **Instalación**: `pip install "a2a-sdk[http-server]"`
