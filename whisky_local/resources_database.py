from __future__ import annotations

import sqlite3


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            category TEXT,
            focus_area TEXT,
            audience TEXT,
            region_scope TEXT,
            cost TEXT,
            small_distillery_relevance TEXT,
            source_confidence TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS resource_tags (
            resource_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (resource_id, tag),
            FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_resources_name ON resources(name);
        CREATE INDEX IF NOT EXISTS idx_resources_category ON resources(category);
        CREATE INDEX IF NOT EXISTS idx_resources_focus_area ON resources(focus_area);
        CREATE INDEX IF NOT EXISTS idx_resources_audience ON resources(audience);
        CREATE INDEX IF NOT EXISTS idx_resources_region_scope ON resources(region_scope);
        CREATE INDEX IF NOT EXISTS idx_resources_relevance ON resources(small_distillery_relevance);
        """
    )
    conn.commit()


def upsert_resource(conn: sqlite3.Connection, payload: dict[str, str]) -> int:
    conn.execute(
        """
        INSERT INTO resources (
            slug, name, url, category, focus_area, audience,
            region_scope, cost, small_distillery_relevance,
            source_confidence, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            url=excluded.url,
            category=excluded.category,
            focus_area=excluded.focus_area,
            audience=excluded.audience,
            region_scope=excluded.region_scope,
            cost=excluded.cost,
            small_distillery_relevance=excluded.small_distillery_relevance,
            source_confidence=excluded.source_confidence,
            notes=excluded.notes
        """,
        (
            payload["slug"],
            payload["name"],
            payload["url"],
            payload["category"],
            payload["focus_area"],
            payload["audience"],
            payload["region_scope"],
            payload["cost"],
            payload["small_distillery_relevance"],
            payload["source_confidence"],
            payload["notes"],
        ),
    )

    row = conn.execute("SELECT id FROM resources WHERE slug = ?", (payload["slug"],)).fetchone()
    if not row:
        raise RuntimeError("Failed to upsert resource row")
    return int(row[0])


def replace_tags(conn: sqlite3.Connection, resource_id: int, tags: list[str]) -> None:
    conn.execute("DELETE FROM resource_tags WHERE resource_id = ?", (resource_id,))
    for tag in sorted({tag.strip() for tag in tags if tag.strip()}):
        conn.execute(
            "INSERT OR IGNORE INTO resource_tags(resource_id, tag) VALUES (?, ?)",
            (resource_id, tag),
        )
