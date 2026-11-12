"""
In-process bridge between the Django web app and the Mera Hisaab ADK agent.

The agent package (``mh_agent``) lives in the sibling ``mera_hisaab_agent/``
folder with its own venv for *standalone* runs. When embedded here, we import it
into the running web process and drive it with a single long-lived ADK Runner.

Key guarantees:
- **Multi-tenant**: every call is wrapped in ``tenant_scope(business_id, user_id)``
  so all 19 tools resolve to the *logged-in shopkeeper's* business and act as
  that real user — never a hardcoded tenant.
- **Multi-turn**: one in-memory ADK session per (business, user) keeps short
  conversation history alive for the lifetime of the web worker process.
- **Lazy**: the agent + Gemini client are built on first use, so importing this
  module (and running the rest of the app) stays cheap and never fails if the
  agent is misconfigured — the error surfaces only when the assistant is used.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

# ADK tools call the Django ORM synchronously from inside async tool functions;
# allow that (we run one blocking agent turn per request, which is acceptable).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# Make the sibling agent package importable: mh_agent lives inside
# <project_root>/mera_hisaab_agent/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AGENT_ROOT = _PROJECT_ROOT / "mera_hisaab_agent"
if _AGENT_ROOT.is_dir() and str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

_APP_NAME = "mera_hisaab_agent"

# Lazily-built singletons, guarded by a lock (gunicorn workers are single-process
# but may serve concurrent async work).
_lock = threading.Lock()
_runner = None
_session_service = None


class AgentUnavailable(RuntimeError):
    """Raised when the agent cannot be initialised (missing key, import error)."""


def _build_runner():
    """Build the ADK Runner + session service once per process."""
    global _runner, _session_service
    if _runner is not None:
        return _runner

    with _lock:
        if _runner is not None:
            return _runner
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from mh_agent.agent import root_agent
        except Exception as exc:  # pragma: no cover - env/config failure
            raise AgentUnavailable(
                f"Mera Hisaab AI agent could not be loaded: {exc}"
            ) from exc

        _session_service = InMemorySessionService()
        _runner = Runner(
            app_name=_APP_NAME,
            agent=root_agent,
            session_service=_session_service,
            auto_create_session=True,
        )
    return _runner


# A single long-lived event loop on a daemon thread. Running the async ADK agent
# here (instead of a fresh loop per call) keeps the Gemini async HTTP client alive
# and reusable across turns, and avoids "Event loop is closed" teardown noise.
_loop = None
_loop_lock = threading.Lock()


def _get_loop():
    global _loop
    if _loop is not None:
        return _loop
    with _loop_lock:
        if _loop is not None:
            return _loop
        loop = asyncio.new_event_loop()
        t = threading.Thread(
            target=loop.run_forever, name="mh-agent-loop", daemon=True
        )
        t.start()
        _loop = loop
    return _loop


def _session_id(business_id: int, user_id: int) -> str:
    """One persistent conversation per (business, user) within this process."""
    return f"b{int(business_id)}-u{int(user_id)}"


async def _arun(business_id: int, user_id: int, message: str, session_id: str) -> str:
    from google.genai import types

    from mh_agent.context import tenant_scope

    runner = _build_runner()
    adk_user_id = f"u{int(user_id)}"
    content = types.Content(role="user", parts=[types.Part(text=message)])

    # Scope the WHOLE run (incl. every awaited tool call) to this tenant + actor.
    with tenant_scope(business_id, user_id):
        # Ensure the session exists so history accrues across turns.
        existing = await _session_service.get_session(
            app_name=_APP_NAME, user_id=adk_user_id, session_id=session_id
        )
        if existing is None:
            await _session_service.create_session(
                app_name=_APP_NAME, user_id=adk_user_id, session_id=session_id
            )

        final_text_parts: list[str] = []
        async for event in runner.run_async(
            user_id=adk_user_id, session_id=session_id, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        final_text_parts.append(part.text)

    reply = "".join(final_text_parts).strip()
    return reply or "Maaf kijiye, main abhi jawab nahi de paaya. Dobara poochhein."


def ask_agent(business_id: int, user_id: int, message: str) -> str:
    """Synchronous entry point for Django views.

    Runs one agent turn for the given tenant/actor and returns the reply text.
    Raises ``AgentUnavailable`` if the agent cannot run at all.
    """
    message = (message or "").strip()
    if not message:
        return "Kuch to poochhiye — main aapki dukaan ke hisaab-kitaab mein madad kar sakta hoon."

    session_id = _session_id(business_id, user_id)
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(
        _arun(business_id, user_id, message, session_id), loop
    )
    try:
        # Bound how long a single turn may block a web worker.
        return future.result(timeout=120)
    except FuturesTimeout as exc:
        future.cancel()
        raise AgentUnavailable("AI Sahayak ne jawab dene mein bahut der laga di.") from exc
    except Exception as exc:
        # Transient upstream problems (Gemini overload/5xx, network) should read as
        # "try again", not a hard crash. Detect them loosely by status/name so we
        # don't couple this module to the genai error classes.
        text = f"{type(exc).__name__}: {exc}".lower()
        if any(s in text for s in ("503", "unavailable", "overloaded", "429",
                                   "resource_exhausted", "deadline", "timeout")):
            raise AgentUnavailable(str(exc)) from exc
        raise
