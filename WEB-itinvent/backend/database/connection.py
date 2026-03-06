"""
Database connection management with dynamic database switching support.
"""
import pyodbc
import os
from contextlib import contextmanager
from typing import Generator, Optional

from backend.config import config


def get_database_config(db_id: Optional[str] = None) -> dict:
    """
    Get database configuration by ID.
    If db_id is None, returns default configuration from config.

    Args:
        db_id: Database ID (e.g., "ITINVENT", "MSK-ITINVENT", "OBJ-ITINVENT", "SPB-ITINVENT")

    Returns:
        Dictionary with host, database, username, password, driver
    """
    if not db_id or db_id == config.database.database:
        return {
            "host": config.database.host,
            "database": config.database.database,
            "username": config.database.username,
            "password": config.database.password,
            "driver": config.database.driver,
        }

    # Get config for specific database from environment
    env_prefix = f"DB_{db_id}_"
    return {
        "host": os.getenv(f"{env_prefix}HOST", config.database.host),
        "database": os.getenv(f"{env_prefix}DATABASE", db_id),
        "username": os.getenv(f"{env_prefix}USERNAME", "ROUser"),
        "password": os.getenv(f"{env_prefix}PASSWORD", ""),
        "driver": config.database.driver,
    }


def build_connection_string(db_config: dict) -> str:
    """Build ODBC connection string from database config."""
    return (
        f"DRIVER={db_config['driver']};"
        f"SERVER={db_config['host']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['username']};"
        f"PWD={db_config['password']};"
        "TrustServerCertificate=yes;"
        "autocommit=True;"
    )


class DatabaseConnectionManager:
    """Manager for SQL Server database connections with dynamic switching."""

    def __init__(self, db_id: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_id: Database ID to use (None for default)
        """
        self._pool_size = 10
        self._db_id = db_id
        self._db_config = get_database_config(db_id)
        self._connection_string = build_connection_string(self._db_config)

    def get_current_database(self) -> str:
        """Get current database ID."""
        return self._db_id or self._db_config["database"]

    @contextmanager
    def get_connection(self) -> Generator[pyodbc.Connection, None, None]:
        """
        Get a database connection from the pool.

        Usage:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ITEMS")
        """
        conn = None
        try:
            conn = pyodbc.connect(self._connection_string, timeout=30)
            conn.autocommit = False
            conn.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def test_connection(self) -> bool:
        """Test if database connection is working."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            print(f"Database connection error: {e}")
            return False

    def execute_query(self, query: str, params: Optional[tuple] = None) -> list[dict]:
        """
        Execute a SELECT query and return results as list of dicts.

        Args:
            query: SQL query with ? placeholders
            params: Tuple of parameters for query

        Returns:
            List of dictionaries with column names as keys
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())

            # Get column names from cursor.description
            columns = [column[0] for column in cursor.description] if cursor.description else []

            # Convert rows to dictionaries
            results = []
            for row in cursor:
                results.append(dict(zip(columns, row)))

            return results

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query.

        Args:
            query: SQL query with ? placeholders
            params: Tuple of parameters for query

        Returns:
            Number of affected rows
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.rowcount


# Global default connection manager instance
db_manager = DatabaseConnectionManager()


def get_db(db_id: Optional[str] = None) -> DatabaseConnectionManager:
    """
    Dependency function for FastAPI to get database manager.

    Args:
        db_id: Database ID to use (None for default)

    Returns:
        DatabaseConnectionManager instance
    """
    return DatabaseConnectionManager(db_id)


# User database selection (in-memory for session)
_user_databases: dict[str, str] = {}


def _build_user_key(user_id: Optional[int] = None, username: Optional[str] = None) -> Optional[str]:
    """
    Build a stable key for user-scoped storage.

    Priority:
    1. Non-zero numeric user_id
    2. Username (lowercase)
    """
    if user_id not in (None, 0):
        return f"id:{int(user_id)}"
    if username:
        normalized = str(username).strip().lower()
        if normalized:
            return f"user:{normalized}"
    return None


def set_user_database(user_id: Optional[int], db_id: str, username: Optional[str] = None) -> None:
    """Set selected database for a user (by id or username)."""
    key = _build_user_key(user_id, username)
    if not key:
        return
    _user_databases[key] = db_id


def get_user_database(user_id: Optional[int], username: Optional[str] = None) -> Optional[str]:
    """Get selected database for a user (by id or username)."""
    # Try strict id key first, then username key fallback.
    id_key = _build_user_key(user_id, None)
    if id_key and id_key in _user_databases:
        return _user_databases[id_key]

    user_key = _build_user_key(None, username)
    if user_key and user_key in _user_databases:
        return _user_databases[user_key]

    return None


def clear_user_database(user_id: Optional[int], username: Optional[str] = None) -> None:
    """Clear database selection for a user."""
    id_key = _build_user_key(user_id, None)
    user_key = _build_user_key(None, username)
    if id_key:
        _user_databases.pop(id_key, None)
    if user_key:
        _user_databases.pop(user_key, None)
