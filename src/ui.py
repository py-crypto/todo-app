"""Small UI helpers."""

from __future__ import annotations

import streamlit as st


def top_bar(app_name: str, email: str, on_logout: str = "logout_btn") -> None:
    c1, c2, c3 = st.columns([2, 3, 1])
    with c1:
        st.markdown(f"### {app_name}")
    with c2:
        st.caption(email or "")
    with c3:
        if st.button("Log out", key=on_logout):
            from src.auth_ui import clear_session

            clear_session()
            st.rerun()
