import streamlit as st

from pages.home import render_home
from pages.project import render_project
from utils.storage import (
    collect_snapshot_state,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)


st.set_page_config(
    page_title="Infrastructure Decision Support",
    page_icon="",
    layout="wide",
)


def initialise_state() -> None:
    """Create session state containers used across pages."""
    st.session_state.setdefault("projects", {})
    st.session_state.setdefault("active_project", None)


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1440px;
        }
        [data-testid="stSidebarNav"] {
            display: none;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: #171d28;
            border: 1px solid #2b3445;
            border-radius: 8px;
            padding: 14px 16px;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background: #171d28;
            border-radius: 8px 8px 0 0;
            padding: 10px 16px;
        }
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_project_storage_controls() -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Save / Load")

    active_project = st.session_state.get("active_project")
    default_name = "Untitled project"
    if active_project and active_project in st.session_state.projects:
        default_name = st.session_state.projects[active_project]["name"]

    snapshot_name = st.sidebar.text_input("Snapshot name", value=default_name)
    if st.sidebar.button("Save current work"):
        save_snapshot(snapshot_name.strip() or default_name, collect_snapshot_state(st.session_state))
        st.sidebar.success("Saved.")

    snapshots = list_snapshots()
    if snapshots:
        labels = {
            f"{item['name']} - {item['saved_at']}": item["id"]
            for item in snapshots
        }
        selected = st.sidebar.selectbox("Load saved work", options=list(labels.keys()))
        if st.sidebar.button("Load selected snapshot"):
            loaded = load_snapshot(labels[selected])
            for key, value in loaded.items():
                st.session_state[key] = value
            st.sidebar.success("Loaded. The page will refresh on the next interaction.")
    else:
        st.sidebar.caption("No saved snapshots yet.")


def main() -> None:
    initialise_state()
    apply_styles()

    st.sidebar.title("Decision Support")
    page = st.sidebar.radio("Go to", ["Home", "Project"], label_visibility="collapsed")
    render_project_storage_controls()

    if page == "Home":
        render_home()
    else:
        render_project()


if __name__ == "__main__":
    main()
