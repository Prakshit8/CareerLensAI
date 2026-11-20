"""Streamlit dashboard for the CareerLens AI local API."""

import os
from html import escape
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

def _get_api_url() -> str:
    """Resolve the deployed backend URL from Streamlit Secrets or the environment."""
    try:
        secret_url = st.secrets.get("CAREERLENS_API_URL")
    except (FileNotFoundError, KeyError):
        secret_url = None
    return (secret_url or os.getenv("CAREERLENS_API_URL", "http://127.0.0.1:8000")).rstrip("/")


API_URL = _get_api_url()
PAGES = [
    "Dashboard", "AI Job Search", "Recommended Jobs", "My Profile",
    "AI Career Assistant", "Saved Jobs", "Search History",
    "Evaluation Dashboard", "Settings",
]

st.set_page_config(
    page_title="CareerLens AI",
    page_icon="C",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _load_styles() -> None:
    css_path = Path(__file__).parent / "styles" / "app.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def api_request(method: str, path: str, **kwargs: Any) -> Any:
    """Call the backend and surface transport and API errors to the user."""
    timeout = kwargs.pop("timeout", 90.0)
    try:
        response = httpx.request(
            method, f"{API_URL}{path}", timeout=timeout, **kwargs
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        try:
            detail = error.response.json().get("detail", error.response.text)
        except ValueError:
            detail = error.response.text
        raise RuntimeError(f"Request failed ({error.response.status_code}): {detail}") from error
    except (httpx.ConnectError, httpx.TimeoutException) as error:
        raise RuntimeError(
            "The CareerLens backend is not reachable. Configure "
            "`CAREERLENS_API_URL` for your deployed backend."
        ) from error
    if response.status_code == 204:
        return None
    return response.json()


def _notify_api_error(error: Exception) -> None:
    st.error(str(error))


def _render_job_card(
    hit: dict[str, Any], key_prefix: str, *, saved_view: bool = False
) -> None:
    job = hit.get("job", hit)
    job_id = job["id"]
    score = hit.get("score")
    with st.container(border=True):
        heading, score_col = st.columns([5, 1])
        heading.subheader(job["title"])
        if score is not None:
            score_col.metric("Match", f"{float(score) * 100:.0f}%")
        st.caption(" · ".join(filter(None, [job.get("company"), job.get("location")])))
        details = [
            item for item in (job.get("employment_type"), job.get("experience_level"),
                              job.get("role_category")) if item
        ]
        if details:
            st.caption("  |  ".join(details))
        if job.get("skills"):
            skills = job["skills"]
            if isinstance(skills, list):
                st.markdown("**Skills:** " + ", ".join(skills))
        if hit.get("explanation"):
            for explanation in hit["explanation"]:
                st.markdown(f"- {explanation}")
        if job.get("is_synthetic"):
            st.info("Synthetic demo listing — not a real vacancy.")
        if job.get("apply_url"):
            st.link_button("View application", job["apply_url"])
        save_col, like_col, reject_col, apply_col = st.columns(4)
        try:
            if saved_view:
                if save_col.button("Remove", key=f"{key_prefix}-remove-{job_id}"):
                    api_request("DELETE", f"/api/saved/{job_id}")
                    st.rerun()
            elif save_col.button("Save", key=f"{key_prefix}-save-{job_id}"):
                api_request("PUT", f"/api/saved/{job_id}")
                st.toast("Job saved.")
            if like_col.button("Like", key=f"{key_prefix}-like-{job_id}"):
                api_request("POST", "/api/feedback", json={
                    "job_id": job_id, "feedback": "like",
                })
                st.toast("Feedback recorded.")
            if reject_col.button("Not relevant", key=f"{key_prefix}-reject-{job_id}"):
                api_request("POST", "/api/feedback", json={
                    "job_id": job_id, "feedback": "not_relevant",
                })
                st.toast("Feedback recorded.")
            if apply_col.button("Applied", key=f"{key_prefix}-applied-{job_id}"):
                api_request("POST", "/api/feedback", json={
                    "job_id": job_id, "feedback": "applied",
                })
                st.toast("Application feedback recorded.")
        except RuntimeError as error:
            _notify_api_error(error)


def _page_dashboard() -> None:
    try:
        profile = api_request("GET", "/api/profiles/me")
        jobs = api_request("GET", "/api/jobs", params={"limit": 200})
        saved = api_request("GET", "/api/saved")
        history = api_request("GET", "/api/search/history", params={"limit": 5})
    except RuntimeError as error:
        _notify_api_error(error)
        return
    name = escape(profile.get("name") or "there")
    st.markdown(
        f'<div class="hero"><h1>Welcome back, {name}</h1>'
        '<p class="muted">Find work that fits your skills, goals, and preferences.</p></div>',
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    a.metric("Active listings", len(jobs))
    b.metric("Saved jobs", len(saved))
    c.metric("Profile completion", profile["completion_status"])
    d.metric("Recent searches", len(history))
    st.subheader("Your profile at a glance")
    if profile["skills"]:
        st.write("**Skills:** " + ", ".join(profile["skills"]))
    else:
        st.info("Add skills to your profile to unlock personalized recommendations.")
    if profile["preferred_roles"]:
        st.write("**Preferred roles:** " + ", ".join(profile["preferred_roles"]))
    st.subheader("Recent searches")
    if history:
        for item in history:
            st.write(f"• {item['query']} — {item['result_count']} results")
    else:
        st.caption("Your searches will appear here.")
    if profile["completion_status"] != "100%":
        st.progress(int(profile["completion_status"].rstrip("%")), text="Complete your profile")


def _page_search() -> None:
    st.title("AI Job Search")
    st.caption("Compare keyword, semantic, and hybrid retrieval against your job dataset.")
    with st.form("search-form"):
        query = st.text_input(
            "What kind of role are you looking for?",
            placeholder="Entry-level AI internships involving LLMs and Python",
        )
        first, second, third = st.columns(3)
        mode = first.selectbox("Search mode", ["hybrid", "keyword", "semantic"])
        location = second.text_input("Location", placeholder="Remote, Bengaluru, etc.")
        role = third.text_input("Role or category")
        fourth, fifth, sixth = st.columns(3)
        experience = fourth.text_input("Experience level")
        employment = fifth.text_input("Employment type")
        limit = sixth.slider("Results", min_value=5, max_value=30, value=10)
        submitted = st.form_submit_button("Search jobs", type="primary")
    if submitted:
        try:
            with st.spinner("Searching listings..."):
                response = api_request(
                    "POST", "/api/search", timeout=300.0,
                    json={
                        "query": query, "mode": mode, "location": location or None,
                        "role": role or None, "experience_level": experience or None,
                        "employment_type": employment or None, "limit": limit,
                    },
                )
            st.session_state["last_search"] = response
        except RuntimeError as error:
            _notify_api_error(error)
    response = st.session_state.get("last_search")
    if response:
        st.subheader(f"{len(response['results'])} results")
        for warning in response.get("warnings", []):
            st.warning(warning)
        for index, hit in enumerate(response["results"]):
            _render_job_card(hit, f"search-{index}")


def _page_recommendations() -> None:
    st.title("Recommended for You")
    st.caption("Explore a few transparent views of your job data and candidate profile.")
    try:
        response = api_request("GET", "/api/recommendations", params={"limit": 30}, timeout=300)
        recent = api_request("GET", "/api/jobs", params={"limit": 12})
    except RuntimeError as error:
        _notify_api_error(error)
        return
    recommended = response["results"]
    tabs = st.tabs([
        "Recommended for You", "Best Skill Matches", "Similar Jobs",
        "Recently Added", "Explore More",
    ])
    with tabs[0]:
        if not recommended:
            st.info("No recommendations yet. Complete your profile or import active jobs.")
        for index, hit in enumerate(recommended):
            _render_job_card(hit, f"recommend-{index}")
    with tabs[1]:
        skill_matches = sorted(
            recommended,
            key=lambda hit: -float(
                (hit.get("retrieval", {}).get("components") or {}).get("skills") or 0
            ),
        )
        if not skill_matches or not any(
            hit.get("retrieval", {}).get("components", {}).get("skills") is not None
            for hit in skill_matches
        ):
            st.info("Add skills to your profile and ensure jobs include skill details.")
        for index, hit in enumerate(skill_matches):
            _render_job_card(hit, f"skills-{index}")
    with tabs[2]:
        if recommended:
            options = {hit["job"]["id"]: hit["job"]["title"] for hit in recommended}
            selected = st.selectbox(
                "Choose a starting listing", list(options),
                format_func=lambda value: options[value],
            )
            if st.button("Find similar jobs"):
                try:
                    similar = api_request(
                        "GET", f"/api/jobs/{selected}/similar",
                        params={"limit": 10}, timeout=300,
                    )
                    st.session_state["similar_jobs"] = similar
                except RuntimeError as error:
                    _notify_api_error(error)
        similar = st.session_state.get("similar_jobs")
        if similar:
            for index, hit in enumerate(similar["results"]):
                _render_job_card(hit, f"similar-{index}")
        elif not recommended:
            st.info("Generate recommendations to choose a starting listing.")
    with tabs[3]:
        if not recent:
            st.info("No active listings are available.")
        for index, job in enumerate(recent):
            _render_job_card({"job": job}, f"recent-{index}")
    with tabs[4]:
        query = st.text_input("Explore jobs by skills or role")
        mode = st.selectbox("Explore mode", ["hybrid", "keyword", "semantic"], key="explore-mode")
        if st.button("Explore", type="primary"):
            try:
                st.session_state["explore_results"] = api_request(
                    "POST", "/api/search", timeout=300,
                    json={"query": query, "mode": mode, "limit": 15},
                )
            except RuntimeError as error:
                _notify_api_error(error)
        explore = st.session_state.get("explore_results")
        if explore:
            for index, hit in enumerate(explore["results"]):
                _render_job_card(hit, f"explore-{index}")


def _page_profile() -> None:
    st.title("My Profile")
    try:
        profile = api_request("GET", "/api/profiles/me")
    except RuntimeError as error:
        _notify_api_error(error)
        return
    st.caption(f"Profile completion: {profile['completion_status']}")
    with st.form("profile-form"):
        name = st.text_input("Name", value=profile.get("name") or "")
        email = st.text_input("Email", value=profile.get("email") or "")
        skills = st.text_input("Skills (comma separated)", value=", ".join(profile["skills"]))
        experience = st.text_input("Experience level", value=profile.get("experience_level") or "")
        education = st.text_area("Education", value=profile.get("education") or "")
        roles = st.text_input(
            "Preferred roles (comma separated)", value=", ".join(profile["preferred_roles"])
        )
        locations = st.text_input(
            "Preferred locations (comma separated)", value=", ".join(profile["preferred_locations"])
        )
        employment = st.text_input(
            "Preferred employment types (comma separated)",
            value=", ".join(profile["preferred_employment_types"]),
        )
        interests = st.text_area(
            "Career interests", value=profile.get("career_interests") or ""
        )
        salary_min = st.number_input(
            "Minimum salary expectation", min_value=0.0, value=float(profile.get("salary_min") or 0)
        )
        salary_max = st.number_input(
            "Maximum salary expectation", min_value=0.0, value=float(profile.get("salary_max") or 0)
        )
        save = st.form_submit_button("Save profile", type="primary")
    if save:
        payload = {
            "name": name or None, "email": email or None,
            "skills": [item.strip() for item in skills.split(",") if item.strip()],
            "experience_level": experience or None, "education": education or None,
            "preferred_roles": [item.strip() for item in roles.split(",") if item.strip()],
            "preferred_locations": [item.strip() for item in locations.split(",") if item.strip()],
            "preferred_employment_types": [
                item.strip() for item in employment.split(",") if item.strip()
            ],
            "career_interests": interests or None,
            "salary_min": salary_min or None, "salary_max": salary_max or None,
        }
        try:
            api_request("PATCH", "/api/profiles/me", json=payload)
            st.success("Profile saved.")
            st.rerun()
        except RuntimeError as error:
            _notify_api_error(error)
    st.subheader("Resume")
    resume = st.file_uploader("Upload a selectable-text PDF (max 5 MB)", type=["pdf"])
    if resume and st.button("Extract resume text and skills"):
        try:
            result = api_request(
                "POST", "/api/profiles/me/resume",
                files={"file": (resume.name, resume.getvalue(), "application/pdf")},
            )
            st.success("Resume text extracted. Review and edit the detected skills above.")
            st.write("**Detected skills:** " + ", ".join(result["skills"]))
        except RuntimeError as error:
            _notify_api_error(error)


def _page_assistant() -> None:
    st.title("AI Career Assistant")
    st.caption("Search naturally, update preferences, and continue conversations across visits.")
    try:
        conversations = api_request("GET", "/api/assistant/conversations")
    except RuntimeError as error:
        _notify_api_error(error)
        return
    if conversations:
        options = {item["id"]: item["title"] for item in conversations}
        current = st.session_state.get("conversation_id")
        selected = st.selectbox(
            "Conversation",
            list(options),
            format_func=lambda value: options[value],
            index=list(options).index(current) if current in options else 0,
        )
        st.session_state["conversation_id"] = selected
    else:
        st.session_state.pop("conversation_id", None)
    conversation_id = st.session_state.get("conversation_id")
    if conversation_id:
        try:
            messages = api_request(
                "GET", f"/api/assistant/conversations/{conversation_id}/messages"
            )
            for item in messages:
                if item["role"] in {"user", "assistant"}:
                    with st.chat_message(item["role"]):
                        st.markdown(item["content"])
        except RuntimeError as error:
            _notify_api_error(error)
    prompt = st.chat_input("Ask about jobs, skills, or preferences")
    if prompt:
        try:
            with st.spinner("Working on your request..."):
                response = api_request(
                    "POST", "/api/assistant/chat", timeout=300.0,
                    json={"message": prompt, "conversation_id": conversation_id},
                )
            st.session_state["conversation_id"] = response["conversation_id"]
            if response["tool_calls"]:
                st.caption("The assistant searched listings and applied available preferences.")
            st.rerun()
        except RuntimeError as error:
            _notify_api_error(error)
def _page_saved() -> None:
    st.title("Saved Jobs")
    try:
        jobs = api_request("GET", "/api/saved")
    except RuntimeError as error:
        _notify_api_error(error)
        return
    if not jobs:
        st.info("Saved listings will appear here.")
    for index, job in enumerate(jobs):
        _render_job_card({"job": job}, f"saved-{index}", saved_view=True)


def _page_history() -> None:
    st.title("Search History")
    try:
        history = api_request("GET", "/api/search/history", params={"limit": 100})
    except RuntimeError as error:
        _notify_api_error(error)
        return
    if not history:
        st.info("Searches you run will be stored here.")
    for item in history:
        with st.container(border=True):
            st.markdown(f"**{item['query']}**")
            st.caption(
                f"{item['mode']} · {item['result_count']} results · "
                f"{item['latency_ms']:.0f} ms · {item['created_at']}"
            )


def _page_evaluation() -> None:
    st.title("Evaluation Dashboard")
    st.caption("Offline benchmark results are generated from the labeled synthetic dataset.")
    try:
        runs = api_request("GET", "/api/evaluation/runs")
    except RuntimeError as error:
        _notify_api_error(error)
        return
    if not runs:
        st.info("No evaluation runs yet. Run `python -m scripts.evaluate_search` from the project root.")
        return
    latest = runs[0]
    report = latest["metrics"]
    st.caption(f"{latest['dataset_name']} · {latest['created_at']}")
    st.caption(report.get("label_method", ""))
    summary = report.get("summary", {})
    rows = []
    for mode, data in summary.items():
        metrics = data.get("metrics", {})
        latency = data.get("latency_ms", {})
        rows.append({
            "Retrieval mode": mode,
            "Queries": f"{data.get('queries_succeeded', 0)}/{data.get('queries_total', 0)}",
            "Recall@5": metrics.get("recall@5"),
            "nDCG@5": metrics.get("ndcg@5"),
            "MRR": metrics.get("mrr"),
            "p50 latency (ms)": latency.get("p50"),
            "p95 latency (ms)": latency.get("p95"),
            "Error rate": data.get("error_rate"),
        })
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    agent = report.get("agent_metrics", {})
    if agent:
        st.subheader("Assistant workflow metrics")
        st.write({
            "Tool selection accuracy": agent.get("tool_selection_accuracy"),
            "Tool execution success rate": agent.get("tool_execution_success_rate"),
            "Task completion rate": agent.get("task_completion_rate"),
            "Preference retention accuracy": agent.get("preference_retention_accuracy"),
            "Recorded tool calls": agent.get("tool_execution_count", 0),
        })
        if agent.get("note"):
            st.caption(agent["note"])
    for mode, data in summary.items():
        if data.get("warnings") or data.get("errors"):
            with st.expander(f"{mode}: warnings and errors"):
                for message in data.get("warnings", []) + data.get("errors", []):
                    st.write(f"- {message}")


def _page_settings() -> None:
    st.title("Settings & Memory")
    try:
        health = api_request("GET", "/health")
        memories = api_request("GET", "/api/memories")
    except RuntimeError as error:
        _notify_api_error(error)
        return
    st.success("Backend is connected." if health["status"] == "ok" else "Backend is unavailable.")
    st.caption(
        "Career assistant uses local search when an external language-model key is not configured."
    )
    st.subheader("Stored preferences and memories")
    if not memories:
        st.caption("No explicit preferences stored yet.")
    for memory in memories:
        left, right = st.columns([5, 1])
        left.write(f"**{memory['key']}**: {memory['value']}")
        left.caption(f"{memory['kind']} · {'explicit' if memory['is_explicit'] else 'inferred'}")
        if right.button("Delete", key=f"delete-memory-{memory['id']}"):
            try:
                api_request("DELETE", f"/api/memories/{memory['id']}")
                st.rerun()
            except RuntimeError as error:
                _notify_api_error(error)


def main() -> None:
    _load_styles()
    with st.sidebar:
        st.markdown("# CareerLens")
        st.caption("AI-powered job discovery")
        page = st.radio("Navigate", PAGES, label_visibility="collapsed")
        st.divider()
        st.caption("Your profile, searches, and preferences are stored locally.")
    renderers = {
        "Dashboard": _page_dashboard,
        "AI Job Search": _page_search,
        "Recommended Jobs": _page_recommendations,
        "My Profile": _page_profile,
        "AI Career Assistant": _page_assistant,
        "Saved Jobs": _page_saved,
        "Search History": _page_history,
        "Evaluation Dashboard": _page_evaluation,
        "Settings": _page_settings,
    }
    renderers[page]()


if __name__ == "__main__":
    main()
