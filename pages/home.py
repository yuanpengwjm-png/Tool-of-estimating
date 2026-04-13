from datetime import date

import streamlit as st


def _initialise_page_state() -> None:
    st.session_state.setdefault("projects", {})
    st.session_state.setdefault("active_project", None)


def render_home() -> None:
    _initialise_page_state()
    st.title("Public Infrastructure Decision Support")
    st.write(
        "Create a project, then evaluate cost, non-monetary, and additional decision factors."
    )

    with st.form("create_project_form"):
        st.subheader("Create Project")
        name = st.text_input("Project name", placeholder="Example: Road material evaluation")
        description = st.text_area(
            "Project description",
            placeholder="Briefly describe the infrastructure option or decision context.",
        )
        created_on = st.date_input("Created on", value=date.today())
        submitted = st.form_submit_button("Create project")

    if submitted:
        if not name.strip():
            st.error("Please enter a project name.")
            return

        project_id = name.strip().lower().replace(" ", "-")
        st.session_state.projects[project_id] = {
            "name": name.strip(),
            "description": description.strip(),
            "created_on": str(created_on),
        }
        st.session_state.active_project = project_id
        st.success(f"Project created: {name.strip()}")
        st.info("Open the Project page from the sidebar to continue.")

    if st.session_state.projects:
        st.subheader("Existing Projects")
        project_rows = [
            {
                "Project": project["name"],
                "Created": project["created_on"],
                "Description": project["description"],
            }
            for project in st.session_state.projects.values()
        ]
        st.dataframe(project_rows, use_container_width=True)


if __name__ == "__main__":
    st.set_page_config(page_title="Home", layout="wide")
    render_home()
