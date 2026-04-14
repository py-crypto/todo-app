"""Todos CRUD via user-scoped PostgREST client with refresh on auth errors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, List, TypeVar

import streamlit as st
from gotrue.errors import AuthApiError
from postgrest.exceptions import APIError

from src.supabase_client import get_anon_client, get_user_client

T = TypeVar("T")


def _is_auth_error(exc: APIError) -> bool:
    code = str(exc.code) if exc.code is not None else ""
    if code in ("401", "PGRST301", "PGRST302"):
        return True
    msg = (exc.message or "") + (exc.details or "")
    if "JWT" in msg or "jwt" in msg.lower() or "expired" in msg.lower():
        return True
    return False


def _refresh_session() -> bool:
    """Return True if tokens updated; False if refresh failed (caller should clear session)."""
    rt = st.session_state.get("refresh_token")
    if not rt:
        return False
    try:
        client = get_anon_client()
        res = client.auth.refresh_session(rt)
        if res.session is None:
            return False
        st.session_state["access_token"] = res.session.access_token
        st.session_state["refresh_token"] = res.session.refresh_token
        st.session_state["user"] = res.session.user
        return True
    except (AuthApiError, Exception):
        return False


def _force_login() -> None:
    from src.auth_ui import clear_session

    clear_session()
    st.session_state["auth_expired"] = True
    st.rerun()


def with_auth_recovery(fn: Callable[[], T]) -> T:
    """Run fn; on auth-related APIError refresh once and retry; else clear session."""
    try:
        return fn()
    except APIError as e:
        if not _is_auth_error(e):
            raise
        if _refresh_session():
            try:
                return fn()
            except APIError as e2:
                if _is_auth_error(e2):
                    _force_login()
                raise
        else:
            _force_login()


def fetch_todos(access_token: str) -> List[dict[str, Any]]:
    def _() -> List[dict[str, Any]]:
        sb = get_user_client(access_token)
        r = (
            sb.table("todos")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return list(r.data or [])

    return with_auth_recovery(_)


def create_todo(access_token: str, user_id: str, title: str) -> None:
    title = title.strip()
    if not title:
        return

    def _() -> None:
        sb = get_user_client(access_token)
        sb.table("todos").insert(
            {"title": title, "user_id": user_id, "is_done": False}
        ).execute()

    with_auth_recovery(_)


def toggle_todo(access_token: str, todo_id: str, is_done: bool) -> None:
    """Set is_done and completed_at."""

    def _() -> None:
        sb = get_user_client(access_token)
        completed_at = (
            datetime.now(timezone.utc).isoformat() if is_done else None
        )
        sb.table("todos").update(
            {"is_done": is_done, "completed_at": completed_at}
        ).eq("id", todo_id).execute()

    with_auth_recovery(_)


def delete_todo(access_token: str, todo_id: str) -> None:

    def _() -> None:
        sb = get_user_client(access_token)
        sb.table("todos").delete().eq("id", todo_id).execute()

    with_auth_recovery(_)
