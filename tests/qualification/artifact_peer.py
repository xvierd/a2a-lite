"""One loopback JSON-RPC exchange with no lastChunk field on either artifact update."""

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/.well-known/agent-card.json":
            return self.send_error(404)
        card = {
            "name": "Fragmented artifact",
            "description": "Append two fragments, close with a terminal status",
            "version": "1",
            "capabilities": {"streaming": True},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [
                {
                    "id": "pieces",
                    "name": "Pieces",
                    "description": "Text fragments",
                    "tags": ["test"],
                }
            ],
            "supportedInterfaces": [
                {
                    "url": f"http://127.0.0.1:{self.server.server_port}/rpc",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(card).encode())

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/rpc" or request["method"] != "SendStreamingMessage":
            return self.send_error(400)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def emit(result):
            envelope = {"jsonrpc": "2.0", "id": request["id"], "result": result}
            self.wfile.write(f"data: {json.dumps(envelope)}\n\n".encode())
            self.wfile.flush()

        task = {
            "id": "task-1",
            "contextId": "context-1",
            "status": {"state": "TASK_STATE_WORKING"},
        }
        emit({"task": task})
        ids = {"taskId": task["id"], "contextId": task["contextId"]}
        for fragment, append in [("first ", False), ("second", True)]:
            artifact = {"artifactId": "same-artifact", "parts": [{"text": fragment}]}
            emit({"artifactUpdate": {**ids, "artifact": artifact, "append": append}})
        emit({"statusUpdate": {**ids, "status": {"state": "TASK_STATE_COMPLETED"}}})


@contextmanager
def artifact_peer():
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()
