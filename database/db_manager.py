"""
database/db_manager.py

SQLite database manager for government scheme data.
Handles schema creation, CRUD operations, and search.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("database/schemes.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schemes (
    scheme_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_name      TEXT NOT NULL UNIQUE,
    description      TEXT,
    benefits         TEXT,
    state            TEXT DEFAULT 'All',
    district         TEXT DEFAULT 'All',
    min_age          INTEGER,
    max_age          INTEGER,
    income_limit     INTEGER,
    occupation       TEXT DEFAULT 'All',
    education        TEXT,
    category         TEXT DEFAULT 'All',
    disability_required   INTEGER DEFAULT 0,
    minority_required     INTEGER DEFAULT 0,
    widow_required        INTEGER DEFAULT 0,
    ex_serviceman_required INTEGER DEFAULT 0,
    residence_type   TEXT DEFAULT 'Both',
    gender           TEXT DEFAULT 'Any',
    source_url       TEXT,
    application_link TEXT,
    eligibility_text TEXT,
    last_updated     TEXT
);
"""

CREATE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS recommendation_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name     TEXT,
    user_profile  TEXT,
    recommendations TEXT,
    timestamp     TEXT
);
"""

CREATE_ANALYTICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scheme_analytics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_name   TEXT,
    recommended_count INTEGER DEFAULT 0,
    last_recommended  TEXT
);
"""


