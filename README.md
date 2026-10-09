# akapal-geap-bff (Python)

The **BFF** between the logged-in `akapal-geap-chat-portal` user and the GEAP
(Google ADK / Agent Engine) agent — same job and same HTTP contract as the
TypeScript BFF, but in FastAPI and using the Agent Engine SDK instead of hand-rolled
REST.

It owns the mapping between *your* auth identity and the agent's conversation
session — the thing ADK itself does not do (see `ADK_SESSION_AND_BFF.md`).

## Two sides

- **Northbound (client):** verifies the portal's session JWT (HS256, shared
  `SESSION_SECRET`) and reads the logged-in `userId`. The login stays in the
  portal; the BFF only consumes the identity.
- **Southbound (agent):** uses `agentplatform.agent_engines.get(...)` to get the
  deployed engine, then calls its ADK operations (`async_create_session`,
  `async_stream_query`) and reads the reply out of the parsed events.

In between: a persistent `user_id -> session_id` mapping, a create-or-resume
decision, and an ownership check on every resume. The endpoints match the
TypeScript BFF exactly, so the portal needs **no changes**:

```
GET  /health
POST /api/chat   Authorization: Bearer <portal session JWT>
                 { "message": "...", "sessionId"?: "..." }
              -> { reply, userId, sessionId, resumed }
```

`resumed=false` means a new agent session was created for this turn.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate            # or: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # set SESSION_SECRET to the portal's secret
uvicorn app.main:app --port 4000
```

Needs Google Application Default Credentials
(`gcloud auth application-default login`) whose identity can query the engine's
project. Without them the server starts; `/api/chat` returns `502`.

## Layout

| Concern | File |
|---|---|
| Portal-JWT verification | `app/auth.py` |
| `user_id -> session_id` store (SQLite) | `app/store.py` |
| Create-or-resume + ownership | `app/main.py` |
| Agent Engine SDK calls | `app/agent.py` |
| Event -> text extraction | `app/events.py` |

## Tests

```bash
python -m unittest discover -s tests
```
