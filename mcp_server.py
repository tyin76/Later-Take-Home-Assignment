"""Dependency-free MCP stdio server for the Projects API."""

import json
import os
import sys
from datetime import datetime

from project_api import APIError, add_todo, all_projects, get_project, mark_todo, summary

SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}


TOOLS = [
    {
        "name": "list_projects",
        "description": "List every project, including pages after the first five. Use this to find an exact project ID before writing.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_project",
        "description": "Get one project's status, description, and todos by ID.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]},
    },
    {
        "name": "list_overdue",
        "description": "List open, overdue todos across active projects, plus blocked project flags. Dates use the computer's local time zone.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_todo",
        "description": "Add a todo to an existing project. Resolve relative dates such as Friday to YYYY-MM-DD first. Supply an actual assignee name; 'me' uses LATER_DEFAULT_ASSIGNEE if configured. Confirm the project if the name is ambiguous.",
        "inputSchema": {"type": "object", "properties": {
            "project_id": {"type": "string", "description": "Exact project ID from list_projects"},
            "task": {"type": "string"}, "who": {"type": "string"},
            "due": {"type": "string", "description": "Local date in YYYY-MM-DD format"},
        }, "required": ["project_id", "task", "who", "due"]},
    },
    {
        "name": "mark_todo",
        "description": "Mark an existing todo complete or reopen it. Use exact project and todo IDs after reading the project.",
        "inputSchema": {"type": "object", "properties": {
            "project_id": {"type": "string"}, "todo_id": {"type": "string"},
            "done": {"type": "boolean", "default": True},
        }, "required": ["project_id", "todo_id"]},
    },
]


def call_tool(name, args):
    if name == "list_projects":
        return all_projects()
    if name == "get_project":
        return get_project(args["project_id"])
    if name == "list_overdue":
        report = summary()
        return {
            "generated_at": report["generated_at"],
            "projects": [
                {"id": p["id"], "title": p["title"], "status": p["status"], "overdue": [
                    {**todo, "due_date": datetime.fromtimestamp(todo["by"] / 1000).date().isoformat()}
                    for todo in p["overdue"]
                ]}
                for p in report["projects"] if p["stuck"]
            ],
        }
    if name == "add_todo":
        who = args["who"]
        if who.casefold() == "me":
            who = os.environ.get("LATER_DEFAULT_ASSIGNEE", "")
            if not who:
                raise APIError(400, "Set LATER_DEFAULT_ASSIGNEE or provide a name instead of 'me'")
        return add_todo(args["project_id"], args["task"], who, args["due"])
    if name == "mark_todo":
        return mark_todo(args["project_id"], args["todo_id"], args.get("done", True))
    raise APIError(404, f"Unknown tool: {name}")


def dispatch(message):
    method = message.get("method")
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOLS else "2025-11-25"
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "later-projects", "version": "0.1.0"},
            "instructions": "Use list_projects to find an exact project ID before writes. Resolve ambiguous names and relative dates before calling add_todo or mark_todo.",
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            value = call_tool(params.get("name"), params.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
        except (APIError, KeyError, TypeError) as exc:
            return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
    return None


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if "id" not in message:
                continue  # Notification, including notifications/initialized.
            result = dispatch(message)
            if result is None:
                response = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method not found"}}
            else:
                response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
