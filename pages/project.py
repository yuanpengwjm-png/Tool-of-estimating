import streamlit as st

from modules.additional import render_additional
from modules.cost import render_cost
from modules.final_decision import render_final_decision
from modules.non_monetary import render_non_monetary


def _initialise_page_state() -> None:
    st.session_state.setdefault("projects", {})
    st.session_state.setdefault("active_project", None)


def render_project() -> None:
    _initialise_page_state()
    if not st.session_state.projects:
        st.warning("Create a project on the Home page before starting analysis.")
        st.info(
            "Use the Home page to create or load a project. Once a project exists, this "
            "page will show the Cost, Non-monetary, Additional, and Decision Summary tabs."
        )
        return

    project_options = {
        project["name"]: project_id
        for project_id, project in st.session_state.projects.items()
    }
    active_name = st.selectbox(
        "Active project",
        options=list(project_options.keys()),
        index=0,
    )
    st.session_state.active_project = project_options[active_name]
    project = st.session_state.projects[st.session_state.active_project]

    st.title(project["name"])
    if project["description"]:
        st.caption(project["description"])

    cost_tab, non_monetary_tab, additional_tab, final_tab = st.tabs(
        ["Cost", "Non-monetary", "Additional", "Decision Summary"]
    )

    with cost_tab:
        render_cost()
    with non_monetary_tab:
        render_non_monetary()
    with additional_tab:
        render_additional()
    with final_tab:
        render_final_decision()


if __name__ == "__main__":
    st.set_page_config(page_title="Project", layout="wide")
    render_project()
