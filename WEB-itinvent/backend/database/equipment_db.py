"""
Equipment database functions using correct schema with dynamic database switching.
"""
from typing import List, Dict, Any, Optional
import logging

from backend.database.connection import get_db

logger = logging.getLogger(__name__)


def _group_rows_by_branch_location(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Group flat rows by branch and location."""
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for item in rows or []:
        branch = item.get('branch_name') or 'Не указан'
        location = item.get('location') or 'Не указано'

        if branch not in grouped:
            grouped[branch] = {}
        if location not in grouped[branch]:
            grouped[branch][location] = []

        grouped[branch][location].append(item)

    return grouped


def get_all_equipment(page: int = 1, limit: int = 50, db_id: Optional[str] = None) -> Dict[str, Any]:
    """Get all equipment with pagination."""
    db = get_db(db_id)
    offset = (page - 1) * limit

    from backend.database.queries_new import QUERY_COUNT_ALL_EQUIPMENT

    count_result = db.execute_query(QUERY_COUNT_ALL_EQUIPMENT, ())
    total = count_result[0]['total'] if count_result else 0

    from backend.database.queries_new import QUERY_GET_ALL_EQUIPMENT
    equipment = db.execute_query(
        QUERY_GET_ALL_EQUIPMENT,
        (offset, limit)
    )

    return {
        'equipment': equipment,
        'total': total,
        'page': page,
        'limit': limit,
        'pages': (total + limit - 1) // limit
    }


def get_equipment_by_branch(branch_name: str, page: int = 1, limit: int = 10000, db_id: Optional[str] = None) -> Dict[str, Any]:
    """Get equipment filtered by branch."""
    logger.info(f"Getting equipment for branch: {branch_name}, db_id: {db_id}")
    try:
        db = get_db(db_id)
        logger.info(f"Database connection established: {db.get_current_database()}")
        offset = (page - 1) * limit

        from backend.database.queries_new import QUERY_COUNT_BY_BRANCH, QUERY_GET_EQUIPMENT_BY_BRANCH

        count_result = db.execute_query(QUERY_COUNT_BY_BRANCH, (branch_name,))
        total = count_result[0]['total'] if count_result else 0

        equipment = db.execute_query(
            QUERY_GET_EQUIPMENT_BY_BRANCH,
            (branch_name, offset, limit)
        )

        logger.info(f"Found {total} equipment items for branch {branch_name}")

        return {
            'equipment': equipment,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit,
            'branch': branch_name
        }
    except Exception as e:
        logger.error(f"Error getting equipment by branch: {e}", exc_info=True)
        raise


def get_all_branches(db_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all branches."""
    db = get_db(db_id)
    from backend.database.queries_new import QUERY_GET_ALL_BRANCHES
    return db.execute_query(QUERY_GET_ALL_BRANCHES, ())


def get_locations_by_branch(branch_no: int, db_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get locations for a branch."""
    db = get_db(db_id)
    from backend.database.queries_new import QUERY_GET_LOCATIONS_BY_BRANCH
    return db.execute_query(QUERY_GET_LOCATIONS_BY_BRANCH, (branch_no,))


def get_all_equipment_types(db_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all equipment types."""
    db = get_db(db_id)
    from backend.database.queries_new import QUERY_GET_ALL_EQUIPMENT_TYPES
    return db.execute_query(QUERY_GET_ALL_EQUIPMENT_TYPES, ())


def get_equipment_grouped(page: int = 1, limit: int = 100, db_id: Optional[str] = None) -> Dict[str, Any]:
    """Get equipment grouped by branch and location (simplified fields)."""
    db = get_db(db_id)
    offset = (page - 1) * limit

    from backend.database.queries_new import QUERY_GET_EQUIPMENT_GROUPED, QUERY_COUNT_ALL_EQUIPMENT

    count_result = db.execute_query(QUERY_COUNT_ALL_EQUIPMENT, ())
    total = count_result[0]['total'] if count_result else 0

    equipment = db.execute_query(
        QUERY_GET_EQUIPMENT_GROUPED,
        (offset, limit)
    )

    grouped = _group_rows_by_branch_location(equipment)

    return {
        'grouped': grouped,
        'total': total,
        'page': page,
        'limit': limit,
        'pages': (total + limit - 1) // limit
    }


def get_all_equipment_flat(db_id: Optional[str] = None, limit: int = 10000) -> List[Dict[str, Any]]:
    """Fetch all CI_TYPE=1 equipment in a single query without pagination.

    Returns flat list of rows (not grouped). Use this instead of paginated
    get_equipment_grouped when you need the full dataset in one round-trip.
    """
    db = get_db(db_id)
    from backend.database.queries_new import QUERY_GET_EQUIPMENT_GROUPED_ALL
    rows = db.execute_query(QUERY_GET_EQUIPMENT_GROUPED_ALL, ())
    return (rows or [])[:limit]


def get_consumables_grouped(page: int = 1, limit: int = 100, db_id: Optional[str] = None) -> Dict[str, Any]:
    """Get consumables (CI_TYPE=4) grouped by branch and location."""
    db = get_db(db_id)
    offset = (page - 1) * limit

    from backend.database.queries_new import QUERY_GET_CONSUMABLES_GROUPED, QUERY_COUNT_ALL_CONSUMABLES

    count_result = db.execute_query(QUERY_COUNT_ALL_CONSUMABLES, ())
    total = count_result[0]['total'] if count_result else 0

    consumables = db.execute_query(
        QUERY_GET_CONSUMABLES_GROUPED,
        (offset, limit)
    )

    grouped = _group_rows_by_branch_location(consumables)

    return {
        'grouped': grouped,
        'total': total,
        'page': page,
        'limit': limit,
        'pages': (total + limit - 1) // limit
    }
