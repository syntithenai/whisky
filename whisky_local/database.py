from __future__ import annotations

from pathlib import Path
import sqlite3
import re


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS distilleries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            country TEXT,
            region TEXT,
            section TEXT,
            why_study TEXT,
            official_site TEXT,
            description TEXT,
            key_focus TEXT,
            study_status TEXT,
            operating_status TEXT,
            website_confidence TEXT,
            notes TEXT,
            source_headers TEXT,
            search_terms TEXT,
            search_metadata_json TEXT,
            last_summarized_at TEXT
        );

        CREATE TABLE IF NOT EXISTS styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS distillery_styles (
            distillery_id INTEGER NOT NULL,
            style_id INTEGER NOT NULL,
            PRIMARY KEY (distillery_id, style_id),
            FOREIGN KEY (distillery_id) REFERENCES distilleries(id) ON DELETE CASCADE,
            FOREIGN KEY (style_id) REFERENCES styles(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distillery_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            fetched_at TEXT,
            UNIQUE(distillery_id, url),
            FOREIGN KEY (distillery_id) REFERENCES distilleries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distillery_id INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            page_url TEXT,
            local_path TEXT NOT NULL,
            category TEXT,
            alt_text TEXT,
            score INTEGER DEFAULT 0,
            UNIQUE(distillery_id, source_url),
            FOREIGN KEY (distillery_id) REFERENCES distilleries(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_distilleries_name ON distilleries(name);
        CREATE INDEX IF NOT EXISTS idx_distilleries_country ON distilleries(country);
        CREATE INDEX IF NOT EXISTS idx_distilleries_region ON distilleries(region);
        CREATE INDEX IF NOT EXISTS idx_distilleries_operating ON distilleries(operating_status);
        CREATE INDEX IF NOT EXISTS idx_distilleries_confidence ON distilleries(website_confidence);
        CREATE INDEX IF NOT EXISTS idx_images_distillery ON images(distillery_id);
        """
    )

    # Lightweight migration for existing databases created before new columns.
    existing_cols = {
        str(row[1]).lower() for row in conn.execute("PRAGMA table_info(distilleries)").fetchall()
    }
    if "description" not in existing_cols:
        conn.execute("ALTER TABLE distilleries ADD COLUMN description TEXT")
    if "search_terms" not in existing_cols:
        conn.execute("ALTER TABLE distilleries ADD COLUMN search_terms TEXT")
    if "search_metadata_json" not in existing_cols:
        conn.execute("ALTER TABLE distilleries ADD COLUMN search_metadata_json TEXT")
    if "last_summarized_at" not in existing_cols:
        conn.execute("ALTER TABLE distilleries ADD COLUMN last_summarized_at TEXT")
    conn.commit()


def upsert_distillery(conn: sqlite3.Connection, payload: dict[str, str]) -> int:
    conn.execute(
        """
        INSERT INTO distilleries (
            slug, name, country, region, section, why_study, official_site,
            description,
            key_focus, study_status, operating_status, website_confidence,
            notes, source_headers, search_terms, search_metadata_json, last_summarized_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            country=excluded.country,
            region=excluded.region,
            section=excluded.section,
            why_study=excluded.why_study,
            official_site=excluded.official_site,
            description=excluded.description,
            key_focus=excluded.key_focus,
            study_status=excluded.study_status,
            operating_status=excluded.operating_status,
            website_confidence=excluded.website_confidence,
            notes=excluded.notes,
            source_headers=excluded.source_headers,
            search_terms=excluded.search_terms,
            search_metadata_json=excluded.search_metadata_json,
            last_summarized_at=excluded.last_summarized_at
        """,
        (
            payload["slug"],
            payload["name"],
            payload["country"],
            payload["region"],
            payload["section"],
            payload["why_study"],
            payload["official_site"],
            payload.get("description", ""),
            payload["key_focus"],
            payload["study_status"],
            payload["operating_status"],
            payload["website_confidence"],
            payload["notes"],
            payload["source_headers"],
            payload.get("search_terms", ""),
            payload.get("search_metadata_json", ""),
            payload.get("last_summarized_at", ""),
        ),
    )

    # Always re-select by slug because sqlite lastrowid is not reliable for UPSERT updates.
    row = conn.execute(
        "SELECT id FROM distilleries WHERE slug = ?",
        (payload["slug"],),
    ).fetchone()
    return int(row["id"])


def replace_styles(conn: sqlite3.Connection, distillery_id: int, styles: set[str]) -> None:
    conn.execute(
        "DELETE FROM distillery_styles WHERE distillery_id = ?",
        (distillery_id,),
    )

    for style in sorted(styles):
        conn.execute("INSERT OR IGNORE INTO styles(name) VALUES (?)", (style,))
        style_id = conn.execute(
            "SELECT id FROM styles WHERE name = ?",
            (style,),
        ).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO distillery_styles(distillery_id, style_id) VALUES (?, ?)",
            (distillery_id, style_id),
        )

    conn.commit()
