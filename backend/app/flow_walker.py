def _ordered(edges, by_id):
    """Transform and publish map run before integrations and publish.

    A fan-out used to follow edge order. The first path to Publish won, so a
    Chroma processor wired to both an integration and a transform published the
    raw Chroma result.
    """
    rank = {
        "schema": 0, "rule": 1, "processor": 2, "transform": 3, "publishMap": 4,
        "if": 5, "switch": 5, "integration": 8, "alert": 8, "publish": 9, "stop": 10,
    }
    return sorted(edges, key=lambda e: rank.get((by_id.get(e.get("target")) or {}).get("type"), 6))
