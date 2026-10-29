"""Optional Streamlit UI for TriageBot.

Unlike LegalBot, this UI does NOT import the agents. It is a thin client that
calls the FastAPI backend over HTTP. That is why docker compose can run it as a
separate container: it only needs to know API_URL (e.g. http://api:8000).
"""

import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")

EXAMPLE = (
    "The Android app crashes as soon as I try to upload my profile photo. The photo is about 8 MB "
    "from my phone camera. App version 2.3.1 on a Samsung A52."
)

st.set_page_config(page_title="TriageBot", page_icon="🐞")
st.title("🐞 TriageBot")
st.caption("Issue Analyst → Duplicate Investigator (tools) → Triage Lead")

# Sidebar: backend health
with st.sidebar:
    st.subheader("Backend")
    st.code(API_URL)
    try:
        health = httpx.get(f"{API_URL}/health", timeout=5).json()
        if health["llm_configured"]:
            st.success(f"Ready: {health['model']}")
        else:
            st.warning("Backend up, but no API key is set.")
        st.write("Agents:", ", ".join(health["agents"]))
        st.write("Known issues in tracker:", health["known_issues"])
    except httpx.HTTPError:
        st.error("Backend not reachable.")

issue = st.text_area("Bug report", value=EXAMPLE, height=150, max_chars=4000)

if st.button("Triage this bug", type="primary"):
    with st.spinner("Three agents are working (this can take 20-60 seconds)..."):
        try:
            res = httpx.post(f"{API_URL}/triage", json={"issue": issue}, timeout=120)
        except httpx.HTTPError as exc:
            st.error(f"Could not reach the backend: {exc}")
            st.stop()

    if res.status_code != 200:
        detail = res.json().get("detail")
        if isinstance(detail, list):  # 422 validation errors come as a list
            detail = "; ".join(d["msg"] for d in detail)
        st.error(f"{res.status_code}: {detail}")
    else:
        data = res.json()
        col1, col2, col3 = st.columns(3)
        col1.metric("Severity", data["severity"] or "?")
        col2.metric("Priority", data["priority"] or "?")
        col3.metric("Team", data["team"] or "?")
        st.write("**Related past issues:**", ", ".join(data["related_issues"]) or "none")
        st.write("**Tools called:**", ", ".join(data["tools_used"]) or "none")
        st.divider()
        st.markdown(data["report"])
