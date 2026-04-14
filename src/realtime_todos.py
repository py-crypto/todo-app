"""
Supabase Realtime (postgres_changes) via WebSocket — supabase-py 2.4.0 has no wired client.

Events are pushed to a queue; the main script drains the queue and updates session_state.
Never call st.rerun from this module's background thread.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import urllib.parse
from typing import Any

import streamlit as st
import websockets

logger = logging.getLogger(__name__)


def _ws_url(supabase_url: str, anon_key: str) -> str:
    parsed = urllib.parse.urlparse(supabase_url)
    host = parsed.netloc
    scheme = "wss" if parsed.scheme == "https" else "ws"
    q = urllib.parse.urlencode({"apikey": anon_key, "vsn": "1.0.0"})
    return f"{scheme}://{host}/realtime/v1/websocket?{q}"


def _run_async_loop(
    ws_url: str,
    access_token: str,
    user_id: str,
    event_queue: "queue.Queue[dict[str, Any]]",
    stop_event: threading.Event,
) -> None:
    async def heartbeat(ws: Any) -> None:
        while not stop_event.is_set():
            await asyncio.sleep(20)
            if stop_event.is_set():
                break
            msg = {
                "topic": "phoenix",
                "event": "heartbeat",
                "payload": {"msg": "ping"},
                "ref": None,
            }
            try:
                await ws.send(json.dumps(msg))
            except Exception:
                break

    async def main() -> None:
        topic = "realtime:public:todos"
        join_payload = {
            "config": {
                "postgres_changes": [
                    {
                        "event": "*",
                        "schema": "public",
                        "table": "todos",
                        "filter": f"user_id=eq.{user_id}",
                    }
                ]
            },
            "access_token": access_token,
        }
        join_msg = {
            "topic": topic,
            "event": "phx_join",
            "payload": join_payload,
            "ref": "1",
            "join_ref": "1",
        }
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                await ws.send(json.dumps(join_msg))
                hb = asyncio.create_task(heartbeat(ws))
                try:
                    async for raw in ws:
                        if stop_event.is_set():
                            break
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        try:
                            _dispatch_realtime_message(
                                raw, event_queue, stop_event
                            )
                        except Exception as e:
                            logger.exception("realtime dispatch: %s", e)
                            event_queue.put({"type": "dirty"})
                finally:
                    hb.cancel()
                    try:
                        await hb
                    except asyncio.CancelledError:
                        pass
        except Exception as e:
            logger.exception("realtime connection: %s", e)
            event_queue.put({"type": "dirty"})

    asyncio.run(main())


def _dispatch_realtime_message(
    raw: str,
    event_queue: "queue.Queue[dict[str, Any]]",
    stop_event: threading.Event,
) -> None:
    if stop_event.is_set():
        return
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return

    if isinstance(msg, dict):
        event = msg.get("event")
        payload = msg.get("payload")
        if event == "postgres_changes" and isinstance(payload, dict):
            data = payload.get("data")
            if data is None and "type" in payload and (
                "record" in payload or "old_record" in payload
            ):
                data = payload
            if isinstance(data, dict):
                event_queue.put({"type": "postgres_changes", "data": data})
                return
        if event == "phx_reply" and isinstance(payload, dict):
            status = payload.get("status")
            if status and status != "ok":
                event_queue.put({"type": "dirty"})
        return

    if isinstance(msg, list) and len(msg) >= 5:
        event_name = msg[3]
        body = msg[4] if len(msg) > 4 else None
        if event_name == "postgres_changes" and isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                event_queue.put({"type": "postgres_changes", "data": data})


def stop_realtime() -> None:
    """Stop background Realtime worker for this Streamlit session."""
    stop = st.session_state.get("_realtime_stop")
    if stop is not None:
        stop.set()
    t = st.session_state.get("_realtime_thread")
    if t is not None and t.is_alive():
        t.join(timeout=3.0)


def start_realtime(
    supabase_url: str,
    anon_key: str,
    access_token: str,
    user_id: str,
    event_queue: "queue.Queue[dict[str, Any]]",
) -> None:
    """Start a single worker thread; store handles on session_state."""
    stop_realtime()
    st.session_state.pop("_realtime_stop", None)
    st.session_state.pop("_realtime_thread", None)

    stop = threading.Event()
    url = _ws_url(supabase_url, anon_key)

    def worker() -> None:
        try:
            _run_async_loop(url, access_token, user_id, event_queue, stop)
        except Exception as e:
            logger.exception("realtime worker: %s", e)
            event_queue.put({"type": "dirty"})

    t = threading.Thread(target=worker, name="supabase-realtime", daemon=True)
    st.session_state["_realtime_stop"] = stop
    st.session_state["_realtime_thread"] = t
    t.start()


def apply_realtime_to_todos(
    item: dict[str, Any], todos: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge one Realtime event into todos list (by id)."""
    if item.get("type") == "dirty":
        return todos
    if item.get("type") != "postgres_changes":
        return todos
    data = item.get("data") or {}
    change = data.get("type")
    record = data.get("record") or {}
    old_record = data.get("old_record") or {}
    tid = record.get("id") or old_record.get("id")
    if not tid:
        return todos
    out = [r for r in todos if r.get("id") != tid]
    if change == "DELETE":
        return out
    if change in ("INSERT", "UPDATE") and record:
        out.append(record)
        out.sort(
            key=lambda r: str(r.get("created_at") or ""),
            reverse=True,
        )
    return out
