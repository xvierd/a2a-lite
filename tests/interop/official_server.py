"""Loopback reference server built solely with the official A2A Python SDK."""

import argparse
import json
from importlib.metadata import version

import uvicorn
from a2a.helpers import new_task, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.routes.rest_routes import create_rest_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState
from a2a.utils.errors import InvalidParamsError, TaskNotCancelableError
from starlette.applications import Starlette
from starlette.routing import Mount


class ReferenceExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        payload = json.loads(context.get_user_input())
        skill = payload["skill"]
        if skill in ("greet", "tenant"):
            text = payload["params"]["text"] if skill == "greet" else context.tenant
            await event_queue.enqueue_event(new_text_message(text, context_id=context.context_id))
            return

        task = new_task(context.task_id, context.context_id, TaskState.TASK_STATE_SUBMITTED)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        if skill == "taskProbe":
            await updater.complete(new_text_message(task.id, context_id=task.context_id, task_id=task.id))
        elif skill == "stream":
            for chunk in ("one", "two"):
                await updater.add_artifact([new_text_part(chunk)])
            # The third chunk proves that the Lite iterator consumed the terminal event.
            await updater.complete(new_text_message("three", context_id=task.context_id, task_id=task.id))
        elif skill == "streamError":
            await updater.add_artifact([new_text_part(f"before-error:{context.tenant}")])
            raise InvalidParamsError("intentional stream error")
        else:
            raise InvalidParamsError(f"Unknown fixture skill {skill!r}")

    async def cancel(self, context, event_queue):
        raise TaskNotCancelableError()


def card_for(url, tenant=""):
    interfaces = [
        AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0"),
    ]
    if tenant:
        interfaces = [
            AgentInterface(url=url + path, protocol_binding=binding, protocol_version="1.0", tenant=tenant)
            for path, binding in (("/rest", "HTTP+JSON"), ("/rpc", "JSONRPC"))
        ]
    return AgentCard(
        name="Official SDK reference",
        description="Loopback interoperability fixture",
        version=version("a2a-sdk"),
        supported_interfaces=interfaces,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(id=skill, name=skill, description=skill, tags=["interop"])
            for skill in ("greet", "tenant", "taskProbe", "stream", "streamError")
        ],
    )


def build_app(port):
    url = f"http://127.0.0.1:{port}"
    card = card_for(url)
    handler = DefaultRequestHandler(agent_executor=ReferenceExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, "/"),
        *create_jsonrpc_routes(handler, "/rpc"),
        Mount("/rest", routes=create_rest_routes(handler)),
    ]
    for tenant in ("blue", "green"):
        routes.extend(
            create_agent_card_routes(card_for(url, tenant), card_url=f"/{tenant}/.well-known/agent-card.json")
        )
    return Starlette(routes=routes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["server"])
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if version("a2a-sdk") != "1.3.1":
        parser.error("The official reference server requires a2a-sdk[http-server]==1.3.1")
    uvicorn.run(build_app(args.port), host="127.0.0.1", port=args.port, log_level="warning")