class DBManager:
    """
    Database manager for scheme storage, retrieval, and management.
    Uses SQLite for zero-dependency operation.
    """

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create all tables if they don't exist."""
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(CREATE_HISTORY_TABLE_SQL)
            conn.execute(CREATE_ANALYTICS_TABLE_SQL)
            conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    # ── JSON helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_list(value) -> str:
        """Convert list to JSON string for storage."""
        if isinstance(value, list):
            return json.dumps(value)
        if isinstance(value, str):
            return value
        return json.dumps(["All"])

    @staticmethod
    def _deserialize_list(value: Optional[str]) -> List[str]:
        """Convert stored JSON string back to list."""
        if not value:
            return ["All"]
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, TypeError):
            return [value] if value else ["All"]

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def insert_scheme(self, scheme: Dict[str, Any]) -> bool:
        """Insert a single scheme. Returns True on success, False on duplicate."""
        sql = """
        INSERT OR IGNORE INTO schemes (
            scheme_name, description, benefits, state, district,
            min_age, max_age, income_limit, occupation, education,
            category, disability_required, minority_required,
            widow_required, ex_serviceman_required, residence_type,
            gender, source_url, application_link, eligibility_text, last_updated
        ) VALUES (
            :scheme_name, :description, :benefits, :state, :district,
            :min_age, :max_age, :income_limit, :occupation, :education,
            :category, :disability_required, :minority_required,
            :widow_required, :ex_serviceman_required, :residence_type,
            :gender, :source_url, :application_link, :eligibility_text, :last_updated
        )
        """
        params = {
            "scheme_name": scheme.get("scheme_name", ""),
            "description": scheme.get("description", ""),
            "benefits": scheme.get("benefits", ""),
            "state": self._serialize_list(scheme.get("state", ["All"])),
            "district": self._serialize_list(scheme.get("district", ["All"])),
            "min_age": scheme.get("min_age"),
            "max_age": scheme.get("max_age"),
            "income_limit": scheme.get("income_limit"),
            "occupation": self._serialize_list(scheme.get("occupation", ["All"])),
            "education": scheme.get("education"),
            "category": self._serialize_list(scheme.get("category", ["All"])),
            "disability_required": int(scheme.get("disability_required", False)),
            "minority_required": int(scheme.get("minority_required", False)),
            "widow_required": int(scheme.get("widow_required", False)),
            "ex_serviceman_required": int(scheme.get("ex_serviceman_required", False)),
            "residence_type": scheme.get("residence_type", "Both"),
            "gender": scheme.get("gender", "Any"),
            "source_url": scheme.get("source_url", ""),
            "application_link": scheme.get("application_link", ""),
            "eligibility_text": scheme.get("eligibility_text", ""),
            "last_updated": datetime.now().isoformat(),
        }
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def update_scheme(self, scheme_name: str, scheme: Dict[str, Any]) -> bool:
        """Update an existing scheme by name."""
        sql = """
        UPDATE schemes SET
            description=:description, benefits=:benefits, state=:state,
            district=:district, min_age=:min_age, max_age=:max_age,
            income_limit=:income_limit, occupation=:occupation, education=:education,
            category=:category, disability_required=:disability_required,
            minority_required=:minority_required, widow_required=:widow_required,
            ex_serviceman_required=:ex_serviceman_required, residence_type=:residence_type,
            gender=:gender, source_url=:source_url, application_link=:application_link,
            eligibility_text=:eligibility_text, last_updated=:last_updated
        WHERE scheme_name=:scheme_name
        """
        params = {
            "scheme_name": scheme_name,
            "description": scheme.get("description", ""),
            "benefits": scheme.get("benefits", ""),
            "state": self._serialize_list(scheme.get("state", ["All"])),
            "district": self._serialize_list(scheme.get("district", ["All"])),
            "min_age": scheme.get("min_age"),
            "max_age": scheme.get("max_age"),
            "income_limit": scheme.get("income_limit"),
            "occupation": self._serialize_list(scheme.get("occupation", ["All"])),
            "education": scheme.get("education"),
            "category": self._serialize_list(scheme.get("category", ["All"])),
            "disability_required": int(scheme.get("disability_required", False)),
            "minority_required": int(scheme.get("minority_required", False)),
            "widow_required": int(scheme.get("widow_required", False)),
            "ex_serviceman_required": int(scheme.get("ex_serviceman_required", False)),
            "residence_type": scheme.get("residence_type", "Both"),
            "gender": scheme.get("gender", "Any"),
            "source_url": scheme.get("source_url", ""),
            "application_link": scheme.get("application_link", ""),
            "eligibility_text": scheme.get("eligibility_text", ""),
            "last_updated": datetime.now().isoformat(),
        }
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def upsert_scheme(self, scheme: Dict[str, Any]):
        """Insert or update a scheme."""
        inserted = self.insert_scheme(scheme)
        if not inserted:
            self.update_scheme(scheme["scheme_name"], scheme)

    def delete_scheme(self, scheme_name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM schemes WHERE scheme_name=?", (scheme_name,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_old_schemes(self, before_date: str):
        """Remove schemes not updated since before_date (ISO format)."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM schemes WHERE last_updated < ?", (before_date,)
            )
            conn.commit()
            logger.info(f"Deleted {cursor.rowcount} stale schemes")

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_all_schemes(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM schemes ORDER BY scheme_name").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_scheme_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM schemes WHERE scheme_name=?", (name,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_scheme_by_id(self, scheme_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM schemes WHERE scheme_id=?", (scheme_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def search_schemes(self, keyword: str) -> List[Dict[str, Any]]:
        """Full-text search across name, description, and benefits."""
        kw = f"%{keyword}%"
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM schemes
                   WHERE scheme_name LIKE ?
                      OR description LIKE ?
                      OR benefits LIKE ?
                      OR eligibility_text LIKE ?
                   ORDER BY scheme_name""",
                (kw, kw, kw, kw),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count_schemes(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]

    # ── History & Analytics ───────────────────────────────────────────────────

    def save_recommendation_history(
        self,
        user_name: str,
        user_profile: Dict,
        recommendations: List[Dict],
    ):
        sql = """
        INSERT INTO recommendation_history
            (user_name, user_profile, recommendations, timestamp)
        VALUES (?, ?, ?, ?)
        """
        with self._connect() as conn:
            conn.execute(
                sql,
                (
                    user_name,
                    json.dumps(user_profile),
                    json.dumps([r.get("scheme_name") for r in recommendations]),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            # Update analytics
            for rec in recommendations:
                self._increment_analytics(conn, rec.get("scheme_name", ""))
            conn.commit()

    def _increment_analytics(self, conn: sqlite3.Connection, scheme_name: str):
        existing = conn.execute(
            "SELECT id FROM scheme_analytics WHERE scheme_name=?", (scheme_name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE scheme_analytics SET recommended_count=recommended_count+1, "
                "last_recommended=? WHERE scheme_name=?",
                (datetime.now().isoformat(), scheme_name),
            )
        else:
            conn.execute(
                "INSERT INTO scheme_analytics (scheme_name, recommended_count, last_recommended) "
                "VALUES (?, 1, ?)",
                (scheme_name, datetime.now().isoformat()),
            )

    def get_recommendation_history(self, limit: int = 50) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendation_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_analytics(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scheme_analytics ORDER BY recommended_count DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Admin ─────────────────────────────────────────────────────────────────

    def add_scheme_admin(self, scheme: Dict[str, Any]):
        """Admin: insert with auto-parsed list fields."""
        self.upsert_scheme(scheme)

    def edit_scheme_admin(self, scheme_name: str, updates: Dict[str, Any]):
        """Admin: patch specific fields."""
        existing = self.get_scheme_by_name(scheme_name)
        if not existing:
            raise ValueError(f"Scheme '{scheme_name}' not found")
        merged = {**existing, **updates}
        self.update_scheme(scheme_name, merged)

    # ── Bulk ──────────────────────────────────────────────────────────────────

    def bulk_upsert(self, schemes: List[Dict[str, Any]]) -> int:
        """Upsert many schemes. Returns count of processed."""
        count = 0
        for s in schemes:
            try:
                self.upsert_scheme(s)
                count += 1
            except Exception as exc:
                logger.error(f"Failed to upsert '{s.get('scheme_name')}': {exc}")
        logger.info(f"Bulk upsert: {count}/{len(schemes)} schemes processed")
        return count

    # ── Row conversion ────────────────────────────────────────────────────────

    def _row_to_dict(self, row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        if row is None:
            return {}
        d = dict(row)
        # Deserialize JSON lists
        for field in ["state", "district", "occupation", "category"]:
            d[field] = self._deserialize_list(d.get(field))
        # Convert booleans
        for field in ["disability_required", "minority_required", "widow_required", "ex_serviceman_required"]:
            d[field] = bool(d.get(field, 0))
        return d


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db = DBManager()
    print(f"Total schemes in DB: {db.count_schemes()}")
    schemes = db.get_all_schemes()
    for s in schemes[:3]:
        print(f"  • [{s['scheme_id']}] {s['scheme_name']}")
