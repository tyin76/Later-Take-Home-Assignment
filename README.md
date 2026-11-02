# Later Projects workbench

Submission for the AI Automation Engineer take-home. A small Python adapter connects the hosted Projects API to a local browser UI, an automation endpoint, a Markdown brief, and an MCP server. The hosted API remains the source of truth; this project stores no copy of its in-memory data.

## Run

From this directory, with Python 3.9+:

```sh
python3 app.py
```

The browser UI is available at <http://127.0.0.1:8000>. There are no package dependencies. The upstream default is `https://fde-takehome-projects-api-hkbn2zj27a-ue.a.run.app`. `LATER_API_BASE_URL`, `PORT`, and `HOST` can be set for a different API instance, local port, or bind address.

## Four workflows

| Teammate | Implemented path | Boundary |
| --- | --- | --- |
| Andy | Each todo has **Copy automation URL** for an HTTP action in Zapier, Make, n8n, or Gumloop, plus **Copy curl test** for a Terminal check. The action uses POST, `Content-Type: application/json`, and `{"flag":"yes"}`. The local `POST /api/automation/complete` endpoint also resolves exact project and task names and handles repeated completions. | Direct hosted-API URLs contain todo IDs and must be recopied if the API resets. Cloud tools need a tunnel only for the optional local endpoint. |
| Betty | The browser UI lists and searches all projects, filters by status or overdue work, shows project details, and adds, completes, or reopens todos. | The UI runs on the local machine. `HOST=0.0.0.0` permits LAN access, but there is no authentication. |
| Carlos | Overview highlights blocked projects, overdue tasks, completion counts, and projects updated this week. `GET /api/summary.md` produces a brief with overdue tasks and due dates for manual sharing. | “Updated this week” comes from `updated_at`; the API has no change history, so the brief cannot identify the exact changes. |
| Dan | `mcp_server.py` exposes `list_projects`, `get_project`, `list_overdue`, `add_todo`, and `mark_todo` to a local MCP-capable LLM client. | This is a STDIO server, not a hosted ChatGPT web plugin. Client setup is required; `LATER_DEFAULT_ASSIGNEE` optionally maps “me” to an assignee. |

An MCP client launches `python3 /absolute/path/to/Later/mcp_server.py`; `app.py` is not required for MCP. The browser UI and MCP server use the same API adapter.

## API findings and choices

- `GET /api/v1/proj` is paginated. The default response contained five projects with `total: 7`; the adapter follows `from` and `take` to retrieve all pages.
- Project details are at `GET /api/v1/proj/{project_id}`. Todos are nested under projects. Adding one uses `POST /api/v1/proj/{project_id}/items/add` with `task`, `who`, and `by` in epoch milliseconds.
- Completion uses `POST /api/v1/proj/{project_id}/items/{todo_id}/mark` with `{"flag":"yes"}` or `{"flag":"no"}`. The adapter translates date-only inputs and booleans into those upstream values.
- The implemented scope covers reading projects, adding todos, and marking todos. Project creation, editing, deletion, and todo deletion are omitted because the four selected workflows do not require them. No database, scheduled sender, or production authentication was added.

