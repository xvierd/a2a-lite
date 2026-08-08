# Batalla Naval — A2A Lite

Demo jugable del protocolo **A2A v1.0** con a2a-lite: un agente jugador (humano vs bot) y una arena agente-vs-agente. Toda la partida viaja por JSON-RPC `SendMessage` con header `A2A-Version: 1.0`.

## Qué incluye

| Archivo | Rol |
|---------|-----|
| `game.py` | Tablero 10×10, flota clásica, hit/miss/sunk |
| `strategy.py` | Estrategias `hunter` y `random` |
| `agent.py` | Jugador A2A + UI en `GET /` |
| `arena.py` | Dos agentes + espectador; movimientos con `AgentNetwork` |
| `static/index.html` | Interfaz (modo humano y `?mode=arena`) |
| `test_battleship.py` | Lógica, skills (`AgentTestClient`) y arena con stubs |

### Skills del agente

- `new_game()` — flota nueva
- `receive_shot(row, col)` — disparo del rival sobre este tablero
- `next_shot()` — siguiente casilla a disparar
- `report_shot_result(row, col, result, ship?)` — feedback a la estrategia
- `status()` — barcos restantes / contadores

## Requisitos

```bash
# Desde la raíz del repo (recomendado en desarrollo):
pip install -e packages/python

# O solo las deps del ejemplo (PyPI, cuando 1.0 esté publicado):
pip install -r requirements.txt
```

## Modo humano vs agente

```bash
cd examples/python/11_battleship_lite
python agent.py
```

Abre [http://localhost:8790/](http://localhost:8790/).

Variables de entorno:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BATTLESHIP_NAME` | `Capitán A2A` | Nombre del agente |
| `BATTLESHIP_STRATEGY` | `hunter` | `hunter` o `random` |
| `BATTLESHIP_PORT` | `8790` | Puerto HTTP |

Card: `http://localhost:8790/.well-known/agent-card.json`

## Modo arena (agente vs agente)

```bash
cd examples/python/11_battleship_lite
python arena.py
```

Abre [http://localhost:8793/?mode=arena](http://localhost:8793/?mode=arena).

Flujo A2A por turno:

1. arena → `next_shot` (atacante)
2. arena → `receive_shot` (defensor)
3. arena → `report_shot_result` (atacante)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ARENA_PORT` | `8793` | Servidor espectador (UI + `/arena/state`) |
| `ARENA_PORT_A` | `8791` | Agente A |
| `ARENA_PORT_B` | `8792` | Agente B |
| `ARENA_NAME_A` | `Capitán Hunter` | Nombre agente A (estrategia hunter) |
| `ARENA_NAME_B` | `Almirante Random` | Nombre agente B (estrategia random) |

Los únicos endpoints no-A2A son de espectáculo: `GET /arena/state`, `POST /arena/new`.

## Tests

Desde la raíz del repo:

```bash
packages/python/.venv/bin/python -m pytest examples/python/11_battleship_lite -q
```

## Por qué este ejemplo

- Muestra **multi-agente real** (`AgentNetwork` / `SendMessage`), no mocks en la UI de arena.
- Sirve UI junto al agent card sin tocar el tráfico A2A (wrapper ASGI mínimo).
- Separación limpia: `ArenaEngine` acepta un `call` async — A2A en prod, stubs en tests.
