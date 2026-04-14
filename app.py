"""
Streamlit Todo app — Supabase Auth + PostgREST + Realtime (postgres_changes).
"""

from __future__ import annotations

import queue
from typing import Any

import streamlit as st

from src.auth_ui import clear_session, render_auth_page
from src.realtime_todos import apply_realtime_to_todos, start_realtime
from src.supabase_client import get_config
from src.todos_repo import (
    create_todo,
    delete_todo,
    fetch_todos,
    toggle_todo,
)
from src.ui import top_bar


def _user_id(user: Any) -> str | None:
    if user is None:
        return None
    uid = getattr(user, "id", None)
    if uid is not None:
        return str(uid)
    if isinstance(user, dict):
        u = user.get("id")
        return str(u) if u is not None else None
    return None


def _user_email(user: Any) -> str:
    e = getattr(user, "email", None)
    if e:
        return str(e)
    if isinstance(user, dict) and user.get("email"):
        return str(user["email"])
    return ""


def _drain_realtime_queue() -> bool:
    """Apply queued Realtime events to session_state['todos']. Returns True if UI should refresh."""
    q = st.session_state.get("_realtime_queue")
    if not q:
        return False
    changed = False
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        if item.get("type") == "dirty":
            st.session_state["_todos_dirty"] = True
            changed = True
        else:
            todos = st.session_state.get("todos") or []
            st.session_state["todos"] = apply_realtime_to_todos(item, todos)
            changed = True
    return changed


def _refetch_if_dirty(access_token: str) -> bool:
    if not st.session_state.pop("_todos_dirty", False):
        return False
    try:
        st.session_state["todos"] = fetch_todos(access_token)
    except Exception as e:
        st.error(f"Could not reload todos. Check your connection and retry. ({e})")
        st.session_state["_todos_dirty"] = True
    return True


def main() -> None:
    st.set_page_config(page_title="Todo", page_icon="✓", layout="wide")

    try:
        get_config()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    if "access_token" not in st.session_state:
        render_auth_page()
        return

    access_token = st.session_state["access_token"]
    user = st.session_state["user"]
    user_id = _user_id(user)
    email = _user_email(user)

    if not user_id:
        st.error("Invalid session: missing user id.")
        clear_session()
        st.stop()

    if _drain_realtime_queue():
        st.rerun()

    if _refetch_if_dirty(access_token):
        st.rerun()

    if "todos" not in st.session_state:
        try:
            st.session_state["todos"] = fetch_todos(access_token)
        except Exception as e:
            err = str(e).lower()
            if "connection" in err or "timeout" in err or "network" in err:
                st.error("Network error — please check your connection and try again.")
            else:
                st.error(f"Could not load todos: {e}")
            if st.button("Retry"):
                st.rerun()
            st.stop()

    if "realtime_started" not in st.session_state:
        st.session_state["_realtime_queue"] = queue.Queue()
        url, anon = get_config()
        start_realtime(
            url,
            anon,
            access_token,
            str(user_id),
            st.session_state["_realtime_queue"],
        )
        st.session_state["realtime_started"] = True

    top_bar("Todo", email)

    new_title = st.text_input("New task", key="new_todo", placeholder="Add a todo…")
    if st.button("Add", type="primary"):
        if new_title and new_title.strip():
            try:
                create_todo(access_token, str(user_id), new_title.strip())
                st.session_state["todos"] = fetch_todos(access_token)
                st.rerun()
            except Exception as e:
                err = str(e).lower()
                if "connection" in err or "timeout" in err:
                    st.error("Network error — try again.")
                else:
                    st.error(str(e))

    todos = st.session_state.get("todos") or []
    if not todos:
        st.info("No todos yet.")
    else:
        for t in todos:
            tid = t.get("id")
            title = t.get("title", "")
            done = bool(t.get("is_done"))
            c1, c2, c3 = st.columns([1, 6, 1])
            with c1:
                checked = st.checkbox(
                    "done",
                    value=done,
                    key=f"chk_{tid}",
                    label_visibility="collapsed",
                )
                if checked != done:
                    try:
                        toggle_todo(access_token, str(tid), checked)
                        st.session_state["todos"] = fetch_todos(access_token)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c2:
                st.markdown(
                    f"~~{title}~~" if done else title,
                )
            with c3:
                if st.button("Delete", key=f"del_{tid}"):
                    try:
                        delete_todo(access_token, str(tid))
                        st.session_state["todos"] = fetch_todos(access_token)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


main()
