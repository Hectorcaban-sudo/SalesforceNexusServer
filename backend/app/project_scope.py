"""Project scoping helpers for list endpoints."""
from typing import Any, Iterable, List, Optional


def filter_by_project(
    rows: Iterable[dict],
    project_id: Optional[str] = None,
    *,
    include_global: bool = False,
) -> List[dict]:
    """
    Filter records by project.

    - project_id is None/empty: return all rows (admin / unscoped list)
    - include_global=False (orgs, events, integrations, sharepoint):
        only rows whose project_id matches
    - include_global=True (processors, rules library):
        matching project_id OR missing/empty project_id (global library)
    """
    rows = list(rows or [])
    if not project_id:
        return rows
    out: List[dict] = []
    for r in rows:
        pid = r.get("project_id")
        if pid is None or pid == "":
            if include_global:
                out.append(r)
        elif pid == project_id:
            out.append(r)
    return out
