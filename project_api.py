"""Small adapter for the hosted, undocumented Projects API."""

import json
import os
from datetime import date, datetime, time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


BASE_URL = os.environ.get(
    "LATER_API_BASE_URL",
    "https://fde-takehome-projects-api-hkbn2zj27a-ue.a.run.app",
).rstrip("/")


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        BASE_URL + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            message = json.load(exc).get("error", exc.reason)
        except (ValueError, AttributeError):
            message = exc.reason
        raise APIError(exc.code, str(message)) from exc
    except (URLError, TimeoutError) as exc:
        raise APIError(502, f"Projects API unavailable: {exc}") from exc


def _segment(value):
    if not isinstance(value, str) or not value.strip():
        raise APIError(400, "An ID is required")
    return quote(value, safe="")


def all_projects():
    """The upstream defaults to five results, even if more projects exist."""
    projects = []
    offset = 0
    while True:
        page = _request("GET", "/api/v1/proj?" + urlencode({"from": offset, "take": 50}))
        batch = page.get("projects", [])
        if not isinstance(batch, list):
            raise APIError(502, "Unexpected project list response")
        projects.extend(batch)
        offset += len(batch)
        if not batch or offset >= page.get("total", offset):
            return projects


def get_project(project_id):
    return _request("GET", f"/api/v1/proj/{_segment(project_id)}")


def due_timestamp(value):
    if isinstance(value, bool):
        raise APIError(400, "Due date must be YYYY-MM-DD or epoch milliseconds")
    if isinstance(value, (int, float)):
        return int(value)
    try:
        day = date.fromisoformat(value)
        # Noon local time keeps a date-only input on that date in the local UI.
        return int(datetime.combine(day, time(hour=12)).astimezone().timestamp() * 1000)
    except (TypeError, ValueError):
        raise APIError(400, "Due date must be YYYY-MM-DD or epoch milliseconds")


def add_todo(project_id, task, who, due):
    if not isinstance(task, str) or not task.strip():
        raise APIError(400, "Task is required")
    if not isinstance(who, str) or not who.strip():
        raise APIError(400, "Assignee is required")
    return _request(
        "POST",
        f"/api/v1/proj/{_segment(project_id)}/items/add",
        {"task": task.strip(), "who": who.strip(), "by": due_timestamp(due)},
    )


def mark_todo(project_id, todo_id, done=True):
    if not isinstance(done, bool):
        raise APIError(400, "done must be true or false")
    return _request(
        "POST",
        f"/api/v1/proj/{_segment(project_id)}/items/{_segment(todo_id)}/mark",
        {"flag": "yes" if done else "no"},
    )


def resolve_project(projects, project_id=None, project=None):
    if project_id is not None and not isinstance(project_id, str):
        raise APIError(400, "project_id must be a string")
    if project is not None and not isinstance(project, str):
        raise APIError(400, "project must be a string")
    if project_id:
        matches = [p for p in projects if p.get("id") == project_id]
    elif project:
        matches = [p for p in projects if p.get("title", "").casefold() == project.casefold()]
    else:
        raise APIError(400, "project_id or exact project title is required")
    if len(matches) != 1:
        raise APIError(404 if not matches else 409, "Project not found or ambiguous")
    return matches[0]


def resolve_todo(project, todo_id=None, task=None):
    if todo_id is not None and not isinstance(todo_id, str):
        raise APIError(400, "todo_id must be a string")
    if task is not None and not isinstance(task, str):
        raise APIError(400, "task must be a string")
    items = project.get("items", [])
    if todo_id:
        matches = [item for item in items if item.get("id") == todo_id]
    elif task:
        matches = [item for item in items if item.get("task", "").casefold() == task.casefold()]
    else:
        raise APIError(400, "todo_id or exact task text is required")
    if len(matches) != 1:
        raise APIError(404 if not matches else 409, "Todo not found or ambiguous")
    return matches[0]


def complete_todo(project_id=None, project=None, todo_id=None, task=None):
    selected_project = resolve_project(all_projects(), project_id, project)
    selected_todo = resolve_todo(selected_project, todo_id, task)
    if selected_todo.get("done"):
        return {"already_complete": True, "project": selected_project, "todo": selected_todo}
    updated = mark_todo(selected_project["id"], selected_todo["id"], True)
    return {"already_complete": False, "project": selected_project, "todo": updated}


def summary(projects=None):
    projects = projects if projects is not None else all_projects()
    today = datetime.now().astimezone().date()
    week_start = today.toordinal() - today.weekday()
    rows = []
    for project in projects:
        items = project.get("items", [])
        active = project.get("status", "").lower() not in {"wrapped", "dropped"}
        overdue = [
            item for item in items
            if active and not item.get("done") and isinstance(item.get("by"), (int, float))
            and datetime.fromtimestamp(item["by"] / 1000).date() < today
        ]
        updated = project.get("updated_at")
        changed_this_week = isinstance(updated, (int, float)) and (
            week_start <= datetime.fromtimestamp(updated / 1000).date().toordinal() <= today.toordinal()
        )
        rows.append({
            "id": project.get("id"),
            "title": project.get("title"),
            "status": project.get("status"),
            "updated_at": updated,
            "changed_this_week": changed_this_week,
            "completed": sum(bool(item.get("done")) for item in items),
            "total": len(items),
            "overdue": overdue,
            "stuck": project.get("status", "").lower() == "blocked" or bool(overdue),
        })
    return {"generated_at": datetime.now().astimezone().isoformat(), "projects": rows}
