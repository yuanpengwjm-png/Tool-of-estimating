import pickle
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DB_PATH = Path("app_data") / "decision_support.sqlite3"

STATE_KEYS = [
    "projects",
    "active_project",
    "monetary_schemes",
    "monetary_factors",
    "monetary_factor_values",
    "monetary_components",
    "monetary_constraints",
    "monetary_scores",
    "monetary_component_results",
    "monetary_totals",
    "monetary_constraint_report",
    "non_monetary_importance_weights",
    "non_monetary_importance_method",
    "non_monetary_performance_profile",
    "non_monetary_scores",
    "non_monetary_contributions",
    "additional_review_items",
    "additional_warning_summary",
    "decision_summary",
]


def initialise_database() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                payload BLOB NOT NULL
            )
            """
        )


def save_snapshot(name: str, state: dict[str, Any]) -> None:
    initialise_database()
    payload = pickle.dumps(state)
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO project_snapshots (name, saved_at, payload) VALUES (?, ?, ?)",
            (name, saved_at, payload),
        )


def list_snapshots() -> list[dict[str, Any]]:
    initialise_database()
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT id, name, saved_at
            FROM project_snapshots
            ORDER BY id DESC
            """
        ).fetchall()
    return [{"id": row[0], "name": row[1], "saved_at": row[2]} for row in rows]


def load_snapshot(snapshot_id: int) -> dict[str, Any]:
    initialise_database()
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT payload FROM project_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Snapshot {snapshot_id} was not found.")
    return pickle.loads(row[0])


def collect_snapshot_state(session_state: Any) -> dict[str, Any]:
    return {key: session_state[key] for key in STATE_KEYS if key in session_state}
