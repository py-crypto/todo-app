"""Login via Google OAuth; session is source of truth."""

from __future__ import annotations

import streamlit as st

from src.supabase_client import get_anon_client, get_config


def clear_session() -> None:
    """Remove all auth and app state (logout or failed refresh)."""
    from src.realtime_todos import stop_realtime

    stop_realtime()
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def render_auth_page() -> None:
    """Unauthenticated: Google OAuth login only."""
    if st.session_state.pop("auth_expired", None):
        st.warning("Session expired, please login again.")

    st.title("Todo")
    
    # Handle OAuth callback
    if "code" in st.query_params:
        try:
            client = get_anon_client()
            # Exchange authorization code for session
            res = client.auth.exchange_code_for_session(st.query_params["code"])
            if res.session is None:
                st.error("Failed to create session from OAuth callback.")
                return
            st.session_state["access_token"] = res.session.access_token
            st.session_state["refresh_token"] = res.session.refresh_token
            st.session_state["user"] = res.session.user
            # Clear query params and rerun
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"OAuth authentication failed: {e}")
            return
    
    # Google OAuth login button
    st.write("Sign in with your Google account:")
    if st.button("🔐 Continue with Google", key="google_login_btn", use_container_width=True):
        try:
            client = get_anon_client()
            url, _ = get_config()
            # Get authorization URL for Google OAuth
            res = client.auth.sign_in_with_oauth(
                {
                    "provider": "google",
                    "options": {
                        "redirect_to": st.query_params.get("redirect_to", f"{url}/auth/v1/callback")
                    },
                }
            )
            if res.url:
                st.markdown(f"[Click here to continue with Google]({res.url})")
            else:
                st.error("Failed to generate Google login URL.")
        except Exception as e:
            st.error(f"Could not initiate Google login: {e}")
