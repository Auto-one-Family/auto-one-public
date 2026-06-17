"""
Database Type Definitions

Provides dialect-compatible types for use across PostgreSQL (production)
and SQLite (unit tests). JSONB is PostgreSQL-specific; SQLite uses JSON.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


class JSONBCompat(JSONB):
    """
    JSONB for PostgreSQL, JSON for SQLite.

    Use this instead of raw JSONB when the table may be created with SQLite
    (e.g. in-memory tests). SQLite does not support JSONB; this type
    automatically falls back to JSON when the dialect is sqlite.
    """

    _variant_mapping = {"sqlite": JSON()}
