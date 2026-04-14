"""Supabase clients: anon-only; user JWT via postgrest.auth — never service_role."""

from __future__ import annotations

from typing import Tuple

import streamlit as st
from supabase import Client, create_client


def get_config() -> Tuple[str, str]:
    """Read URL and anon key from Streamlit secrets."""
    try:
        url = st.secrets["SUPABASE_URL"]
        anon = st.secrets["SUPABASE_ANON_KEY"]
    except KeyError as e:
        raise RuntimeError(
            "Missing Streamlit secret. Add SUPABASE_URL and SUPABASE_ANON_KEY "
            "(see .streamlit/secrets.toml.example)."
        ) from e
    if not url or not anon:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be non-empty.")
    return str(url).strip(), str(anon).strip()


def get_anon_client() -> Client:
    """Client for Auth API only (sign-in, sign-up, refresh). Uses anon key."""
    url, anon = get_config()
    return create_client(url, anon)


def get_user_client(access_token: str) -> Client:
    """
    Client for PostgREST (table ops). Anon key + user JWT on PostgREST only.
    """
    url, anon = get_config()
    supabase = create_client(url, anon)
    supabase.postgrest.auth(access_token)
    return supabase
