"""Local Projects workbench. Run: python3 app.py"""

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from project_api import BASE_URL, APIError, add_todo, all_projects, complete_todo, get_project, mark_todo, summary


ROOT = Path(__file__).parent / "static"
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "127.0.0.1")


def markdown_report(data):
    lines = ["# Projects update", "", f"Generated: {data['generated_at']}", ""]
    for project in data["projects"]:
        flags = []
        if project["status"] == "blocked":
            flags.append("blocked")
        if project["overdue"]:
            flags.append(f"{len(project['overdue'])} overdue")
        if project["changed_this_week"]:
            flags.append("updated this week")
        lines.append(f"## {project['title']} ({project['status']})")
        lines.append(f"{project['completed']}/{project['total']} todos complete" + ("; " + ", ".join(flags) if flags else ""))
        for item in project["overdue"]:
            due = datetime.fromtimestamp(item["by"] / 1000).date().isoformat()
            lines.append(f"- Overdue: {item['task']} - {item['who']}, due {due}")
        lines.append("")
    lines.append("Note: 'updated this week' uses updated_at. The API exposes no change history, so this is not a diff.")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if content_type.startswith("application/json"):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        try:
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise APIError(415, "Content-Type must be application/json")
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0:
                raise APIError(400, "Invalid Content-Length")
            if size > 65536:
                raise APIError(413, "Request body is too large")
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError):
            raise APIError(400, "Expected a JSON object")

    def _handle(self):
        path = urlsplit(self.path).path
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if self.command == "GET":
            if path == "/api/health":
                return self._send(200, {"status": "ok"})
            if path == "/api/projects":
                return self._send(200, {"projects": all_projects(), "api_base_url": BASE_URL})
            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                return self._send(200, get_project(parts[2]))
            if path == "/api/summary":
                return self._send(200, summary())
            if path == "/api/summary.md":
                return self._send(200, markdown_report(summary()), "text/markdown; charset=utf-8")
            assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if path in assets:
                name, content_type = assets[path]
                return self._send(200, (ROOT / name).read_bytes(), content_type + "; charset=utf-8")
        if self.command == "POST":
            body = self._json_body()
            if path == "/api/automation/complete":
                result = complete_todo(body.get("project_id"), body.get("project"), body.get("todo_id"), body.get("task"))
                return self._send(200, result)
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "todos":
                todo = add_todo(parts[2], body.get("task"), body.get("who"), body.get("due"))
                return self._send(201, todo)
            if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "todos" and parts[5] == "mark":
                todo = mark_todo(parts[2], parts[4], body.get("done", True))
                return self._send(200, todo)
        raise APIError(404, "Not found")

    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()

    def _run(self):
        try:
            self._handle()
        except APIError as exc:
            self._send(exc.status, {"error": exc.message})
        except Exception as exc:
            self.log_error("Unhandled error: %s", exc)
            self._send(500, {"error": "Unexpected local server error"})


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Later workbench: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()
