<p align="center">
  <h1 align="center">A2A Lite</h1>
  <p align="center">
    <strong>La forma mas simple de construir agentes para el Protocolo A2A de Google.</strong>
  </p>
  <p align="center">
    <a href="#instalacion">Instalacion</a> &bull;
    <a href="#inicio-rapido">Inicio Rapido</a> &bull;
    <a href="#complejidad-progresiva">Caracteristicas</a> &bull;
    <a href="#ejemplos">Ejemplos</a> &bull;
    <a href="ROADMAP.md">Hoja de ruta</a>
  </p>
</p>

---

A2A Lite envuelve los SDKs oficiales de A2A ([Python](https://github.com/a2aproject/a2a-python), [TypeScript](https://github.com/a2aproject/a2a-js), [Java](https://github.com/a2aproject/a2a-java)) para darte una API simple basada en decoradores para el **protocolo A2A v1.0**. La [matriz de características](#matriz-de-caracteristicas) detalla las funciones disponibles y las limitaciones de cada transporte.

> **SDKs de referencia (2026-10-17):** `a2a-sdk 1.2.2`, `@a2a-js/sdk 1.3.0` y `a2a-java-sdk 1.4.0.Final`. La última [especificación estable de A2A es 1.0.1](https://github.com/a2aproject/A2A/releases/tag/v1.0.1); las agent cards y la cabecera `A2A-Version` siguen usando `1.0`, según las [reglas de versionado](https://a2a-protocol.org/latest/specification/#36-versioning). La versión 1.2.0 agrega runtime administrado, identidades y tenants autorizados, persistencia PostgreSQL y modos explícitos de entrega y recuperación. El registro básico de skills se conserva. Los agentes v0.3 siguen sin estar soportados. Consulta [MIGRATION.md](MIGRATION.md) para los cambios de SDK y los pasos de migración.

> **Aprende con un agente pequeño y agrega capacidades según las necesitas.** El perfil `learning` funciona sin base de datos. `authenticated` exige identidad verificada y `durable` requiere almacenamiento compatible. Python y npm 1.2.0 están publicados; Java 1.2.0 está validado desde código fuente y su publicación en Maven Central sigue pendiente. Consulta [OPERATIONS.md](OPERATIONS.md) para límites y recuperación, y la [evidencia de 1.2.0](tests/evidence/2026-10-17-1.2.0/README.md) para resultados medidos.

## Por que A2A Lite?

|  | SDK Oficial A2A | A2A Lite |
|---|---|---|
| Hello World | ~80 lineas, 3 archivos | **8 lineas, 1 archivo** |
| Esquemas JSON | Manual | **Auto-generados desde tipos** |
| Curva de aprendizaje | Empinada | **Progresiva** |
| Herramientas CLI | — | **init · create · serve · inspect · info · test · discover · doctor** |
| Testing | Configuracion manual | **TestClient incluido** |

## Inicio Rapido

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
<th>Java</th>
</tr>
<tr>
<td>

```python
from a2a_lite import Agent

agent = Agent(
    name="Bot",
    description="Mi bot"
)

@agent.skill("saludar")
async def saludar(nombre: str):
    return f"Hola, {nombre}!"

agent.run()
```

</td>
<td>

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({
  name: 'Bot',
  description: 'Mi bot'
});

agent.skill('saludar', async ({ nombre }) =>
  `Hola, ${nombre}!`
);

agent.run();
```

</td>
<td>

```java
var agent = Agent.builder()
    .name("Bot")
    .description("Mi bot")
    .build();

agent.skill("saludar", params ->
    "Hola, " + params.get("nombre") + "!"
);

agent.run();
```

</td>
</tr>
</table>

El agente publica su AgentCard A2A v1.0. Los clientes deben usar uno de los transportes que anuncia; consulta la matriz de características para sus límites.

## Instalacion

### Python
```bash
pip install a2a-lite
# o
uv add a2a-lite
```

### TypeScript
```bash
npm install a2a-lite
```

### Java (Gradle)

La coordenada 1.2.0 corresponde al código de este repositorio; aún no está publicada en Maven Central. Para ejecutarla ahora, usa los [ejemplos con compilación local](examples/java/README.md). Los consumidores Maven deben aplicar los BOM indicados en la [guía Java](packages/java/README.md#installation).
```groovy
dependencies {
    implementation 'io.github.xvierd:a2a-lite:1.2.0'
    implementation 'io.javalin:javalin:7.2.3'   // Java 17+
}
```

---

## Complejidad Progresiva

A2A Lite sigue la filosofia de *usa solo lo que necesitas*. Empieza con una habilidad basica y agrega capacidades a medida que tu agente crece.

### Nivel 1 — Solo Funciona

```python
from a2a_lite import Agent

agent = Agent(name="Bot", description="Un bot")

@agent.skill("saludar")
async def saludar(nombre: str) -> str:
    return f"Hola, {nombre}!"

agent.run()
```

### Nivel 2 — Modelos Pydantic

Los esquemas de entrada/salida se generan automaticamente desde tus type hints.

```python
from pydantic import BaseModel

class Usuario(BaseModel):
    nombre: str
    email: str

@agent.skill("crear_usuario")
async def crear_usuario(usuario: Usuario) -> dict:
    return {"id": 1, "nombre": usuario.nombre}
```

### Nivel 3 — Streaming

Solo usa `yield` en lugar de `return`.

```python
@agent.skill("chat", streaming=True)
async def chat(mensaje: str):
    for palabra in mensaje.split():
        yield palabra + " "
```

### Nivel 4 — Middleware

Preocupaciones transversales (logging, metricas, rate-limiting) sin tocar el codigo de las habilidades.

```python
@agent.middleware
async def log_requests(ctx, next):
    print(f"Llamando: {ctx.skill}")
    return await next()
```

### Nivel 5 — Manejo de Archivos

Acepta y retorna archivos a traves del protocolo A2A.

```python
from a2a_lite import FilePart

@agent.skill("resumir")
async def resumir(doc: FilePart) -> str:
    contenido = await doc.read_text()
    return f"Resumen: {contenido[:100]}..."
```

### Nivel 6 — Seguimiento de Tareas

Operaciones de larga duración con actualizaciones de progreso. `TaskContext` usa el ID real del protocolo y no requiere un `task_store` adicional. Para una skill sin contexto que deba devolver una Task consultable, usa `@agent.skill("nombre", task=True)`.

```python
from a2a_lite import TaskContext

agent = Agent(name="Bot", description="Un bot")

@agent.skill("procesar")
async def procesar(datos: str, task: TaskContext) -> str:
    await task.update("working", "Iniciando...", progress=0.0)
    for i in range(10):
        await task.update("working", f"Paso {i}/10", progress=i/10)
    return "Listo!"
```

### Nivel 7 — Autenticacion

API key, Bearer y OAuth2 son opcionales en el perfil de aprendizaje. OAuth2 verifica la firma y los claims del JWT. Para rotar una API key sin cambiar la propiedad de las tareas, asigna ambas claves a una identidad estable.

```python
from a2a_lite import Agent, APIKeyAuth

agent = Agent(
    name="BotSeguro",
    description="Un bot seguro",
    auth=APIKeyAuth(principals={"clave-actual": "alumno", "clave-nueva": "alumno"}),
)
```

### Nivel 8 — Runtime administrado y persistencia

Elige el perfil y configura límites de ejecución antes de aceptar tráfico:

```python
from a2a_lite import Agent, APIKeyAuth, RuntimeConfig

agent = Agent(
    name="Bot",
    description="Un bot autenticado",
    auth=APIKeyAuth(principals={"clave-de-ejemplo": "alumno"}),
    runtime=RuntimeConfig(profile="authenticated", max_concurrent_tasks=32),
    cors_origins=["https://miapp.com"],
)
```

Para embeberlo en otra aplicación, usa `runtime = await agent.start()` y cierra el runtime con `await runtime.stop()` en un bloque `finally`. La aplicación controla las señales del proceso. El perfil `durable` requiere configurar `PersistenceConfig`, ejecutar migraciones y conservar las claves de cifrado fuera de la base de datos; no basta con activar una bandera de producción.

Los recorridos de [Python](examples/python/12_production_path/README.md), [TypeScript](examples/typescript/11_production_path/README.md) y [Java](examples/java/11_production_path_lite/README.md) muestran Message → Task → streaming → autenticación → persistencia. La cancelación es cooperativa y los efectos externos requieren idempotencia propia.

---

## Testing

Cada lenguaje incluye un `TestClient` para que puedas testear sin HTTP.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
<th>Java</th>
</tr>
<tr>
<td>

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)
result = client.call("saludar", nombre="Mundo")
assert result == "Hola, Mundo!"
```

</td>
<td>

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);
const result = await client.call('saludar', { nombre: 'Mundo' });
expect(result.data).toBe('Hola, Mundo!');
```

</td>
<td>

```java
var client = new AgentTestClient(agent);
assertThat(client.call("saludar", Map.of("nombre", "Mundo")).getData())
    .isEqualTo("Hola, Mundo!");
```

</td>
</tr>
</table>

---

## CLI (Python)

Referencia completa: [`packages/python/docs/cli.md`](packages/python/docs/cli.md).

```bash
a2a-lite init mi-agente                         # Scaffold básico
a2a-lite create mi-agente                       # Proyecto + tests + Docker
a2a-lite serve agente.py                        # Ejecutar un agente desde archivo
a2a-lite inspect http://localhost:8787          # Agent card y habilidades
a2a-lite info http://localhost:8787             # Info compacta
a2a-lite test http://localhost:8787 greet -p name=Mundo
a2a-lite discover http://localhost:8787 http://localhost:8788
a2a-lite doctor                                 # Entorno local
a2a-lite doctor http://localhost:8787           # + verificar A2A v1.0 remoto
a2a-lite version
```

TypeScript (`npx a2a-lite`): `init`, `inspect`, `info`, `test`, `discover`, `doctor`.
---

## A2A v1.0

Desde a2a-lite 1.0.0, los tres paquetes sirven el **protocolo A2A v1.0** sobre los SDKs oficiales 1.x:

- **Transporte JSON-RPC** — Python, TypeScript, Java.
- **Transporte REST (HTTP+JSON)** — Python y TypeScript; Java actualmente sirve y anuncia solo JSON-RPC.
- **Transporte gRPC** — Python **experimental** (`pip install 'a2a-lite[grpc]'`, `agent.run_grpc()`); TypeScript/Java planeado.
- **Streaming SSE y ciclo de vida de tareas** — Python, TypeScript y el servidor Java Javalin usan los handlers oficiales para streaming, consulta y cancelación de tareas.
- **Push notifications por tarea** (`TaskPushNotificationConfig`) y **`securitySchemes` en la agent card** — en los tres lenguajes.
- **Signed Agent Cards** — TypeScript (experimental, `signAgentCard` / `verifyAgentCard`); Python/Java planeado.
- Agent card servida en **`/.well-known/agent-card.json`** (la ruta antigua `agent.json` ya no existe).
- **Sin compatibilidad con v0.3** — los clientes lite detectan cards 0.3 y fallan con un error claro.

¿Migras desde una versión anterior? El registro básico de skills no cambia; revisa los cambios de autenticación, push y TaskHandle de 1.1.0 y los perfiles, límites e identidades de 1.2.0. Consulta [MIGRATION.md](MIGRATION.md) para breaking changes, pasos por lenguaje y tablas de equivalencia SDK 0.3 → 1.x.

---

## Matriz de Caracteristicas

| Caracteristica | Python | TypeScript | Java |
|---|:---:|:---:|:---:|
| **Protocolo (A2A v1.0)** | | | |
| Protocolo A2A v1.0 | ✅ | ✅ | ✅ |
| Transporte JSON-RPC | ✅ | ✅ | ✅ |
| Transporte REST (HTTP+JSON) | ✅ | ✅ | 🔜 planeado¹ |
| Transporte gRPC | ✅ experimental² | 🔜 planeado | 🔜 planeado |
| `securitySchemes` en la agent card | ✅ | ✅ | ✅ |
| Signed Agent Cards | 🔜 planeado | ✅ experimental | 🔜 planeado |
| `ListTasks` filtrado por propietario | ✅ | ✅ | ✅ |
| Tenants autorizados | ✅ | ✅ | ✅ |
| Compatibilidad v0.3 | ❌ | ❌ | ❌ |
| **API Lite** | | | |
| Habilidades basicas | `@agent.skill()` | `agent.skill()` | `agent.skill()` |
| Esquemas JSON automaticos | ✅ Pydantic | ⚠️ Manual | ⚠️ Manual |
| Streaming | `yield` | `yield` | `SkillConfig.withStreaming()` |
| Middleware | `@agent.middleware` | `agent.use()` | `agent.use()` |
| Manejo de archivos | `FilePart` | `FilePart` | `FilePart` |
| Datos estructurados | `DataPart` | `DataPart` | `DataPart` |
| Salidas ricas | `Artifact` | `Artifact` | `Artifact` |
| Seguimiento de tareas | `TaskContext` | `TaskContext` | `TaskContext` |
| Auth API Key | `APIKeyAuth` | `APIKeyAuth` | `APIKeyAuth` |
| Bearer / JWT | `BearerAuth` | `BearerAuth` | `BearerAuth` |
| OAuth2 | `OAuth2Auth` | `OAuth2Auth` | `OAuth2Auth` |
| Auth compuesta | ✅ | ✅ | ✅ |
| AgentNetwork + `delegate()` | ✅ | ✅ | ✅ |
| Skills LLM (OpenAI/Anthropic/Ollama/Bedrock) | ✅ | ✅ | ✅ |
| Cliente MCP | ✅ | ✅ | — |
| Router (multi-agente) | ✅ | ✅ | ✅ |
| `get_tool_schemas()` | ✅ | ✅ | ✅ |
| Errores estructurados | ✅ | ✅ | ✅ |
| Testing | `AgentTestClient` | `AgentTestClient` | `AgentTestClient` |
| CLI | ✅ completo | ✅ (sin create/serve) | — |
| Descubrimiento multi-agente (`discover`) | ✅ CLI (URLs explícitas) | ✅ CLI (URLs explícitas) | — |
| Control de CORS | ✅ | ✅ | ✅ (Javalin) |
| TaskHandle (seguimiento de tareas remotas) | ✅ | ✅ | ✅ |
| Descubrimiento de agent card | ✅ | ✅ | ✅ |
| `get/cancel` de tareas remotas | ✅ | ✅ | ✅ |
| Streaming SSE del lado cliente | ✅ | ✅ | ✅ |
| Push notifications por tarea | ✅ | ✅ | ✅ |
| Inicio/cierre administrado y health probes | ✅ | ✅ | ✅ |
| Persistencia PostgreSQL del protocolo | ✅ | ✅ | ✅ |
| Outbox durable de callbacks | ✅ | ✅ | ✅ |

Las garantías de persistencia, entrega y coordinación requieren habilitar el adaptador y las opciones documentadas. La entrega de callbacks es al menos una vez: el receptor debe deduplicar. Con coordinación durable activa, una skill ordinaria interrumpida pasa a fallida tras expirar su lease; la recuperación con checkpoints depende del contrato de cada lenguaje. Estas capacidades no certifican disponibilidad ni capacidad de producción.

> **Nota sobre v0.3:** a2a-lite 1.0 no interopera con agentes A2A 0.3 (decision explicita — sin modo compatibilidad). Los clientes lite detectan cards 0.3 y fallan con un error claro. Consulta [MIGRATION.md](MIGRATION.md).
>
> ¹ **Java REST:** planeado. El adaptador Javalin sirve JSON-RPC en `POST /`; su agent card anuncia únicamente ese transporte implementado.
>
> ² **Python gRPC:** extra opcional (`a2a-lite[grpc]`). `agent.build_grpc_server()` / `agent.run_grpc()` sirven A2A por gRPC (standalone; combínalo con `agent.run()` si también quieres HTTP). No se activa solo con `agent.run()`.

---

## Mapeo al Protocolo A2A

Todo en A2A Lite se mapea directamente al protocolo subyacente — sin magia, sin lock-in.

| A2A Lite | Protocolo A2A |
|----------|---------------|
| `@agent.skill()` / `agent.skill()` | Agent Skills |
| `streaming=True` | SSE Streaming |
| `TaskContext.update()` | Estados del ciclo de vida de tareas |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` | Esquemas de seguridad |

---

## Ejemplos

### Showcase: Batalla naval (demo A2A jugable)

Demo multi-agente de punta a punta: llamadas reales **A2A v1.0** `SendMessage`, UI web, sin API key.

| Modo | Comando | URL |
|------|---------|-----|
| Humano vs bot | `python agent.py` | http://localhost:8790/ |
| Bot vs bot (arena) | `python arena.py` | http://localhost:8793/?mode=arena |

```bash
cd examples/python/11_battleship_lite
pip install -e ../../../packages/python   # desde un checkout
python agent.py
# o: python arena.py
```

Docs: [`examples/python/11_battleship_lite/README.md`](examples/python/11_battleship_lite/README.md)

### Google SDK vs A2A Lite — comparacion lado a lado

El directorio [`examples/`](examples/) compara ejemplos del SDK de Python e implementaciones manuales del protocolo en Java con A2A Lite. También incluye aprobación humana, almacenamiento de aplicación, la ruta progresiva durable y el [showcase de batalla naval](examples/python/11_battleship_lite/). Las guías identifican simulaciones, requisitos de proveedores y límites de cada demo; consulta [examples/README.md](examples/README.md).

### Python

| Ejemplo | Que muestra |
|---------|-------------|
| [01_hello_world.py](packages/python/examples/01_hello_world.py) | Agente mas simple (8 lineas) |
| [02_calculator.py](packages/python/examples/02_calculator.py) | Multiples habilidades |
| [03_async_agent.py](packages/python/examples/03_async_agent.py) | Operaciones async y hooks de ciclo de vida |
| [04_multi_agent/](packages/python/examples/04_multi_agent) | Dos agentes comunicandose |
| [05_with_llm.py](packages/python/examples/05_with_llm.py) | Integracion con OpenAI / Anthropic |
| [06_pydantic_models.py](packages/python/examples/06_pydantic_models.py) | Conversion automatica con Pydantic |
| [06_task_handle_discovery.py](packages/python/examples/06_task_handle_discovery.py) | TaskHandle + descubrimiento de card |
| [07_middleware.py](packages/python/examples/07_middleware.py) | Pipeline de middleware |
| [07_client_streaming.py](packages/python/examples/07_client_streaming.py) | Streaming SSE del lado cliente |
| [08_streaming.py](packages/python/examples/08_streaming.py) | Respuestas en streaming |
| [09_testing.py](packages/python/examples/09_testing.py) | TestClient incluido |
| [10_file_handling.py](packages/python/examples/10_file_handling.py) | Carga y procesamiento de archivos |
| [11_task_tracking.py](packages/python/examples/11_task_tracking.py) | Actualizaciones de progreso |
| [12_with_auth.py](packages/python/examples/12_with_auth.py) | Autenticacion |
| [13_mcp_tools.py](packages/python/examples/13_mcp_tools.py) | Integracion con servidores MCP |
| [14_multi_agent_network.py](packages/python/examples/14_multi_agent_network.py) | AgentNetwork + delegate() |
| [15_llm_openai.py](packages/python/examples/15_llm_openai.py) | Skill LLM con OpenAI |
| [16_llm_anthropic.py](packages/python/examples/16_llm_anthropic.py) | Skill LLM con Anthropic |
| [17_llm_bedrock.py](packages/python/examples/17_llm_bedrock.py) | Skill LLM con AWS Bedrock |
| [18_per_task_push.py](packages/python/examples/18_per_task_push.py) | Push notifications por tarea |
| [19_capability_negotiation.py](packages/python/examples/19_capability_negotiation.py) | Negociacion de capacidades |
| [20_streaming_negotiation.py](packages/python/examples/20_streaming_negotiation.py) | Negociacion de streaming |
| [**11_battleship_lite/**](examples/python/11_battleship_lite/) | **Showcase:** UI de batalla naval + arena multi-agente (A2A) |

TypeScript y Java tienen sus propios ejemplos: [`packages/typescript/examples/`](packages/typescript/examples/) y [`packages/java/examples/`](packages/java/examples/). El showcase de batalla naval es solo Python (a2a-lite sobre A2A real).

---

## Documentacion por Lenguaje

| Lenguaje | Paquete | Docs |
|----------|---------|------|
| Python | [`a2a-lite`](packages/python) | [packages/python/README.md](packages/python/README.md) |
| TypeScript | [`a2a-lite`](packages/typescript) | [packages/typescript/README.md](packages/typescript/README.md) |
| Java | [`a2a-lite`](packages/java) | [packages/java/README.md](packages/java/README.md) |

---

## Para Asistentes de Codigo con IA

Consulta [AGENT.md](AGENT.md) — una referencia concisa disenada para LLMs que escriben agentes A2A.

---

## Contribuir

1. Verifica si el SDK oficial de A2A ya soporta la funcionalidad
2. Disena la API mas simple posible
3. Mantenla opcional — nunca rompas el hello world de 8 lineas
4. Agrega ejemplos y tests
5. Envia un PR

Consulta [ROADMAP.md](ROADMAP.md) para ver que viene.

---

## Licencia

MIT

## Agradecimientos

- [Protocolo A2A de Google](https://google.github.io/A2A/) — El protocolo subyacente
- [A2A Python SDK](https://github.com/a2aproject/a2a-python) — SDK oficial de Python
- [A2A JS SDK](https://github.com/a2aproject/a2a-js) — SDK oficial de TypeScript
- [A2A Java SDK](https://github.com/a2aproject/a2a-java) — SDK oficial de Java
