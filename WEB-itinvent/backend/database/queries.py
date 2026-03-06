"""
SQL queries for ITINVENT database.
All queries use parameterized statements to prevent SQL injection.
Based on universal_database.py schema
"""
from datetime import datetime
from typing import Optional, List, Any, Dict
import mimetypes
import base64
import re
import os
from backend.database.connection import get_db


# SQL Queries
QUERY_SEARCH_BY_SERIAL = """
    SELECT
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        i.PART_NO,
        t.TYPE_NO as type_no,
        t.TYPE_NAME as type_name,
        m.MODEL_NO as model_no,
        m.MODEL_NAME as model_name,
        v.VENDOR_NO as vendor_no,
        v.VENDOR_NAME as vendor_name,
        s.STATUS_NO as status_no,
        s.DESCR as status_name,
        o.OWNER_NO as empl_no,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        b.BRANCH_NO as branch_no,
        b.BRANCH_NAME as branch_name,
        l.LOC_NO as loc_no,
        l.DESCR as location_name
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1 AND (i.SERIAL_NO LIKE ?
       OR i.HW_SERIAL_NO LIKE ?
       OR CAST(i.INV_NO AS VARCHAR(50)) LIKE ?)
    ORDER BY i.INV_NO
"""

QUERY_SEARCH_UNIVERSAL = """
    SELECT TOP {limit}
        i.INV_NO as inv_no,
        i.SERIAL_NO as serial_no,
        i.HW_SERIAL_NO as hw_serial_no,
        i.PART_NO as part_no,
        i.IP_ADDRESS as ip_address,
        i.MAC_ADDRESS as mac_address,
        i.NETBIOS_NAME as network_name,
        i.DOMAIN_NAME as domain_name,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as vendor_name,
        s.DESCR as status_name,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location_name
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1 AND (i.SERIAL_NO LIKE ?
       OR i.HW_SERIAL_NO LIKE ?
       OR CAST(i.INV_NO AS VARCHAR(50)) LIKE ?
       OR m.MODEL_NAME LIKE ?
       OR v.VENDOR_NAME LIKE ?
       OR o.OWNER_DISPLAY_NAME LIKE ?
       OR o.OWNER_DEPT LIKE ?
       OR b.BRANCH_NAME LIKE ?
       OR l.DESCR LIKE ?
       OR t.TYPE_NAME LIKE ?
       OR s.DESCR LIKE ?
       OR i.IP_ADDRESS LIKE ?
       OR i.MAC_ADDRESS LIKE ?
       OR i.NETBIOS_NAME LIKE ?
       OR i.DOMAIN_NAME LIKE ?)
    ORDER BY i.INV_NO
""".format(limit="{limit}")

QUERY_COUNT_UNIVERSAL = """
    SELECT COUNT(DISTINCT i.INV_NO, i.SERIAL_NO, i.HW_SERIAL_NO) as total
    FROM ITEMS i
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    WHERE i.CI_TYPE = 1 AND (i.SERIAL_NO LIKE ?
       OR i.HW_SERIAL_NO LIKE ?
       OR CAST(i.INV_NO AS VARCHAR(50)) LIKE ?
       OR m.MODEL_NAME LIKE ?
       OR v.VENDOR_NAME LIKE ?
       OR o.OWNER_DISPLAY_NAME LIKE ?
       OR o.OWNER_DEPT LIKE ?
       OR b.BRANCH_NAME LIKE ?
       OR l.DESCR LIKE ?
       OR t.TYPE_NAME LIKE ?
       OR s.DESCR LIKE ?
       OR i.IP_ADDRESS LIKE ?
       OR i.MAC_ADDRESS LIKE ?
       OR i.NETBIOS_NAME LIKE ?
       OR i.DOMAIN_NAME LIKE ?)
"""

QUERY_SEARCH_BY_EMPLOYEE = """
    SELECT DISTINCT
        o.OWNER_NO,
        o.OWNER_DISPLAY_NAME,
        o.OWNER_DEPT,
        COUNT(i.INV_NO) as equipment_count
    FROM OWNERS o
    LEFT JOIN ITEMS i ON o.OWNER_NO = i.EMPL_NO AND i.CI_TYPE = 1
    WHERE o.OWNER_DISPLAY_NAME LIKE ?
       OR o.OWNER_DEPT LIKE ?
    GROUP BY o.OWNER_NO, o.OWNER_DISPLAY_NAME, o.OWNER_DEPT
    ORDER BY o.OWNER_DISPLAY_NAME
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_COUNT_EMPLOYEES = """
    SELECT COUNT(DISTINCT o.OWNER_NO) as total
    FROM OWNERS o
    WHERE o.OWNER_DISPLAY_NAME LIKE ?
       OR o.OWNER_DEPT LIKE ?
"""

QUERY_GET_EQUIPMENT_BY_OWNER = """
    SELECT
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as vendor_name,
        s.DESCR as status_name,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location_name
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1 AND i.EMPL_NO = ?
    ORDER BY i.INV_NO
"""

QUERY_GET_EQUIPMENT_BY_INV = """
    SELECT
        i.ID as id,
        i.INV_NO as inv_no,
        i.SERIAL_NO as serial_no,
        i.HW_SERIAL_NO as hw_serial_no,
        i.PART_NO as part_no,
        i.CI_TYPE as ci_type,
        i.TYPE_NO as type_no,
        i.MODEL_NO as model_no,
        i.STATUS_NO as status_no,
        i.EMPL_NO as empl_no,
        i.BRANCH_NO as branch_no,
        i.LOC_NO as loc_no,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as vendor_name,
        s.DESCR as status,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        o.OWNER_EMAIL as employee_email,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location,
        i.DESCR as DESCRIPTION,
        i.IP_ADDRESS as ip_address,
        NULL as mac_address,
        NULL as network_name,
        NULL as domain_name
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1 AND i.INV_NO = ?
"""

QUERY_GET_ALL_EQUIPMENT = """
    SELECT
        i.INV_NO,
        i.SERIAL_NO,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        o.OWNER_DISPLAY_NAME as employee_name,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location_name,
        s.DESCR as status_name
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1
    ORDER BY i.INV_NO
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_COUNT_ALL_EQUIPMENT = """
    SELECT COUNT(*) as total
    FROM ITEMS i
    WHERE i.CI_TYPE = 1
"""

QUERY_GET_ALL_BRANCHES = """
    SELECT BRANCH_NO, BRANCH_NAME
    FROM BRANCHES
    ORDER BY BRANCH_NAME
"""

QUERY_GET_LOCATIONS_BY_BRANCH = """
    SELECT DISTINCT
        i.LOC_NO as LOC_NO,
        l.DESCR as LOC_NAME
    FROM ITEMS i
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.BRANCH_NO = ?
      AND i.LOC_NO IS NOT NULL
    ORDER BY l.DESCR
"""

QUERY_GET_ALL_EQUIPMENT_TYPES = """
    SELECT CI_TYPE, TYPE_NO, TYPE_NAME
    FROM CI_TYPES
    WHERE CI_TYPE IS NOT NULL AND TYPE_NO IS NOT NULL
    ORDER BY TYPE_NAME
"""

QUERY_GET_ALL_STATUSES = """
    SELECT STATUS_NO, DESCR as STATUS_NAME
    FROM STATUS
    ORDER BY DESCR
"""

QUERY_GET_MODELS_BY_TYPE = """
    SELECT
        m.MODEL_NO as model_no,
        m.MODEL_NAME as model_name,
        m.TYPE_NO as type_no
    FROM CI_MODELS m
    WHERE m.CI_TYPE = 1 AND m.TYPE_NO = ?
    ORDER BY m.MODEL_NAME
"""

# Branches for database switching
AVAILABLE_DATABASES = {
    "ITINVENT": {
        "host": "10.103.0.213",
        "database": "ITINVENT",
        "username": "ROUser",
        "access": "read-only",
        "description": "Главная база"
    },
    "MSK-ITINVENT": {
        "host": "10.103.0.213",
        "database": "MSK-ITINVENT",
        "username": "ROUser",
        "access": "read-only",
        "description": "Филиал Москва"
    },
    "OBJ-ITINVENT": {
        "host": "10.103.0.213",
        "database": "OBJ-ITINVENT",
        "username": "RWUser",
        "access": "read-write",
        "description": "Объекты"
    },
    "SPB-ITINVENT": {
        "host": "10.103.0.213",
        "database": "SPB-ITINVENT",
        "username": "ROUser",
        "access": "read-only",
        "description": "Филиал Санкт-Петербург"
    },
}


def search_equipment_by_serial(search_term: str, db_id: Optional[str] = None) -> List[dict]:
    """
    Search equipment by serial number, hardware serial, or inventory number.

    Args:
        search_term: Serial number or inventory number to search for
        db_id: Database ID to use (None for default)

    Returns:
        List of equipment dictionaries
    """
    db = get_db(db_id)
    pattern = f"%{search_term}%"
    return db.execute_query(QUERY_SEARCH_BY_SERIAL, (pattern, pattern, pattern))


def search_equipment_universal(search_term: str, page: int = 1, limit: int = 50, db_id: Optional[str] = None) -> dict:
    """
    Universal search across all equipment fields.

    Args:
        search_term: Search term
        page: Page number (1-indexed)
        limit: Results per page
        db_id: Database ID to use (None for default)

    Returns:
        Dict with equipment list and pagination info
    """
    import logging
    logger = logging.getLogger(__name__)
    
    db = get_db(db_id)
    pattern = f"%{search_term}%"
    
    # Get results using TOP
    query = QUERY_SEARCH_UNIVERSAL.format(limit=limit)
    logger.info(f"Universal search: term='{search_term}', limit={limit}")
    logger.info(f"Query: {query[:200]}...")
    
    try:
        equipment = db.execute_query(query, (pattern,) * 15)
        logger.info(f"Found {len(equipment)} results")
        total = len(equipment)
    except Exception as e:
        logger.error(f"Search error: {e}")
        equipment = []
        total = 0
    
    return {
        "equipment": equipment,
        "total": total,
        "page": 1,
        "pages": 1
    }


def search_employees(search_term: str, page: int = 1, limit: int = 50, db_id: Optional[str] = None) -> dict:
    """
    Search employees by name or department.

    Args:
        search_term: Name or department to search for
        page: Page number (1-indexed)
        limit: Results per page
        db_id: Database ID to use (None for default)

    Returns:
        Dict with employees list and pagination info
    """
    db = get_db(db_id)
    pattern = f"%{search_term}%"
    offset = (page - 1) * limit

    # Get count for pagination
    count_result = db.execute_query(QUERY_COUNT_EMPLOYEES, (pattern, pattern))
    total = count_result[0]["total"] if count_result else 0

    # Get employees
    employees = db.execute_query(
        QUERY_SEARCH_BY_EMPLOYEE,
        (pattern, pattern, offset, limit)
    )

    return {
        "employees": employees,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


def get_equipment_by_owner(owner_no: int, db_id: Optional[str] = None) -> List[dict]:
    """
    Get all equipment assigned to an employee.

    Args:
        owner_no: Employee ID (OWNER_NO)
        db_id: Database ID to use (None for default)

    Returns:
        List of equipment dictionaries
    """
    db = get_db(db_id)
    return db.execute_query(QUERY_GET_EQUIPMENT_BY_OWNER, (owner_no,))


def get_equipment_by_inv(inv_no: str, db_id: Optional[str] = None) -> Optional[dict]:
    """
    Get equipment by inventory number.

    Args:
        inv_no: Inventory number (string or numeric)
        db_id: Database ID to use (None for default)

    Returns:
        Equipment dict or None if not found
    """
    db = get_db(db_id)
    # INV_NO is float in database, convert string to float
    try:
        inv_no_float = float(inv_no) if inv_no else None
    except (ValueError, TypeError):
        inv_no_float = None
    # Primary expected columns in ITINVENT DB snapshots.
    # If a specific database does not have these columns, query will fallback below.
    optional_ip_select = "i.IP_ADDRESS as ip_address"
    optional_mac_select = "i.MAC_ADDRESS as mac_address"
    optional_network_select = "i.NETBIOS_NAME as network_name"
    optional_domain_select = "i.DOMAIN_NAME as domain_name"

    try:
        item_columns = _get_table_columns("ITEMS", db_id)
        available_columns = {
            str(row.get("column_name") or row.get("COLUMN_NAME") or "").upper()
            for row in (item_columns or [])
        }

        def _pick_first(candidates: List[str]) -> Optional[str]:
            for column in candidates:
                if column in available_columns:
                    return column
            return None

        ip_col = _pick_first(["IP_ADDRESS"])
        mac_col = _pick_first(["MAC_ADDRESS", "MAC_ADDR", "MAC"])
        network_col = _pick_first(
            [
                "NETBIOS_NAME",
                "HOST_NAME",
                "HOSTNAME",
                "DNS_NAME",
                "NETWORK_NAME",
                "NET_NAME",
                "PC_NAME",
                "COMPUTER_NAME",
            ]
        )
        domain_col = _pick_first(["DOMAIN_NAME", "NET_DOMAIN", "DOMAIN"])

        if ip_col:
            optional_ip_select = f"i.{ip_col} as ip_address"
        if mac_col:
            optional_mac_select = f"i.{mac_col} as mac_address"
        if network_col:
            optional_network_select = f"i.{network_col} as network_name"
        if domain_col:
            optional_domain_select = f"i.{domain_col} as domain_name"
    except Exception:
        pass

    query = f"""
        SELECT
            i.ID as id,
            i.INV_NO as inv_no,
            i.SERIAL_NO as serial_no,
            i.HW_SERIAL_NO as hw_serial_no,
            i.PART_NO as part_no,
            i.CI_TYPE as ci_type,
            i.TYPE_NO as type_no,
            i.MODEL_NO as model_no,
            i.STATUS_NO as status_no,
            i.EMPL_NO as empl_no,
            i.BRANCH_NO as branch_no,
            i.LOC_NO as loc_no,
            t.TYPE_NAME as type_name,
            m.MODEL_NAME as model_name,
            v.VENDOR_NAME as vendor_name,
            s.DESCR as status,
            o.OWNER_DISPLAY_NAME as employee_name,
            o.OWNER_DEPT as employee_dept,
            o.OWNER_EMAIL as employee_email,
            b.BRANCH_NAME as branch_name,
            l.DESCR as location,
            i.DESCR as DESCRIPTION,
            {optional_ip_select},
            {optional_mac_select},
            {optional_network_select},
            {optional_domain_select}
        FROM ITEMS i
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
        LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
        LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
        LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
        LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
        WHERE i.CI_TYPE = 1 AND i.INV_NO = ?
    """

    try:
        result = db.execute_query(query, (inv_no_float,))
    except Exception:
        # Safe fallback to legacy query shape when optional metadata lookup fails.
        result = db.execute_query(QUERY_GET_EQUIPMENT_BY_INV, (inv_no_float,))
    return result[0] if result else None


def _resolve_doc_type_names(type_nos: List[Any], db_id: Optional[str] = None) -> dict[int, str]:
    """
    Resolve DOCS.TYPE_NO -> readable type name from doc-type lookup tables.

    This function is defensive because DB snapshots may differ:
    it discovers candidate tables in INFORMATION_SCHEMA and tries each one.
    """
    normalized_type_nos: List[int] = []
    for raw in type_nos or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in normalized_type_nos:
            normalized_type_nos.append(value)

    if not normalized_type_nos:
        return {}

    db = get_db(db_id)
    mapping: dict[int, str] = {}

    def _doc_label_score(label: str) -> int:
        text = str(label or "").strip().lower()
        if not text:
            return 0
        keywords = [
            "акт",
            "аннулир",
            "док",
            "перемещ",
            "передач",
            "прием",
            "наклад",
            "счет",
        ]
        return 1 if any(keyword in text for keyword in keywords) else 0

    def _query_table_mapping(
        *,
        table_name: str,
        type_column: str,
        name_column: str,
    ) -> dict[int, str]:
        if not table_name or not type_column or not name_column:
            return {}
        safe_table_name = table_name.replace("]", "]]")
        safe_type_column = type_column.replace("]", "]]")
        safe_name_column = name_column.replace("]", "]]")
        placeholders = ", ".join(["?"] * len(normalized_type_nos))
        query = f"""
            SELECT
                t.[{safe_type_column}] AS type_no,
                t.[{safe_name_column}] AS type_name
            FROM [{safe_table_name}] t
            WHERE t.[{safe_type_column}] IN ({placeholders})
        """
        try:
            rows = db.execute_query(query, tuple(sorted(normalized_type_nos)))
        except Exception:
            return {}

        result: dict[int, str] = {}
        for row in rows or []:
            try:
                type_no = int(row.get("type_no") or row.get("TYPE_NO"))
            except (TypeError, ValueError):
                continue
            type_name = str(row.get("type_name") or row.get("TYPE_NAME") or "").strip()
            if type_no in normalized_type_nos and type_name:
                result[type_no] = type_name
        return result

    # 1) Preferred source: FK from DOCS.TYPE_NO to dictionary table.
    fk_candidates: List[dict[str, str]] = []
    try:
        fk_rows = db.execute_query(
            """
            SELECT DISTINCT
                kcu2.TABLE_NAME AS ref_table,
                kcu2.COLUMN_NAME AS ref_column
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu1
                ON rc.CONSTRAINT_NAME = kcu1.CONSTRAINT_NAME
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
               AND kcu1.ORDINAL_POSITION = kcu2.ORDINAL_POSITION
            WHERE kcu1.TABLE_NAME = 'DOCS'
              AND kcu1.COLUMN_NAME = 'TYPE_NO'
            """
        )
        for row in fk_rows or []:
            ref_table = str(row.get("ref_table") or row.get("REF_TABLE") or "").strip()
            ref_column = str(row.get("ref_column") or row.get("REF_COLUMN") or "").strip()
            if not ref_table or not ref_column:
                continue
            # Resolve preferred title column in referenced table.
            col_rows = db.execute_query(
                """
                SELECT
                    MAX(CASE WHEN c.COLUMN_NAME = 'TYPE_NAME' THEN 1 ELSE 0 END) AS has_type_name,
                    MAX(CASE WHEN c.COLUMN_NAME = 'DESCR' THEN 1 ELSE 0 END) AS has_descr
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE c.TABLE_NAME = ?
                  AND c.COLUMN_NAME IN ('TYPE_NAME', 'DESCR')
                """,
                (ref_table,),
            )
            has_type_name = int((col_rows[0].get("has_type_name") or col_rows[0].get("HAS_TYPE_NAME") or 0)) == 1 if col_rows else False
            has_descr = int((col_rows[0].get("has_descr") or col_rows[0].get("HAS_DESCR") or 0)) == 1 if col_rows else False
            if not (has_type_name or has_descr):
                continue
            fk_candidates.append(
                {
                    "table_name": ref_table,
                    "type_column": ref_column,
                    "name_column": "TYPE_NAME" if has_type_name else "DESCR",
                }
            )
    except Exception:
        fk_candidates = []

    best_fk_mapping: dict[int, str] = {}
    best_fk_score = (-1, -1)
    for item in fk_candidates:
        candidate_mapping = _query_table_mapping(
            table_name=item["table_name"],
            type_column=item["type_column"],
            name_column=item["name_column"],
        )
        if not candidate_mapping:
            continue
        doc_hits = sum(_doc_label_score(value) for value in candidate_mapping.values())
        score = (doc_hits, len(candidate_mapping))
        if score > best_fk_score:
            best_fk_score = score
            best_fk_mapping = candidate_mapping

    # FK source is authoritative for document types.
    if best_fk_mapping:
        return best_fk_mapping

    # 2) Fallback source: only DOC* tables with TYPE_NO + TYPE_NAME/DESCR.
    candidate_tables: List[dict[str, Any]] = []
    try:
        table_rows = db.execute_query(
            """
            SELECT
                c.TABLE_NAME AS table_name,
                MAX(CASE WHEN c.COLUMN_NAME = 'TYPE_NO' THEN 1 ELSE 0 END) AS has_type_no,
                MAX(CASE WHEN c.COLUMN_NAME = 'TYPE_NAME' THEN 1 ELSE 0 END) AS has_type_name,
                MAX(CASE WHEN c.COLUMN_NAME = 'DESCR' THEN 1 ELSE 0 END) AS has_descr
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE c.TABLE_NAME LIKE '%DOC%'
              AND c.COLUMN_NAME IN ('TYPE_NO', 'TYPE_NAME', 'DESCR')
            GROUP BY c.TABLE_NAME
            """
        )
        for row in table_rows or []:
            table_name = str(row.get("table_name") or row.get("TABLE_NAME") or "").strip()
            if not table_name or table_name.upper() in {"DOCS", "DOCS_LIST"}:
                continue
            has_type_no = int(row.get("has_type_no") or row.get("HAS_TYPE_NO") or 0) == 1
            has_type_name = int(row.get("has_type_name") or row.get("HAS_TYPE_NAME") or 0) == 1
            has_descr = int(row.get("has_descr") or row.get("HAS_DESCR") or 0) == 1
            if has_type_no and (has_type_name or has_descr):
                candidate_tables.append(
                    {
                        "table_name": table_name,
                        "name_column": "TYPE_NAME" if has_type_name else "DESCR",
                    }
                )
    except Exception:
        candidate_tables = []

    best_mapping: dict[int, str] = {}
    best_score = (-1, -1, -1)
    for item in candidate_tables:
        candidate_mapping = _query_table_mapping(
            table_name=str(item.get("table_name") or ""),
            type_column="TYPE_NO",
            name_column=str(item.get("name_column") or ""),
        )
        if not candidate_mapping:
            continue
        doc_hits = sum(_doc_label_score(value) for value in candidate_mapping.values())
        # Require at least one document-like label to avoid wrong dictionary.
        if doc_hits <= 0:
            continue
        table_name = str(item.get("table_name") or "").upper()
        doc_priority = 1 if table_name.startswith("DOC") else 0
        score = (doc_hits, len(candidate_mapping), doc_priority)
        if score > best_score:
            best_score = score
            best_mapping = candidate_mapping

    return best_mapping


def get_equipment_acts_by_inv(inv_no: str, db_id: Optional[str] = None) -> dict:
    """
    Get equipment-linked documents (acts) by inventory number.

    Link is resolved through DOCS_LIST.ITEM_ID -> DOCS.DOC_NO.

    Args:
        inv_no: Inventory number
        db_id: Database ID to use (None for default)

    Returns:
        Dict with item_id and acts list
    """
    equipment = get_equipment_by_inv(inv_no, db_id)
    if not equipment:
        return {"item_id": None, "acts": []}

    item_id_raw = equipment.get("id") or equipment.get("ID")
    try:
        item_id = int(item_id_raw) if item_id_raw is not None else None
    except (TypeError, ValueError):
        item_id = None

    if item_id is None:
        return {"item_id": None, "acts": []}

    db = get_db(db_id)
    query = """
        SELECT
            dl.ITEM_ID AS item_id,
            dl.CI_TYPE AS ci_type,
            d.DOC_NO AS doc_no,
            d.DOC_NUMBER AS doc_number,
            d.DOC_DATE AS doc_date,
            d.TYPE_NO AS type_no,
            d.COMP_NO AS comp_no,
            d.BRANCH_NO AS branch_no,
            b.BRANCH_NAME AS branch_name,
            d.LOC_NO AS loc_no,
            l.DESCR AS location_name,
            d.EMPL_NO AS empl_no,
            o.OWNER_DISPLAY_NAME AS employee_name,
            d.SUPPL_NO AS suppl_no,
            d.DOC_SUMM AS doc_summ,
            d.ADDINFO AS add_info,
            d.CREATE_DATE AS create_date,
            d.CREATE_USER_NAME AS create_user_name,
            d.CH_DATE AS ch_date,
            d.CH_USER AS ch_user
        FROM DOCS_LIST dl
        INNER JOIN DOCS d ON d.DOC_NO = dl.DOC_NO
        LEFT JOIN BRANCHES b ON b.BRANCH_NO = d.BRANCH_NO
        LEFT JOIN LOCATIONS l ON l.LOC_NO = d.LOC_NO
        LEFT JOIN OWNERS o ON o.OWNER_NO = d.EMPL_NO
        WHERE dl.ITEM_ID = ?
          AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
        ORDER BY
            CASE WHEN d.DOC_DATE IS NULL THEN 1 ELSE 0 END,
            d.DOC_DATE DESC,
            d.CREATE_DATE DESC,
            d.DOC_NO DESC
    """
    acts = db.execute_query(query, (item_id,))
    type_name_map = _resolve_doc_type_names(
        [act.get("type_no") or act.get("TYPE_NO") for act in acts or []],
        db_id=db_id,
    )
    for act in acts or []:
        raw_type_no = act.get("type_no") or act.get("TYPE_NO")
        try:
            type_no = int(raw_type_no) if raw_type_no is not None else None
        except (TypeError, ValueError):
            type_no = None
        if type_no is not None and type_no in type_name_map:
            act["type_name"] = type_name_map[type_no]

    return {"item_id": item_id, "acts": acts}


def get_equipment_items_by_ids(item_ids: List[int], db_id: Optional[str] = None) -> List[dict]:
    """
    Resolve equipment records by ITEMS.ID.

    Returns normalized fields used by uploaded-act draft preview.
    """
    normalized_ids: List[int] = []
    for raw in item_ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in normalized_ids:
            normalized_ids.append(value)

    if not normalized_ids:
        return []

    placeholders = ", ".join(["?"] * len(normalized_ids))
    query = f"""
        SELECT
            i.ID AS item_id,
            CAST(i.INV_NO AS VARCHAR(64)) AS inv_no,
            i.SERIAL_NO AS serial_no,
            m.MODEL_NAME AS model_name,
            o.OWNER_DISPLAY_NAME AS employee_name,
            b.BRANCH_NAME AS branch_name,
            l.DESCR AS location_name
        FROM ITEMS i
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
        LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
        LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
        WHERE i.CI_TYPE = 1
          AND i.ID IN ({placeholders})
        ORDER BY i.ID
    """
    db = get_db(db_id)
    return db.execute_query(query, tuple(normalized_ids))


def _normalize_inv_no_token(raw: Any) -> Optional[str]:
    """Normalize inventory number token for resilient matching."""
    text = str(raw or "").strip()
    if not text:
        return None

    text = re.sub(r"\s+", "", text)
    text = text.replace("№", "")
    text = text.strip(".,;:|")
    if not text:
        return None

    if re.fullmatch(r"\d+[.,]0+", text):
        text = re.split(r"[.,]", text, maxsplit=1)[0]
    if re.fullmatch(r"\d+", text):
        text = str(int(text))

    return text


def get_equipment_items_by_inv_nos(inv_nos: List[str], db_id: Optional[str] = None) -> List[dict]:
    """
    Resolve equipment records by ITEMS.INV_NO.

    Returns normalized fields used by uploaded-act draft preview.
    """
    normalized_tokens: List[str] = []
    for raw in inv_nos or []:
        token = _normalize_inv_no_token(raw)
        if token and token not in normalized_tokens:
            normalized_tokens.append(token)

    if not normalized_tokens:
        return []

    text_tokens = list(normalized_tokens)
    numeric_tokens: List[int] = []
    for token in normalized_tokens:
        if re.fullmatch(r"\d+", token):
            numeric = int(token)
            if numeric not in numeric_tokens:
                numeric_tokens.append(numeric)

    where_parts: List[str] = []
    params: List[Any] = []

    if text_tokens:
        placeholders = ", ".join(["?"] * len(text_tokens))
        where_parts.append(f"UPPER(CAST(i.INV_NO AS VARCHAR(64))) IN ({placeholders})")
        params.extend([token.upper() for token in text_tokens])

    if numeric_tokens:
        placeholders = ", ".join(["?"] * len(numeric_tokens))
        where_parts.append(f"TRY_CONVERT(BIGINT, i.INV_NO) IN ({placeholders})")
        params.extend(numeric_tokens)

    if not where_parts:
        return []

    query = f"""
        SELECT
            i.ID AS item_id,
            CAST(i.INV_NO AS VARCHAR(64)) AS inv_no,
            i.SERIAL_NO AS serial_no,
            m.MODEL_NAME AS model_name,
            o.OWNER_DISPLAY_NAME AS employee_name,
            b.BRANCH_NAME AS branch_name,
            l.DESCR AS location_name
        FROM ITEMS i
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
        LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
        LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
        WHERE i.CI_TYPE = 1
          AND ({' OR '.join(where_parts)})
        ORDER BY TRY_CONVERT(BIGINT, i.INV_NO), i.ID
    """
    db = get_db(db_id)
    return db.execute_query(query, tuple(params))


def find_duplicate_uploaded_act(
    document_title: str,
    file_name: str,
    db_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Detect possible duplicate act by DOCS and FILES metadata.
    """
    db = get_db(db_id)
    title = str(document_title or "").strip()
    fname = str(file_name or "").strip()

    if title:
        docs_rows = db.execute_query(
            """
            SELECT TOP 1
                d.DOC_NO AS doc_no,
                d.DOC_NUMBER AS doc_number,
                d.DOC_DATE AS doc_date
            FROM DOCS d
            WHERE d.DOC_NUMBER = ?
               OR d.ADDINFO = ?
            ORDER BY
                CASE WHEN d.DOC_DATE IS NULL THEN 1 ELSE 0 END,
                d.DOC_DATE DESC,
                d.DOC_NO DESC
            """,
            (title, title),
        )
        if docs_rows:
            row = docs_rows[0]
            return {
                "source": "DOCS",
                "doc_no": row.get("doc_no") or row.get("DOC_NO"),
                "doc_number": row.get("doc_number") or row.get("DOC_NUMBER"),
                "doc_date": row.get("doc_date") or row.get("DOC_DATE"),
            }

    if fname or title:
        files_rows = db.execute_query(
            """
            SELECT TOP 1
                f.ITEM_ID AS doc_no,
                f.FILE_NO AS file_no,
                f.FILE_NAME AS file_name,
                f.FILE_DESCR AS file_descr,
                f.CREATE_DATE AS create_date
            FROM FILES f
            WHERE (? <> '' AND f.FILE_NAME = ?)
               OR (? <> '' AND f.FILE_DESCR = ?)
            ORDER BY f.CREATE_DATE DESC, f.FILE_NO DESC
            """,
            (fname, fname, title, title),
        )
        if files_rows:
            row = files_rows[0]
            return {
                "source": "FILES",
                "doc_no": row.get("doc_no") or row.get("DOC_NO"),
                "file_no": row.get("file_no") or row.get("FILE_NO"),
                "file_name": row.get("file_name") or row.get("FILE_NAME"),
                "file_descr": row.get("file_descr") or row.get("FILE_DESCR"),
                "create_date": row.get("create_date") or row.get("CREATE_DATE"),
            }

    return None


def create_uploaded_transfer_act(
    *,
    document_title: str,
    from_employee: str,
    to_employee: str,
    doc_date: Optional[datetime],
    equipment_item_ids: List[int],
    file_name: str,
    file_bytes: bytes,
    created_by: str = "IT-WEB",
    db_id: Optional[str] = None,
) -> dict:
    """
    Create uploaded transfer act in DOCS + DOCS_LIST + FILES within one transaction.
    """
    if not file_bytes:
        raise ValueError("file_bytes is empty")

    normalized_ids: List[int] = []
    for raw in equipment_item_ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in normalized_ids:
            normalized_ids.append(value)
    if not normalized_ids:
        raise ValueError("equipment_item_ids is empty")

    title = str(document_title or "").strip()
    if not title:
        title = "Перемещение оборудования"
    title = title[:250]

    safe_file_name = str(file_name or "").strip() or f"Акт {datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    file_descr = title[:250]

    date_value = doc_date or datetime.now()
    from_employee_value = str(from_employee or "").strip()
    to_employee_value = str(to_employee or "").strip()
    add_info = f"Передача: {from_employee_value or '-'} → {to_employee_value or '-'}"
    if title and title.lower() not in add_info.lower():
        add_info = f"{add_info}. {title}"
    add_info = add_info[:500]

    owner_no = None
    if to_employee_value:
        owner_no = get_owner_no_by_name(to_employee_value, strict=True, db_id=db_id)
        if owner_no is None:
            owner_no = get_owner_no_by_name(to_employee_value, strict=False, db_id=db_id)

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Collect previous act links before creating a new act.
        previous_act_links: dict[int, list[str]] = {}
        previous_doc_by_item: dict[int, int] = {}
        if normalized_ids:
            placeholders_prev = ", ".join(["?"] * len(normalized_ids))
            cursor.execute(
                f"""
                SELECT
                    dl.DOC_NO,
                    dl.ITEM_ID,
                    CAST(i.INV_NO AS VARCHAR(64)) AS INV_NO,
                    i.SERIAL_NO AS SERIAL_NO,
                    m.MODEL_NAME AS MODEL_NAME
                FROM DOCS_LIST dl
                INNER JOIN DOCS d ON d.DOC_NO = dl.DOC_NO
                LEFT JOIN ITEMS i ON i.ID = dl.ITEM_ID AND i.CI_TYPE = 1
                LEFT JOIN CI_MODELS m ON m.CI_TYPE = i.CI_TYPE AND m.MODEL_NO = i.MODEL_NO
                WHERE dl.ITEM_ID IN ({placeholders_prev})
                  AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
                  AND (
                    LOWER(COALESCE(d.DOC_NUMBER, N'')) LIKE N'%акт%'
                    OR LOWER(COALESCE(d.ADDINFO, N'')) LIKE N'%акт%'
                    OR LOWER(COALESCE(d.DOC_NUMBER, N'')) LIKE N'%перемещ%'
                    OR LOWER(COALESCE(d.ADDINFO, N'')) LIKE N'%перемещ%'
                  )
                """,
                tuple(normalized_ids),
            )
            for row in cursor.fetchall() or []:
                try:
                    prev_doc_no = int(row[0]) if row[0] is not None else None
                except Exception:
                    prev_doc_no = None
                if prev_doc_no is None:
                    continue
                try:
                    item_id_value = int(row[1]) if row[1] is not None else None
                except Exception:
                    item_id_value = None
                if item_id_value is not None:
                    current_prev = previous_doc_by_item.get(item_id_value)
                    if current_prev is None or prev_doc_no > current_prev:
                        previous_doc_by_item[item_id_value] = prev_doc_no

                inv_value = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
                serial_value = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
                model_value = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""

                label_parts: List[str] = []
                if inv_value:
                    label_parts.append(f"Инв.№ {inv_value}")
                if serial_value:
                    label_parts.append(f"Серийный {serial_value}")
                if model_value:
                    label_parts.append(f"Модель {model_value}")
                item_label = ", ".join(label_parts).strip()
                if not item_label:
                    item_label = f"ITEM_ID {row[1]}"

                bucket = previous_act_links.setdefault(prev_doc_no, [])
                if item_label and item_label not in bucket:
                    bucket.append(item_label)

        # 1) Resolve branch/location from linked equipment (priority source).
        equipment_branch_no = None
        equipment_loc_no = None
        if normalized_ids:
            placeholders = ", ".join(["?"] * len(normalized_ids))
            cursor.execute(
                f"""
                SELECT i.ID, i.BRANCH_NO, i.LOC_NO
                FROM ITEMS i
                WHERE i.CI_TYPE = 1
                  AND i.ID IN ({placeholders})
                """,
                tuple(normalized_ids),
            )
            rows = cursor.fetchall()
            by_item_id = {}
            for row in rows or []:
                try:
                    by_item_id[int(row[0])] = row
                except Exception:
                    continue

            for item_id in normalized_ids:
                row = by_item_id.get(int(item_id))
                if row is None:
                    continue
                if equipment_branch_no is None and row[1] is not None:
                    equipment_branch_no = int(row[1])
                if equipment_loc_no is None and row[2] is not None:
                    equipment_loc_no = int(row[2])
                if equipment_branch_no is not None and equipment_loc_no is not None:
                    break

        # 2) Resolve generic template defaults from latest linked document.
        cursor.execute(
            """
            SELECT TOP 1
                d.TYPE_NO, d.COMP_NO, d.BRANCH_NO, d.LOC_NO, d.EMPL_NO, d.SUPPL_NO
            FROM DOCS d
            WHERE EXISTS (
                SELECT 1
                FROM DOCS_LIST dl
                WHERE dl.DOC_NO = d.DOC_NO
                  AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
            )
            ORDER BY
                CASE WHEN d.DOC_DATE IS NULL THEN 1 ELSE 0 END,
                d.DOC_DATE DESC,
                d.DOC_NO DESC
            """
        )
        template = cursor.fetchone()

        template_type_no = int(template[0]) if template and template[0] is not None else 0
        template_comp_no = int(template[1]) if template and template[1] is not None else 0
        template_branch_no = int(template[2]) if template and template[2] is not None else None
        template_loc_no = int(template[3]) if template and template[3] is not None else None
        template_empl_no = int(template[4]) if template and template[4] is not None else None
        template_suppl_no = int(template[5]) if template and template[5] is not None else None

        # Force document type as "Act" using recent act documents.
        cursor.execute(
            """
            SELECT TOP 1 d.TYPE_NO
            FROM DOCS d
            WHERE d.TYPE_NO IS NOT NULL
              AND (
                LOWER(COALESCE(d.DOC_NUMBER, N'')) LIKE N'%акт%'
                OR LOWER(COALESCE(d.ADDINFO, N'')) LIKE N'%акт%'
              )
            ORDER BY
                CASE WHEN d.DOC_DATE IS NULL THEN 1 ELSE 0 END,
                d.DOC_DATE DESC,
                d.DOC_NO DESC
            """
        )
        act_type_row = cursor.fetchone()
        if act_type_row and act_type_row[0] is not None:
            template_type_no = int(act_type_row[0])

        branch_no_value = equipment_branch_no if equipment_branch_no is not None else template_branch_no
        loc_no_value = equipment_loc_no if equipment_loc_no is not None else template_loc_no
        empl_no_value = owner_no if owner_no is not None else template_empl_no

        # 3) DOCS insert.
        cursor.execute("SELECT ISNULL(MAX(DOC_NO), 0) + 1 FROM DOCS")
        doc_no = int(cursor.fetchone()[0])

        cursor.execute(
            """
            INSERT INTO DOCS (
                DOC_NO, TYPE_NO, COMP_NO, BRANCH_NO, LOC_NO, EMPL_NO, SUPPL_NO,
                DOC_NUMBER, DOC_DATE, DOC_SUMM, ADDINFO,
                CREATE_DATE, CREATE_USER_NAME, CH_DATE, CH_USER
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_no,
                template_type_no,
                template_comp_no,
                branch_no_value,
                loc_no_value,
                empl_no_value,
                template_suppl_no,
                title,
                date_value,
                0,
                add_info,
                date_value,
                created_by,
                date_value,
                created_by,
            ),
        )

        # 4) DOCS_LIST links. Keep old links; add only missing links for the new act.
        for item_id in normalized_ids:
            cursor.execute(
                """
                IF NOT EXISTS (
                    SELECT 1
                    FROM DOCS_LIST
                    WHERE DOC_NO = ? AND ITEM_ID = ? AND (CI_TYPE = 1 OR CI_TYPE IS NULL)
                )
                INSERT INTO DOCS_LIST (DOC_NO, ITEM_ID, CI_TYPE)
                VALUES (?, ?, 1)
                """,
                (doc_no, item_id, doc_no, item_id),
            )

        # 5) Add transfer note to equipment DESCRIPTION.
        if normalized_ids:
            placeholders_items = ", ".join(["?"] * len(normalized_ids))
            cursor.execute(
                f"""
                SELECT i.ID, i.DESCR
                FROM ITEMS i
                WHERE i.CI_TYPE = 1
                  AND i.ID IN ({placeholders_items})
                """,
                tuple(normalized_ids),
            )
            descr_by_item: dict[int, str] = {}
            for row in cursor.fetchall() or []:
                try:
                    descr_item_id = int(row[0]) if row[0] is not None else None
                except Exception:
                    descr_item_id = None
                if descr_item_id is None:
                    continue
                descr_by_item[descr_item_id] = str(row[1]) if row[1] is not None else ""

            max_descr_len = 4000
            now_text_for_items = datetime.now().strftime("%d.%m.%Y %H:%M")
            now_dt_for_items = datetime.now()
            for item_id in normalized_ids:
                item_id_int = int(item_id)
                prev_doc_no_for_item = previous_doc_by_item.get(item_id_int)
                if prev_doc_no_for_item is not None and int(prev_doc_no_for_item) != int(doc_no):
                    note_line = f"{now_text_for_items}: акт №{int(prev_doc_no_for_item)}→№{doc_no}"
                else:
                    note_line = f"{now_text_for_items}: акт №{doc_no}"

                if len(note_line) > max_descr_len:
                    note_line = note_line[:max_descr_len]

                existing_descr = descr_by_item.get(item_id_int) or ""
                if existing_descr:
                    remaining = max_descr_len - len(note_line) - 1
                    if remaining < 0:
                        remaining = 0
                    existing_descr = existing_descr[:remaining]
                    separator = "" if existing_descr.endswith(("\r\n", "\n")) else "\n"
                    new_descr = f"{existing_descr}{separator}{note_line}" if existing_descr else note_line
                else:
                    new_descr = note_line

                cursor.execute(
                    """
                    UPDATE ITEMS
                    SET DESCR = ?, CH_DATE = ?, CH_USER = ?
                    WHERE ID = ? AND CI_TYPE = 1
                    """,
                    (new_descr, now_dt_for_items, created_by, item_id_int),
                )

        # 6) Add note to previous acts and auto-annul old act when all items moved.
        annulled_doc_nos: List[int] = []
        cursor.execute(
            """
            SELECT TOP 1 d.TYPE_NO
            FROM DOCS d
            WHERE d.TYPE_NO IS NOT NULL
              AND (
                LOWER(COALESCE(d.DOC_NUMBER, N'')) LIKE N'%аннулирован%'
                OR LOWER(COALESCE(d.ADDINFO, N'')) LIKE N'%аннулирован%'
              )
            ORDER BY
                CASE WHEN d.DOC_DATE IS NULL THEN 1 ELSE 0 END,
                d.DOC_DATE DESC,
                d.DOC_NO DESC
            """
        )
        annulled_type_row = cursor.fetchone()
        annulled_type_no = int(annulled_type_row[0]) if annulled_type_row and annulled_type_row[0] is not None else None

        if previous_act_links:
            now_text = datetime.now().strftime("%d.%m.%Y %H:%M")
            for prev_doc_no, inv_list in previous_act_links.items():
                if int(prev_doc_no) == int(doc_no):
                    continue
                inv_part = "; ".join(inv_list[:20]) if inv_list else "нет данных"
                note = f"{now_text}: №{prev_doc_no}→№{doc_no}: {inv_part}."

                cursor.execute("SELECT TOP 1 ADDINFO FROM DOCS WHERE DOC_NO = ?", (prev_doc_no,))
                prev_row = cursor.fetchone()
                existing_addinfo = str(prev_row[0]).strip() if prev_row and prev_row[0] is not None else ""

                max_len = 500
                if len(note) > max_len:
                    note = note[:max_len]
                if existing_addinfo:
                    remaining = max_len - len(note) - 1
                    if remaining < 0:
                        remaining = 0
                    existing_addinfo = existing_addinfo[:remaining]
                    new_addinfo = f"{existing_addinfo}\n{note}" if existing_addinfo else note
                else:
                    new_addinfo = note

                cursor.execute(
                    """
                    UPDATE DOCS
                    SET ADDINFO = ?, CH_DATE = ?, CH_USER = ?
                    WHERE DOC_NO = ?
                    """,
                    (new_addinfo, datetime.now(), created_by, prev_doc_no),
                )

                # Annul old act when all its equipment already has links to newer acts.
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT dl.ITEM_ID)
                    FROM DOCS_LIST dl
                    WHERE dl.DOC_NO = ?
                      AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
                    """,
                    (prev_doc_no,),
                )
                total_items_raw = cursor.fetchone()
                total_items = int(total_items_raw[0]) if total_items_raw and total_items_raw[0] is not None else 0

                if total_items > 0:
                    cursor.execute(
                        """
                        SELECT COUNT(DISTINCT dl.ITEM_ID)
                        FROM DOCS_LIST dl
                        WHERE dl.DOC_NO = ?
                          AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
                          AND EXISTS (
                              SELECT 1
                              FROM DOCS_LIST dl2
                              INNER JOIN DOCS d2 ON d2.DOC_NO = dl2.DOC_NO
                              WHERE dl2.ITEM_ID = dl.ITEM_ID
                                AND (dl2.CI_TYPE = 1 OR dl2.CI_TYPE IS NULL)
                                AND dl2.DOC_NO > ?
                                AND (
                                    LOWER(COALESCE(d2.DOC_NUMBER, N'')) LIKE N'%акт%'
                                    OR LOWER(COALESCE(d2.ADDINFO, N'')) LIKE N'%акт%'
                                    OR LOWER(COALESCE(d2.DOC_NUMBER, N'')) LIKE N'%перемещ%'
                                    OR LOWER(COALESCE(d2.ADDINFO, N'')) LIKE N'%перемещ%'
                                )
                          )
                        """,
                        (prev_doc_no, prev_doc_no),
                    )
                    moved_items_raw = cursor.fetchone()
                    moved_items = int(moved_items_raw[0]) if moved_items_raw and moved_items_raw[0] is not None else 0

                    if moved_items >= total_items:
                        cursor.execute(
                            "SELECT TOP 1 DOC_NUMBER, ADDINFO FROM DOCS WHERE DOC_NO = ?",
                            (prev_doc_no,),
                        )
                        doc_row = cursor.fetchone()
                        old_doc_number = str(doc_row[0]).strip() if doc_row and doc_row[0] is not None else ""
                        old_addinfo = str(doc_row[1]).strip() if doc_row and doc_row[1] is not None else ""

                        annul_note = f"{now_text}: акт аннулирован (все позиции перенесены)."
                        max_len = 500
                        if len(annul_note) > max_len:
                            annul_note = annul_note[:max_len]
                        if old_addinfo:
                            remaining = max_len - len(annul_note) - 1
                            if remaining < 0:
                                remaining = 0
                            old_addinfo = old_addinfo[:remaining]
                            old_addinfo_new = f"{old_addinfo}\n{annul_note}" if old_addinfo else annul_note
                        else:
                            old_addinfo_new = annul_note

                        marker = "АННУЛИРОВАН"
                        if marker.lower() in old_doc_number.lower():
                            new_doc_number = old_doc_number
                        else:
                            prefix = "АННУЛИРОВАНО: "
                            base_name = (old_doc_number or f"Акт {prev_doc_no}").strip()
                            new_doc_number = f"{prefix}{base_name}"[:250]

                        if annulled_type_no is not None:
                            cursor.execute(
                                """
                                UPDATE DOCS
                                SET DOC_NUMBER = ?, ADDINFO = ?, TYPE_NO = ?, CH_DATE = ?, CH_USER = ?
                                WHERE DOC_NO = ?
                                """,
                                (new_doc_number, old_addinfo_new, annulled_type_no, datetime.now(), created_by, prev_doc_no),
                            )
                        else:
                            cursor.execute(
                                """
                                UPDATE DOCS
                                SET DOC_NUMBER = ?, ADDINFO = ?, CH_DATE = ?, CH_USER = ?
                                WHERE DOC_NO = ?
                                """,
                                (new_doc_number, old_addinfo_new, datetime.now(), created_by, prev_doc_no),
                            )
                        if int(prev_doc_no) not in annulled_doc_nos:
                            annulled_doc_nos.append(int(prev_doc_no))

        # 7) FILES insert (store binary PDF in FILE_DATA).
        cursor.execute("SELECT ISNULL(MAX(FILE_NO), 0) + 1 FROM FILES")
        file_no = int(cursor.fetchone()[0])

        cursor.execute(
            """
            INSERT INTO FILES (
                FILE_NO, CI_TYPE, ITEM_ID, FILE_TYPE, FILE_NAME, FILE_SIZE, FILE_DESCR, FILE_DATA,
                CREATE_DATE, CREATE_USER
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
            """,
            (
                file_no,
                10,  # Documents/acts bucket used in existing DB snapshots.
                doc_no,
                1,
                safe_file_name,
                round(float(len(file_bytes)) / (1024.0 * 1024.0), 2),
                file_descr,
                bytes(file_bytes),
                created_by,
            ),
        )

        return {
            "doc_no": doc_no,
            "doc_number": title,
            "file_no": file_no,
            "linked_item_ids": normalized_ids,
            "updated_previous_doc_nos": sorted(
                [doc for doc in previous_act_links.keys() if int(doc) != int(doc_no)]
            ),
            "annulled_doc_nos": sorted(annulled_doc_nos),
        }


def update_uploaded_transfer_act_file(
    *,
    file_no: int,
    file_bytes: bytes,
    db_id: Optional[str] = None,
) -> None:
    """
    Update FILES.FILE_DATA for uploaded act file.
    Used to post-process PDF bytes (e.g., apply visible DOC_NO stamp).
    """
    if not file_bytes:
        raise ValueError("file_bytes is empty")
    try:
        normalized_file_no = int(file_no)
    except (TypeError, ValueError):
        raise ValueError("file_no must be int") from None

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE FILES
            SET FILE_DATA = ?,
                FILE_SIZE = ?
            WHERE FILE_NO = ?
            """,
            (
                bytes(file_bytes),
                round(float(len(file_bytes)) / (1024.0 * 1024.0), 2),
                normalized_file_no,
            ),
        )


def update_uploaded_transfer_act_file_by_doc_no(
    *,
    doc_no: int,
    file_bytes: bytes,
    db_id: Optional[str] = None,
) -> Optional[int]:
    """
    Update latest FILES row bound to DOC_NO (FILES.ITEM_ID = DOC_NO, CI_TYPE=10).
    Returns updated FILE_NO or None if not found.
    """
    if not file_bytes:
        raise ValueError("file_bytes is empty")
    try:
        normalized_doc_no = int(doc_no)
    except (TypeError, ValueError):
        raise ValueError("doc_no must be int") from None

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1 FILE_NO
            FROM FILES
            WHERE ITEM_ID = ?
              AND CI_TYPE = 10
            ORDER BY CREATE_DATE DESC, FILE_NO DESC
            """,
            (normalized_doc_no,),
        )
        row = cursor.fetchone()
        if not row or row[0] is None:
            return None
        file_no = int(row[0])
        cursor.execute(
            """
            UPDATE FILES
            SET FILE_DATA = ?,
                FILE_SIZE = ?
            WHERE FILE_NO = ?
            """,
            (
                bytes(file_bytes),
                round(float(len(file_bytes)) / (1024.0 * 1024.0), 2),
                file_no,
            ),
        )
        return file_no


def _get_table_columns(table_name: str, db_id: Optional[str] = None) -> List[dict]:
    """Read table columns metadata from INFORMATION_SCHEMA.COLUMNS."""
    db = get_db(db_id)
    query = """
        SELECT
            COLUMN_NAME as column_name,
            DATA_TYPE as data_type
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """
    return db.execute_query(query, (table_name,))


def _guess_content_type_from_name(file_name: str) -> str:
    guessed, _ = mimetypes.guess_type(file_name or "")
    return guessed or "application/octet-stream"


def _normalize_base64_text(raw_value: Any) -> Optional[str]:
    """Normalize possible base64 text payload."""
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None

    # Handle data URI format: data:...;base64,<payload>
    if text.lower().startswith("data:") and "," in text:
        text = text.split(",", 1)[1].strip()

    # Remove whitespace/new lines often present in DB text blobs
    text = re.sub(r"\s+", "", text)
    if not text:
        return None

    # Heuristic: binary file as base64 is usually long
    if len(text) < 64:
        return None

    return text


def _try_decode_base64(raw_value: Any) -> Optional[bytes]:
    """Decode bytes from base64-like string value."""
    normalized = _normalize_base64_text(raw_value)
    if not normalized:
        return None

    candidates = [normalized]
    if "-" in normalized or "_" in normalized:
        candidates.append(normalized.replace("-", "+").replace("_", "/"))

    for candidate in candidates:
        padded = candidate
        padding = len(padded) % 4
        if padding:
            padded += "=" * (4 - padding)

        try:
            data = base64.b64decode(padded, validate=True)
            if data:
                return data
        except Exception:
            try:
                data = base64.b64decode(padded, validate=False)
                if data:
                    return data
            except Exception:
                continue

    return None


def _try_decode_base64_from_bytes(raw_bytes: bytes) -> Optional[bytes]:
    """Try base64 decode for byte payloads that actually store ASCII base64."""
    if not raw_bytes:
        return None
    try:
        text = raw_bytes.decode("ascii")
    except Exception:
        return None
    return _try_decode_base64(text)


def get_equipment_act_file(
    doc_no: Any,
    item_id: Optional[int] = None,
    inv_no: Optional[str] = None,
    db_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Resolve binary file for equipment act/document.

    Primary source: FILES table.
    Fallback source: DOCS table (if binary data is stored there).
    """
    resolved_item_id = item_id
    doc_tokens_text: List[str] = []
    doc_tokens_int: List[int] = []

    raw_doc_no = str(doc_no or "").strip()
    if raw_doc_no:
        doc_tokens_text.append(raw_doc_no)
        try:
            doc_tokens_int.append(int(raw_doc_no))
        except (TypeError, ValueError):
            pass

    # Some databases store document file metadata by DOC_NUMBER (human number),
    # while API path receives DOC_NO (internal id). Resolve both and search by both.
    if doc_no not in (None, ""):
        try:
            db_for_doc = get_db(db_id)
            doc_rows = db_for_doc.execute_query(
                """
                SELECT TOP 1 d.DOC_NUMBER
                FROM DOCS d
                WHERE d.DOC_NO = ?
                """,
                (doc_no,),
            )
            if doc_rows:
                doc_number_raw = str(doc_rows[0].get("DOC_NUMBER") or "").strip()
                if doc_number_raw and doc_number_raw not in doc_tokens_text:
                    doc_tokens_text.append(doc_number_raw)
                # Add DOC_NUMBER as numeric token only when it is a pure number.
                # Do not extract all numeric chunks from free text (e.g. date "16.02.2026"),
                # otherwise lookup can match unrelated FILES.ITEM_ID values.
                if re.fullmatch(r"\d+", doc_number_raw):
                    try:
                        as_int = int(doc_number_raw)
                        if as_int not in doc_tokens_int:
                            doc_tokens_int.append(as_int)
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass
    if resolved_item_id is None and inv_no not in (None, ""):
        equipment = get_equipment_by_inv(str(inv_no), db_id)
        if equipment:
            raw_id = equipment.get("id") or equipment.get("ID")
            try:
                resolved_item_id = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                resolved_item_id = None

    candidate_item_ids: List[int] = []
    if resolved_item_id is not None:
        candidate_item_ids = [resolved_item_id]
    elif doc_no not in (None, ""):
        try:
            db_for_items = get_db(db_id)
            link_rows = db_for_items.execute_query(
                """
                SELECT DISTINCT dl.ITEM_ID
                FROM DOCS_LIST dl
                WHERE dl.DOC_NO = ?
                  AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
                  AND dl.ITEM_ID IS NOT NULL
                """,
                (doc_no,),
            )
            for row in link_rows:
                raw = row.get("ITEM_ID") or row.get("item_id")
                try:
                    if raw is not None:
                        candidate_item_ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
        except Exception:
            # If DOCS_LIST is unavailable in this DB/user context,
            # keep fallback logic by explicit item_id/inv_no only.
            candidate_item_ids = []

    def _extract_from_table(table_name: str) -> Optional[dict]:
        columns = _get_table_columns(table_name, db_id)
        if not columns:
            return None

        db = get_db(db_id)
        names = {str(c.get("column_name") or "").upper(): str(c.get("column_name") or "") for c in columns}
        file_name_col = names.get("FILE_NAME")
        file_descr_col = names.get("FILE_DESCR")

        rows: List[dict] = []
        table_upper = table_name.upper()

        # Pass 0 (FILES-specific): strict lookup by DOC token in ITEM_ID.
        # In production snapshots act files are stored as FILES.ITEM_ID = DOC_NO.
        if table_upper == "FILES" and "ITEM_ID" in names and doc_tokens_int:
            try:
                exact_doc_ids = list(dict.fromkeys(doc_tokens_int))
                cond_item = ""
                params_item: List[Any] = []
                if len(exact_doc_ids) == 1:
                    cond_item = f"[{names['ITEM_ID']}] = ?"
                    params_item.append(exact_doc_ids[0])
                else:
                    placeholders = ", ".join(["?"] * len(exact_doc_ids))
                    cond_item = f"[{names['ITEM_ID']}] IN ({placeholders})"
                    params_item.extend(exact_doc_ids)

                conds = [cond_item]
                if "CI_TYPE" in names:
                    # Prefer documents bucket to avoid collisions with equipment attachments.
                    conds.append(f"[{names['CI_TYPE']}] = 10")
                where_exact = " AND ".join(conds)

                order_cols: List[str] = []
                if "CREATE_DATE" in names:
                    order_cols.append(f"[{names['CREATE_DATE']}] DESC")
                if "FILE_NO" in names:
                    order_cols.append(f"[{names['FILE_NO']}] DESC")
                order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""

                rows = db.execute_query(
                    f"SELECT TOP 50 * FROM {table_name} WHERE {where_exact}{order_clause}",
                    tuple(params_item),
                )
            except Exception:
                rows = []

        # Pass 1 (FILES-specific): direct metadata match by DOC number.
        if table_upper == "FILES" and not rows and doc_tokens_text and (file_name_col or file_descr_col):
            try:
                conds: List[str] = []
                ps: List[Any] = []
                for token in doc_tokens_text:
                    if not token:
                        continue
                    if file_name_col:
                        conds.append(f"[{file_name_col}] LIKE ?")
                        ps.append(f"%{token}%")
                    if file_descr_col:
                        conds.append(f"[{file_descr_col}] LIKE ?")
                        ps.append(f"%{token}%")
                where_meta = f"({' OR '.join(conds)})"
                # If possible, keep metadata search in DOC-related ITEM_ID subset only.
                if "ITEM_ID" in names and doc_tokens_int:
                    exact_doc_ids = list(dict.fromkeys(doc_tokens_int))
                    if len(exact_doc_ids) == 1:
                        where_meta += f" AND [{names['ITEM_ID']}] = ?"
                        ps.append(exact_doc_ids[0])
                    else:
                        placeholders = ", ".join(["?"] * len(exact_doc_ids))
                        where_meta += f" AND [{names['ITEM_ID']}] IN ({placeholders})"
                        ps.extend(exact_doc_ids)
                rows = db.execute_query(
                    f"SELECT TOP 50 * FROM {table_name} WHERE {where_meta} ORDER BY CREATE_DATE DESC",
                    tuple(ps),
                )
            except Exception:
                rows = []
            # Avoid false positive by ITEM_ID fallback when FILE metadata does not match DOC_NO.
            if not rows:
                return None

        # Pass 2: standard key-based filters.
        if not rows:
            conditions: List[str] = []
            params: List[Any] = []
            item_ids_for_lookup: List[int] = []
            for raw_id in (candidate_item_ids + doc_tokens_int):
                if raw_id not in item_ids_for_lookup:
                    item_ids_for_lookup.append(raw_id)

            if item_ids_for_lookup and "ITEM_ID" in names:
                if len(item_ids_for_lookup) == 1:
                    conditions.append(f"[{names['ITEM_ID']}] = ?")
                    params.append(item_ids_for_lookup[0])
                else:
                    placeholders = ", ".join(["?"] * len(item_ids_for_lookup))
                    conditions.append(f"[{names['ITEM_ID']}] IN ({placeholders})")
                    params.extend(item_ids_for_lookup)
            if doc_no not in (None, "") and "DOC_NO" in names:
                conditions.append(f"[{names['DOC_NO']}] = ?")
                params.append(doc_no)

            if not conditions:
                return None

            where_clause = " AND ".join(conditions)
            rows = db.execute_query(f"SELECT TOP 50 * FROM {table_name} WHERE {where_clause}", tuple(params))

        if not rows:
            return None

        path_columns = [
            "FILE_PATH", "PATH", "DOC_PATH", "FULL_PATH", "STORAGE_PATH", "ABS_PATH",
        ]
        url_columns = [
            "FILE_URL", "URL", "LINK", "DOC_URL",
        ]
        preferred_name_columns = [
            "FILE_NAME", "FILENAME", "DOC_FILE_NAME", "NAME",
            "FILE_TITLE", "TITLE", "DOC_NAME",
        ]
        preferred_type_columns = [
            "CONTENT_TYPE", "MIME_TYPE", "FILE_MIME",
        ]

        binary_data_types = {"varbinary", "binary", "image"}
        binary_candidates = [
            str(col.get("column_name") or "")
            for col in columns
            if str(col.get("data_type") or "").lower() in binary_data_types
        ]
        preferred_binary_names = [
            "FILE_DATA", "DOC_DATA", "DATA", "CONTENT", "FILE_CONTENT",
            "BINARY_DATA", "BIN_DATA", "IMAGE_DATA", "BODY",
        ]

        text_data_types = {"varchar", "nvarchar", "text", "ntext", "char", "nchar"}
        text_candidates = [
            str(col.get("column_name") or "")
            for col in columns
            if str(col.get("data_type") or "").lower() in text_data_types
        ]
        preferred_text_names = [
            "FILE_DATA", "DOC_DATA", "DATA", "CONTENT", "FILE_CONTENT",
            "BINARY_DATA", "BIN_DATA", "BODY", "BASE64_DATA",
        ]

        def _payload_from_row(row: dict) -> Optional[dict]:
            # 1) Path/URL storage support (keep as fallback; prefer blob when available)
            path_payload: Optional[dict] = None
            url_payload: Optional[dict] = None

            for candidate in path_columns:
                if candidate in names:
                    raw_path = row.get(names[candidate])
                    file_path = str(raw_path or "").strip()
                    if file_path:
                        file_name = os.path.basename(file_path) or f"act_{doc_no}.bin"
                        path_payload = {
                            "file_path": file_path,
                            "file_name": file_name,
                            "source_table": table_name,
                            "storage": "path",
                        }
                        break

            for candidate in url_columns:
                if candidate in names:
                    raw_url = row.get(names[candidate])
                    file_url = str(raw_url or "").strip()
                    if file_url:
                        file_name = f"act_{doc_no}.bin"
                        for name_col in preferred_name_columns:
                            if name_col in names:
                                raw_name = row.get(names[name_col])
                                if raw_name is not None and str(raw_name).strip():
                                    file_name = str(raw_name).strip()
                                    break
                        url_payload = {
                            "file_url": file_url,
                            "file_name": file_name,
                            "source_table": table_name,
                            "storage": "url",
                        }
                        break

            selected_binary_cols: List[str] = []
            for candidate in preferred_binary_names:
                if candidate in names and names[candidate] in binary_candidates:
                    selected_binary_cols.append(names[candidate])
            for col_name in binary_candidates:
                if col_name not in selected_binary_cols:
                    selected_binary_cols.append(col_name)
            for key, value in row.items():
                if key not in selected_binary_cols and isinstance(value, (bytes, bytearray, memoryview)):
                    selected_binary_cols.append(key)

            file_bytes = None
            for col_name in selected_binary_cols:
                raw_bytes = row.get(col_name)
                if isinstance(raw_bytes, memoryview):
                    candidate_bytes = raw_bytes.tobytes()
                elif isinstance(raw_bytes, bytearray):
                    candidate_bytes = bytes(raw_bytes)
                elif isinstance(raw_bytes, bytes):
                    candidate_bytes = raw_bytes
                else:
                    continue

                # Some schemas store base64 text in byte columns.
                try:
                    maybe_text = candidate_bytes.decode("ascii")
                except Exception:
                    maybe_text = None
                if maybe_text:
                    decoded = _try_decode_base64(maybe_text)
                    if decoded:
                        candidate_bytes = decoded

                if candidate_bytes:
                    file_bytes = candidate_bytes
                    if file_bytes.startswith(b"%PDF-"):
                        break

            # Fallback: decode base64 from text columns
            if not file_bytes:
                selected_text_cols: List[str] = []
                for candidate in preferred_text_names:
                    if candidate in names and names[candidate] in text_candidates:
                        selected_text_cols.append(names[candidate])
                for col_name in text_candidates:
                    if col_name not in selected_text_cols:
                        selected_text_cols.append(col_name)

                for col_name in selected_text_cols:
                    decoded = _try_decode_base64(row.get(col_name))
                    if decoded:
                        file_bytes = decoded
                        if file_bytes.startswith(b"%PDF-"):
                            break

            if not file_bytes:
                if path_payload:
                    return path_payload
                if url_payload:
                    return url_payload
                return None

            # If payload contains prefix bytes before PDF header, cut to real PDF start.
            pdf_idx = file_bytes.find(b"%PDF-")
            if 0 < pdf_idx < 4096:
                file_bytes = file_bytes[pdf_idx:]

            file_name = None
            for candidate in preferred_name_columns:
                if candidate in names:
                    value = row.get(names[candidate])
                    if value is not None and str(value).strip():
                        file_name = str(value).strip()
                        break

            if not file_name:
                ext = ".pdf" if file_bytes.startswith(b"%PDF-") else ".bin"
                file_name = f"act_{doc_no}{ext}" if doc_no not in (None, "") else f"act_file{ext}"

            content_type = None
            for candidate in preferred_type_columns:
                if candidate in names:
                    value = row.get(names[candidate])
                    normalized = str(value or "").strip().lower()
                    # Keep only valid MIME-like values.
                    if normalized and "/" in normalized and " " not in normalized:
                        content_type = normalized
                        break
            if not content_type:
                content_type = "application/pdf" if file_bytes.startswith(b"%PDF-") else _guess_content_type_from_name(file_name)

            return {
                "file_bytes": file_bytes,
                "file_name": file_name,
                "content_type": content_type,
                "source_table": table_name,
                "storage": "blob",
                "raw_name": str(row.get(file_name_col) or "") if file_name_col else "",
                "raw_descr": str(row.get(file_descr_col) or "") if file_descr_col else "",
                "raw_item_id": row.get(names["ITEM_ID"]) if "ITEM_ID" in names else None,
            }

        def _score_payload(payload: dict) -> int:
            if not payload:
                return -1
            doc_token_values = [str(token).strip().lower() for token in doc_tokens_text if str(token).strip()]
            name_text = str(payload.get("raw_name") or payload.get("file_name") or "").lower()
            descr_text = str(payload.get("raw_descr") or "").lower()
            doc_match_bonus = 0
            if doc_token_values:
                has_match = any((token in name_text) or (token in descr_text) for token in doc_token_values)
                if has_match:
                    doc_match_bonus = 40
                elif name_text or descr_text:
                    doc_match_bonus = -30

            item_match_bonus = 0
            raw_item_id = payload.get("raw_item_id")
            primary_doc_int = doc_tokens_int[0] if doc_tokens_int else None
            try:
                raw_item_id_int = int(raw_item_id) if raw_item_id is not None else None
            except (TypeError, ValueError):
                raw_item_id_int = None
            if raw_item_id_int is not None and primary_doc_int is not None:
                if raw_item_id_int == primary_doc_int:
                    item_match_bonus = 80
                elif raw_item_id_int in doc_tokens_int:
                    item_match_bonus = 40
                elif raw_item_id_int in candidate_item_ids:
                    # Penalize equipment-level attachments when DOC-level file is expected.
                    item_match_bonus = -25

            if payload.get("file_path"):
                fp = str(payload.get("file_path") or "").lower()
                base = 95 if fp.endswith(".pdf") else 70
                return base + doc_match_bonus + item_match_bonus
            if payload.get("file_url"):
                fu = str(payload.get("file_url") or "").lower()
                base = 92 if fu.endswith(".pdf") else 65
                return base + doc_match_bonus + item_match_bonus
            b = payload.get("file_bytes") or b""
            if not isinstance(b, (bytes, bytearray)):
                return 0 + doc_match_bonus + item_match_bonus
            if bytes(b).startswith(b"%PDF-"):
                return 100 + doc_match_bonus + item_match_bonus
            if b"%PDF-" in bytes(b)[:4096]:
                return 90 + doc_match_bonus + item_match_bonus
            if bytes(b).startswith(b"PK\x03\x04"):
                return 80 + doc_match_bonus + item_match_bonus
            return 10 + min(len(bytes(b)) // 1024, 30) + doc_match_bonus + item_match_bonus

        best_payload = None
        best_score = -1
        for row in rows:
            payload = _payload_from_row(row)
            score = _score_payload(payload) if payload else -1
            if score > best_score:
                best_payload = payload
                best_score = score
                if score >= 100:
                    break

        return best_payload

    payload = _extract_from_table("FILES")
    if payload:
        return payload
    return _extract_from_table("DOCS")


def inspect_equipment_act_storage(
    doc_no: Any,
    item_id: Optional[int] = None,
    inv_no: Optional[str] = None,
    db_id: Optional[str] = None,
) -> dict:
    """
    Inspect how act/document content is stored in FILES/DOCS.
    Returns metadata only (no full payload) to diagnose storage format.
    """
    resolved_item_id = item_id
    if resolved_item_id is None and inv_no not in (None, ""):
        equipment = get_equipment_by_inv(str(inv_no), db_id)
        if equipment:
            raw_id = equipment.get("id") or equipment.get("ID")
            try:
                resolved_item_id = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                resolved_item_id = None

    candidate_item_ids: List[int] = []
    docs_list_error: Optional[str] = None
    if resolved_item_id is not None:
        candidate_item_ids = [resolved_item_id]
    elif doc_no not in (None, ""):
        try:
            db_for_items = get_db(db_id)
            link_rows = db_for_items.execute_query(
                """
                SELECT DISTINCT dl.ITEM_ID
                FROM DOCS_LIST dl
                WHERE dl.DOC_NO = ?
                  AND (dl.CI_TYPE = 1 OR dl.CI_TYPE IS NULL)
                  AND dl.ITEM_ID IS NOT NULL
                """,
                (doc_no,),
            )
            for row in link_rows:
                raw = row.get("ITEM_ID") or row.get("item_id")
                try:
                    if raw is not None:
                        candidate_item_ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
        except Exception as exc:
            docs_list_error = str(exc)

    def _looks_like_path(text: str) -> bool:
        s = str(text or "").strip()
        if not s:
            return False
        sl = s.lower()
        if sl.startswith("\\\\") or re.match(r"^[a-z]:\\", sl):
            return True
        return sl.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png"))

    def _looks_like_url(text: str) -> bool:
        s = str(text or "").strip().lower()
        return s.startswith("http://") or s.startswith("https://")

    def _sample_row(row: dict, column_types: dict) -> dict:
        fields = []
        for key, value in row.items():
            if value is None:
                continue
            field_info = {
                "column": key,
                "data_type": column_types.get(key.lower()),
            }
            if isinstance(value, memoryview):
                b = value.tobytes()
                field_info.update({
                    "kind": "bytes",
                    "length": len(b),
                    "head_hex": b[:24].hex(),
                    "has_pdf_prefix": b.startswith(b"%PDF-"),
                    "has_pdf_inside": b"%PDF-" in b[:4096],
                })
            elif isinstance(value, (bytes, bytearray)):
                b = bytes(value)
                field_info.update({
                    "kind": "bytes",
                    "length": len(b),
                    "head_hex": b[:24].hex(),
                    "has_pdf_prefix": b.startswith(b"%PDF-"),
                    "has_pdf_inside": b"%PDF-" in b[:4096],
                })
                decoded_b64 = _try_decode_base64_from_bytes(b)
                if decoded_b64:
                    field_info["base64_decoded_len"] = len(decoded_b64)
                    field_info["base64_has_pdf_prefix"] = decoded_b64.startswith(b"%PDF-")
            elif isinstance(value, str):
                s = value.strip()
                field_info.update({
                    "kind": "text",
                    "length": len(s),
                    "sample": s[:140],
                    "looks_like_path": _looks_like_path(s),
                    "looks_like_url": _looks_like_url(s),
                    "looks_like_base64": _normalize_base64_text(s) is not None,
                })
                decoded = _try_decode_base64(s)
                if decoded:
                    field_info["base64_decoded_len"] = len(decoded)
                    field_info["base64_has_pdf_prefix"] = decoded.startswith(b"%PDF-")
            else:
                field_info.update({
                    "kind": type(value).__name__,
                    "sample": str(value)[:140],
                })
            fields.append(field_info)
        return {
            "non_null_fields": len(fields),
            "fields": fields,
        }

    def _inspect_table(table_name: str) -> dict:
        columns = _get_table_columns(table_name, db_id)
        column_list = [
            {
                "column_name": str(col.get("column_name") or ""),
                "data_type": str(col.get("data_type") or "").lower(),
            }
            for col in columns
        ]
        column_types = {
            str(col.get("column_name") or "").lower(): str(col.get("data_type") or "").lower()
            for col in columns
        }
        names = {str(col.get("column_name") or "").upper(): str(col.get("column_name") or "") for col in columns}

        conditions: List[str] = []
        params: List[Any] = []
        if candidate_item_ids and "ITEM_ID" in names:
            if len(candidate_item_ids) == 1:
                conditions.append(f"[{names['ITEM_ID']}] = ?")
                params.append(candidate_item_ids[0])
            else:
                placeholders = ", ".join(["?"] * len(candidate_item_ids))
                conditions.append(f"[{names['ITEM_ID']}] IN ({placeholders})")
                params.extend(candidate_item_ids)
        if doc_no not in (None, "") and "DOC_NO" in names:
            conditions.append(f"[{names['DOC_NO']}] = ?")
            params.append(doc_no)

        if not conditions:
            sample_rows = []
            try:
                db = get_db(db_id)
                rows = db.execute_query(f"SELECT TOP 3 * FROM {table_name}", ())
                sample_rows = [_sample_row(row, column_types) for row in rows]
            except Exception:
                sample_rows = []
            return {
                "table": table_name,
                "filter_supported": False,
                "rows_found": 0,
                "columns": column_list,
                "rows": sample_rows,
            }

        where_clause = " AND ".join(conditions)
        db = get_db(db_id)
        rows = db.execute_query(f"SELECT TOP 5 * FROM {table_name} WHERE {where_clause}", tuple(params))

        return {
            "table": table_name,
            "filter_supported": True,
            "rows_found": len(rows),
            "columns": column_list,
            "rows": [_sample_row(row, column_types) for row in rows],
        }

    return {
        "doc_no": doc_no,
        "item_id": resolved_item_id,
        "candidate_item_ids": candidate_item_ids,
        "docs_list_error": docs_list_error,
        "tables": [
            _inspect_table("FILES"),
            _inspect_table("DOCS"),
        ],
    }


def get_all_equipment(page: int = 1, limit: int = 50, db_id: Optional[str] = None) -> dict:
    """
    Get all equipment with pagination.

    Args:
        page: Page number (1-indexed)
        limit: Results per page
        db_id: Database ID to use (None for default)

    Returns:
        Dict with equipment list and pagination info
    """
    db = get_db(db_id)
    offset = (page - 1) * limit

    # Get count
    count_result = db.execute_query(QUERY_COUNT_ALL_EQUIPMENT)
    total = count_result[0]["total"] if count_result else 0

    # Get equipment
    equipment = db.execute_query(QUERY_GET_ALL_EQUIPMENT, (offset, limit))

    return {
        "equipment": equipment,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


def get_all_branches(db_id: Optional[str] = None) -> List[dict]:
    """Get all branches from database."""
    db = get_db(db_id)
    rows = db.execute_query(QUERY_GET_ALL_BRANCHES)
    return [
        {
            "id": row.get("id", row.get("BRANCH_NO")),
            "name": row.get("name", row.get("BRANCH_NAME")),
        }
        for row in rows
    ]


def get_locations_by_branch(branch_id: Any, db_id: Optional[str] = None) -> List[dict]:
    """Get locations for a specific branch."""
    db = get_db(db_id)
    rows = db.execute_query(QUERY_GET_LOCATIONS_BY_BRANCH, (branch_id,))
    return [
        {
            "loc_no": row.get("loc_no", row.get("LOC_NO")),
            "loc_name": row.get("loc_name", row.get("LOC_NAME")),
        }
        for row in rows
    ]


def get_all_equipment_types(db_id: Optional[str] = None) -> List[dict]:
    """Get all equipment types."""
    db = get_db(db_id)
    return db.execute_query(QUERY_GET_ALL_EQUIPMENT_TYPES)


def get_all_statuses(db_id: Optional[str] = None) -> List[dict]:
    """Get all equipment statuses."""
    db = get_db(db_id)
    rows = db.execute_query(QUERY_GET_ALL_STATUSES)
    return [
        {
            "status_no": row.get("status_no", row.get("STATUS_NO")),
            "status_name": row.get("status_name", row.get("STATUS_NAME")),
        }
        for row in rows
    ]


def get_available_databases() -> dict:
    """Get list of available databases."""
    return AVAILABLE_DATABASES


def update_equipment_location(
    inv_no: str,
    new_employee_no: int,
    branch_no: int,
    loc_no: int,
    db_id: Optional[str] = None
) -> bool:
    """
    Update equipment location and employee assignment.

    Args:
        inv_no: Inventory number (string or numeric)
        new_employee_no: New employee ID
        branch_no: Branch ID
        loc_no: Location ID
        db_id: Database ID to use (None for default)

    Returns:
        True if update was successful
    """
    db = get_db(db_id)
    # INV_NO is float in database, convert string to float
    try:
        inv_no_float = float(inv_no) if inv_no else None
    except (ValueError, TypeError):
        inv_no_float = None
    query = """
        UPDATE ITEMS
        SET EMPL_NO = ?, BRANCH_NO = ?, LOC_NO = ?
        WHERE INV_NO = ?
    """
    affected = db.execute_update(query, (new_employee_no, branch_no, loc_no, inv_no_float))
    return affected > 0


def search_owners(search_term: str, limit: int = 20, db_id: Optional[str] = None) -> List[dict]:
    """
    Search owners for autocomplete/select controls.

    Args:
        search_term: Name or department search term
        limit: Maximum number of rows
        db_id: Database ID to use

    Returns:
        List of owners with OWNER_NO, OWNER_DISPLAY_NAME, OWNER_DEPT
    """
    db = get_db(db_id)
    safe_limit = max(1, min(int(limit or 20), 100))
    pattern = f"%{search_term}%"
    query = f"""
        SELECT TOP {safe_limit}
            o.OWNER_NO,
            o.OWNER_DISPLAY_NAME,
            o.OWNER_DEPT
        FROM OWNERS o
        WHERE o.OWNER_DISPLAY_NAME LIKE ?
           OR o.OWNER_DEPT LIKE ?
        ORDER BY o.OWNER_DISPLAY_NAME
    """
    return db.execute_query(query, (pattern, pattern))


def get_owner_departments(limit: int = 500, db_id: Optional[str] = None) -> List[str]:
    """
    Get distinct owner departments for selection controls.

    Args:
        limit: Maximum number of departments
        db_id: Database ID to use

    Returns:
        List of department names
    """
    db = get_db(db_id)
    safe_limit = max(1, min(int(limit or 500), 2000))
    query = f"""
        SELECT DISTINCT TOP {safe_limit}
            LTRIM(RTRIM(o.OWNER_DEPT)) AS OWNER_DEPT
        FROM OWNERS o
        WHERE o.OWNER_DEPT IS NOT NULL
          AND LTRIM(RTRIM(o.OWNER_DEPT)) <> ''
        ORDER BY LTRIM(RTRIM(o.OWNER_DEPT))
    """
    rows = db.execute_query(query, ())
    departments: List[str] = []
    for row in rows:
        value = row.get("OWNER_DEPT") or row.get("owner_dept")
        dept = str(value or "").strip()
        if dept:
            departments.append(dept)
    return departments


def get_owner_by_no(owner_no: int, db_id: Optional[str] = None) -> Optional[dict]:
    """Get owner by OWNER_NO."""
    db = get_db(db_id)
    query = """
        SELECT
            o.OWNER_NO,
            o.OWNER_DISPLAY_NAME,
            o.OWNER_DEPT
        FROM OWNERS o
        WHERE o.OWNER_NO = ?
    """
    rows = db.execute_query(query, (owner_no,))
    return rows[0] if rows else None


def get_status_by_no(status_no: int, db_id: Optional[str] = None) -> Optional[dict]:
    """Get status by STATUS_NO."""
    db = get_db(db_id)
    query = """
        SELECT
            s.STATUS_NO,
            s.DESCR as STATUS_NAME
        FROM STATUS s
        WHERE s.STATUS_NO = ?
    """
    rows = db.execute_query(query, (status_no,))
    return rows[0] if rows else None


def get_default_status_no(db_id: Optional[str] = None) -> Optional[int]:
    """Resolve default STATUS_NO for create forms."""
    db = get_db(db_id)
    preferred_query = """
        SELECT TOP 1 s.STATUS_NO
        FROM STATUS s
        WHERE LOWER(CAST(s.DESCR AS NVARCHAR(255))) LIKE N'%эксплуата%'
        ORDER BY s.STATUS_NO
    """
    rows = db.execute_query(preferred_query, ())
    if rows:
        value = rows[0].get("STATUS_NO") or rows[0].get("status_no")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    fallback_query = """
        SELECT TOP 1 s.STATUS_NO
        FROM STATUS s
        ORDER BY s.STATUS_NO
    """
    rows = db.execute_query(fallback_query, ())
    if not rows:
        return None
    value = rows[0].get("STATUS_NO") or rows[0].get("status_no")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def get_type_by_no(type_no: int, db_id: Optional[str] = None, ci_type: int = 1) -> Optional[dict]:
    """Get equipment type by TYPE_NO for selected CI_TYPE."""
    db = get_db(db_id)
    query = """
        SELECT
            t.CI_TYPE,
            t.TYPE_NO,
            t.TYPE_NAME
        FROM CI_TYPES t
        WHERE t.CI_TYPE = ? AND t.TYPE_NO = ?
    """
    rows = db.execute_query(query, (ci_type, type_no))
    return rows[0] if rows else None


def get_models_by_type(type_no: int, db_id: Optional[str] = None, ci_type: int = 1) -> List[dict]:
    """Get model list by TYPE_NO for selected CI_TYPE."""
    db = get_db(db_id)
    query = """
        SELECT
            m.MODEL_NO as model_no,
            m.MODEL_NAME as model_name,
            m.TYPE_NO as type_no,
            m.CI_TYPE as ci_type
        FROM CI_MODELS m
        WHERE m.CI_TYPE = ? AND m.TYPE_NO = ?
        ORDER BY m.MODEL_NAME
    """
    return db.execute_query(query, (ci_type, type_no))


def get_model_no_by_name(model_name: str, ci_type: int = 1, strict: bool = True, db_id: Optional[str] = None) -> Optional[int]:
    """Get MODEL_NO by model name."""
    if not model_name:
        return None
    db = get_db(db_id)
    where_clause = "m.MODEL_NAME = ?" if strict else "m.MODEL_NAME LIKE ?"
    param = model_name if strict else f"%{model_name}%"
    query = f"""
        SELECT TOP 1 m.MODEL_NO
        FROM CI_MODELS m
        WHERE m.CI_TYPE = ? AND {where_clause}
        ORDER BY m.MODEL_NO
    """
    rows = db.execute_query(query, (ci_type, param))
    if not rows:
        return None
    value = rows[0].get("MODEL_NO") or rows[0].get("model_no")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def create_model(model_name: str, type_no: int, ci_type: int = 1, db_id: Optional[str] = None) -> Optional[int]:
    """Create model in CI_MODELS and return MODEL_NO."""
    if not model_name:
        return None
    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1 MODEL_NO
            FROM CI_MODELS
            WHERE CI_TYPE = ? AND MODEL_NAME = ?
            ORDER BY MODEL_NO
            """,
            (ci_type, model_name),
        )
        existing = cursor.fetchone()
        if existing and existing[0] is not None:
            return int(existing[0])

        cursor.execute("SELECT ISNULL(MAX(MODEL_NO), 0) + 1 FROM CI_MODELS")
        next_model_no = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO CI_MODELS (MODEL_NO, CI_TYPE, TYPE_NO, MODEL_NAME)
            VALUES (?, ?, ?, ?)
            """,
            (next_model_no, ci_type, type_no, model_name),
        )
        return int(next_model_no)


def get_model_by_no(model_no: int, db_id: Optional[str] = None, ci_type: int = 1) -> Optional[dict]:
    """Get model by MODEL_NO for selected CI_TYPE."""
    db = get_db(db_id)
    query = """
        SELECT
            m.CI_TYPE,
            m.TYPE_NO,
            m.MODEL_NO,
            m.MODEL_NAME
        FROM CI_MODELS m
        WHERE m.CI_TYPE = ? AND m.MODEL_NO = ?
    """
    rows = db.execute_query(query, (ci_type, model_no))
    return rows[0] if rows else None


def get_branch_by_no(branch_no: Any, db_id: Optional[str] = None) -> Optional[dict]:
    """Get branch by BRANCH_NO."""
    db = get_db(db_id)
    query = """
        SELECT
            b.BRANCH_NO,
            b.BRANCH_NAME
        FROM BRANCHES b
        WHERE b.BRANCH_NO = ?
    """
    rows = db.execute_query(query, (branch_no,))
    return rows[0] if rows else None


def get_location_by_no(loc_no: Any, db_id: Optional[str] = None) -> Optional[dict]:
    """Get location by LOC_NO."""
    db = get_db(db_id)
    query = """
        SELECT
            l.LOC_NO,
            l.DESCR as LOC_NAME
        FROM LOCATIONS l
        WHERE l.LOC_NO = ?
    """
    rows = db.execute_query(query, (loc_no,))
    return rows[0] if rows else None


def is_location_in_branch(loc_no: Any, branch_no: Any, db_id: Optional[str] = None) -> bool:
    """
    Check location-branch relation using ITEMS table mapping.
    Works for schemas where LOCATIONS has no BRANCH_NO column.
    """
    db = get_db(db_id)
    query = """
        SELECT TOP 1 1 as ok
        FROM ITEMS i
        WHERE i.BRANCH_NO = ?
          AND i.LOC_NO = ?
    """
    rows = db.execute_query(query, (branch_no, loc_no))
    return bool(rows)


def update_equipment_fields(
    inv_no: str,
    fields: dict,
    changed_by: str = "IT-WEB",
    db_id: Optional[str] = None,
) -> bool:
    """
    Update allowed fields for equipment card by inventory number.

    Allowed field keys:
        serial_no, hw_serial_no, part_no, ip_address, mac_address, network_name, description,
        status_no, empl_no, branch_no, loc_no,
        type_no, model_no
    """
    allowed_columns = {
        "serial_no": "SERIAL_NO",
        "hw_serial_no": "HW_SERIAL_NO",
        "part_no": "PART_NO",
        "ip_address": "IP_ADDRESS",
        "mac_address": "MAC_ADDRESS",
        "network_name": "NETBIOS_NAME",
        "description": "DESCR",
        "status_no": "STATUS_NO",
        "empl_no": "EMPL_NO",
        "branch_no": "BRANCH_NO",
        "loc_no": "LOC_NO",
        "type_no": "TYPE_NO",
        "model_no": "MODEL_NO",
    }

    set_clauses = []
    params = []
    for key, value in (fields or {}).items():
        column = allowed_columns.get(key)
        if not column:
            continue
        set_clauses.append(f"{column} = ?")
        params.append(value)

    if not set_clauses:
        return False

    db = get_db(db_id)

    try:
        inv_no_float = float(inv_no) if inv_no else None
    except (ValueError, TypeError):
        return False

    query = f"""
        UPDATE ITEMS
        SET {", ".join(set_clauses)},
            CH_DATE = GETDATE(),
            CH_USER = ?
        WHERE INV_NO = ?
    """
    params.append(changed_by or "IT-WEB")
    params.append(inv_no_float)
    affected = db.execute_update(query, tuple(params))
    return affected > 0


def get_owner_no_by_name(employee_name: str, strict: bool = True, db_id: Optional[str] = None) -> Optional[int]:
    """Get OWNER_NO by employee full name."""
    if not employee_name:
        return None
    db = get_db(db_id)
    where_clause = "o.OWNER_DISPLAY_NAME = ?" if strict else "o.OWNER_DISPLAY_NAME LIKE ?"
    param = employee_name if strict else f"%{employee_name}%"
    query = f"""
        SELECT TOP 1 o.OWNER_NO
        FROM OWNERS o
        WHERE {where_clause}
        ORDER BY o.OWNER_NO
    """
    rows = db.execute_query(query, (param,))
    if not rows:
        return None
    value = rows[0].get("OWNER_NO") or rows[0].get("owner_no")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_fio(full_name: str) -> tuple[str, str, str]:
    """Split FIO to last/first/middle name parts."""
    parts = (full_name or "").strip().split()
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    if len(parts) == 1:
        return parts[0], "", ""
    return "", "", ""


def create_owner(employee_name: str, department: Optional[str] = None, db_id: Optional[str] = None) -> Optional[int]:
    """Create owner in OWNERS and return OWNER_NO."""
    if not employee_name:
        return None
    db = get_db(db_id)
    lname, fname, mname = _parse_fio(employee_name)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ISNULL(MAX(OWNER_NO), 0) + 1 FROM OWNERS")
        next_owner_no = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO OWNERS (
                OWNER_NO, OWNER_LNAME, OWNER_FNAME, OWNER_MNAME,
                OWNER_DISPLAY_NAME, OWNER_DEPT
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (next_owner_no, lname, fname, mname, employee_name, department or ""),
        )
        return int(next_owner_no)


def get_owner_email_by_no(owner_no: int, db_id: Optional[str] = None) -> Optional[str]:
    """Get owner email by OWNER_NO."""
    db = get_db(db_id)
    query = """
        SELECT TOP 1 NULLIF(LTRIM(RTRIM(o.OWNER_EMAIL)), '') AS OWNER_EMAIL
        FROM OWNERS o
        WHERE o.OWNER_NO = ?
    """
    rows = db.execute_query(query, (owner_no,))
    if not rows:
        return None
    value = rows[0].get("OWNER_EMAIL") or rows[0].get("owner_email")
    if value is None:
        return None
    email = str(value).strip()
    return email or None


def create_equipment_item(
    serial_no: str,
    employee_name: str,
    branch_no: Any,
    loc_no: Any,
    type_no: int,
    status_no: int,
    model_name: Optional[str] = None,
    model_no: Optional[int] = None,
    employee_no: Optional[int] = None,
    employee_dept: Optional[str] = None,
    hw_serial_no: Optional[str] = None,
    part_no: Optional[str] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None,
    changed_by: str = "IT-WEB",
    db_id: Optional[str] = None,
) -> dict:
    """
    Create equipment record in ITEMS.
    Generates INV_NO automatically and creates OWNER/MODEL when needed.
    """
    result = {
        "success": False,
        "item_id": None,
        "inv_no": None,
        "created_owner": False,
        "created_model": False,
        "message": "",
    }

    normalized_serial = str(serial_no or "").strip()
    normalized_employee = str(employee_name or "").strip()
    normalized_model_name = str(model_name or "").strip()
    normalized_hw_serial = str(hw_serial_no or "").strip() or None
    normalized_part_no = str(part_no or "").strip() or None
    normalized_descr = str(description or "").strip() or None
    normalized_ip = str(ip_address or "").strip() or None

    if not normalized_serial:
        result["message"] = "serial_no is required"
        return result
    if not normalized_employee:
        result["message"] = "employee_name is required"
        return result

    resolved_type_no = int(type_no)
    resolved_status_no = int(status_no)
    resolved_model_no = int(model_no) if model_no is not None else None
    resolved_employee_no = int(employee_no) if employee_no is not None else None

    if resolved_model_no is None:
        if not normalized_model_name:
            result["message"] = "model_name is required when model_no is not provided"
            return result
        resolved_model_no = get_model_no_by_name(normalized_model_name, ci_type=1, strict=True, db_id=db_id)
        if resolved_model_no is None:
            resolved_model_no = get_model_no_by_name(normalized_model_name, ci_type=1, strict=False, db_id=db_id)
        if resolved_model_no is None:
            created = create_model(normalized_model_name, resolved_type_no, ci_type=1, db_id=db_id)
            if created is None:
                result["message"] = "Failed to resolve or create model"
                return result
            resolved_model_no = created
            result["created_model"] = True

    if resolved_employee_no is None:
        resolved_employee_no = get_owner_no_by_name(normalized_employee, strict=True, db_id=db_id)
        if resolved_employee_no is None:
            resolved_employee_no = get_owner_no_by_name(normalized_employee, strict=False, db_id=db_id)
        if resolved_employee_no is None:
            created_owner = create_owner(normalized_employee, department=employee_dept, db_id=db_id)
            if created_owner is None:
                result["message"] = "Failed to resolve or create employee"
                return result
            resolved_employee_no = created_owner
            result["created_owner"] = True

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT TOP 1 ID, INV_NO
            FROM ITEMS
            WHERE CI_TYPE = 1 AND SERIAL_NO = ?
            ORDER BY ID DESC
            """,
            (normalized_serial,),
        )
        existing = cursor.fetchone()
        if existing:
            result["item_id"] = int(existing[0]) if existing[0] is not None else None
            result["inv_no"] = str(existing[1]).strip() if existing[1] is not None else None
            result["message"] = f"Equipment with serial {normalized_serial} already exists"
            return result

        cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM ITEMS")
        next_id = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT ISNULL(MAX(CAST(INV_NO AS INT)), 0) + 1
            FROM ITEMS
            WHERE INV_NO IS NOT NULL AND ISNUMERIC(INV_NO) = 1
            """
        )
        next_inv_no = cursor.fetchone()[0]
        inv_no_value = str(next_inv_no)

        cursor.execute(
            """
            INSERT INTO ITEMS (
                ID, SERIAL_NO, HW_SERIAL_NO, PART_NO, INV_NO,
                CI_TYPE, TYPE_NO, MODEL_NO, STATUS_NO, EMPL_NO,
                BRANCH_NO, LOC_NO, QTY, COMP_NO, DESCR, IP_ADDRESS,
                CREATE_DATE, CH_DATE, CH_USER
            )
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, GETDATE(), GETDATE(), ?)
            """,
            (
                next_id,
                normalized_serial,
                normalized_hw_serial,
                normalized_part_no,
                inv_no_value,
                resolved_type_no,
                resolved_model_no,
                resolved_status_no,
                resolved_employee_no,
                branch_no,
                loc_no,
                normalized_descr,
                normalized_ip,
                changed_by or "IT-WEB",
            ),
        )

        result["success"] = True
        result["item_id"] = int(next_id)
        result["inv_no"] = inv_no_value
        result["message"] = "Equipment created successfully"
        return result


def create_consumable_item(
    branch_no: Any,
    loc_no: Any,
    type_no: int,
    qty: int,
    model_name: Optional[str] = None,
    model_no: Optional[int] = None,
    status_no: Optional[int] = None,
    part_no: Optional[str] = None,
    description: Optional[str] = None,
    changed_by: str = "IT-WEB",
    db_id: Optional[str] = None,
) -> dict:
    """
    Create consumable record in ITEMS (CI_TYPE=4).
    Creates missing model when needed.
    """
    result = {
        "success": False,
        "item_id": None,
        "inv_no": None,
        "created_model": False,
        "message": "",
    }

    normalized_model_name = str(model_name or "").strip()
    normalized_part_no = str(part_no or "").strip() or None
    normalized_descr = str(description or "").strip() or None

    try:
        resolved_qty = int(qty)
    except (TypeError, ValueError):
        result["message"] = "qty must be a positive integer"
        return result
    if resolved_qty <= 0:
        result["message"] = "qty must be a positive integer"
        return result

    resolved_type_no = int(type_no)
    resolved_model_no = int(model_no) if model_no is not None else None
    resolved_status_no = int(status_no) if status_no is not None else None
    if resolved_status_no is None:
        resolved_status_no = get_default_status_no(db_id)
    if resolved_status_no is None:
        result["message"] = "Unable to resolve default status"
        return result

    if resolved_model_no is None:
        if not normalized_model_name:
            result["message"] = "model_name is required when model_no is not provided"
            return result
        resolved_model_no = get_model_no_by_name(normalized_model_name, ci_type=4, strict=True, db_id=db_id)
        if resolved_model_no is None:
            resolved_model_no = get_model_no_by_name(normalized_model_name, ci_type=4, strict=False, db_id=db_id)
        if resolved_model_no is None:
            created = create_model(normalized_model_name, resolved_type_no, ci_type=4, db_id=db_id)
            if created is None:
                result["message"] = "Failed to resolve or create consumable model"
                return result
            resolved_model_no = created
            result["created_model"] = True

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM ITEMS")
        next_id = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT ISNULL(MAX(CAST(INV_NO AS INT)), 0) + 1
            FROM ITEMS
            WHERE INV_NO IS NOT NULL AND ISNUMERIC(INV_NO) = 1
            """
        )
        next_inv_no = cursor.fetchone()[0]
        inv_no_value = str(next_inv_no)

        cursor.execute(
            """
            INSERT INTO ITEMS (
                ID, SERIAL_NO, HW_SERIAL_NO, PART_NO, INV_NO,
                CI_TYPE, TYPE_NO, MODEL_NO, STATUS_NO, EMPL_NO,
                BRANCH_NO, LOC_NO, QTY, COMP_NO, DESCR, IP_ADDRESS,
                CREATE_DATE, CH_DATE, CH_USER
            )
            VALUES (?, NULL, NULL, ?, ?, 4, ?, ?, ?, NULL, ?, ?, ?, 0, ?, NULL, GETDATE(), GETDATE(), ?)
            """,
            (
                next_id,
                normalized_part_no,
                inv_no_value,
                resolved_type_no,
                resolved_model_no,
                resolved_status_no,
                branch_no,
                loc_no,
                resolved_qty,
                normalized_descr,
                changed_by or "IT-WEB",
            ),
        )

        result["success"] = True
        result["item_id"] = int(next_id)
        result["inv_no"] = inv_no_value
        result["message"] = "Consumable created successfully"
        return result


def get_consumables_lookup(
    db_id: Optional[str] = None,
    *,
    type_no: Optional[int] = None,
    model_name: Optional[str] = None,
    branch_no: Optional[Any] = None,
    loc_no: Optional[Any] = None,
    only_positive_qty: bool = True,
    limit: int = 300,
) -> List[Dict[str, Any]]:
    """Lookup consumables (CI_TYPE=4) with branch/location for work operations."""
    db = get_db(db_id)
    safe_limit = max(1, min(int(limit or 300), 1000))

    conditions = ["i.CI_TYPE = 4"]
    params: List[Any] = []

    if only_positive_qty:
        conditions.append("ISNULL(i.QTY, 0) > 0")
    if type_no is not None:
        conditions.append("i.TYPE_NO = ?")
        params.append(int(type_no))
    if model_name:
        conditions.append("LOWER(CAST(m.MODEL_NAME AS NVARCHAR(255))) LIKE ?")
        params.append(f"%{str(model_name).strip().lower()}%")
    if branch_no not in (None, ""):
        conditions.append("i.BRANCH_NO = ?")
        params.append(branch_no)
    if loc_no not in (None, ""):
        conditions.append("i.LOC_NO = ?")
        params.append(loc_no)

    query = f"""
        SELECT TOP {safe_limit}
            i.ID as id,
            i.INV_NO as inv_no,
            i.TYPE_NO as type_no,
            i.MODEL_NO as model_no,
            ISNULL(i.QTY, 0) as qty,
            i.PART_NO as part_no,
            i.DESCR as description,
            t.TYPE_NAME as type_name,
            m.MODEL_NAME as model_name,
            b.BRANCH_NO as branch_no,
            b.BRANCH_NAME as branch_name,
            l.LOC_NO as loc_no,
            l.DESCR as location_name
        FROM ITEMS i
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
        LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
        WHERE {" AND ".join(conditions)}
        ORDER BY m.MODEL_NAME, b.BRANCH_NAME, l.DESCR, i.ID
    """
    return db.execute_query(query, tuple(params))


def consume_consumable_stock(
    *,
    db_id: Optional[str] = None,
    item_id: Optional[int] = None,
    inv_no: Optional[str] = None,
    qty: int = 1,
    changed_by: str = "IT-WEB",
) -> Dict[str, Any]:
    """Decrease consumable stock by qty with underflow protection."""
    result: Dict[str, Any] = {
        "success": False,
        "item_id": None,
        "inv_no": None,
        "qty_old": None,
        "qty_new": None,
        "message": "",
    }

    try:
        resolved_qty = int(qty)
    except (TypeError, ValueError):
        result["message"] = "qty must be a positive integer"
        return result
    if resolved_qty <= 0:
        result["message"] = "qty must be a positive integer"
        return result

    if item_id is None and not str(inv_no or "").strip():
        result["message"] = "item_id or inv_no is required"
        return result

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()

        if item_id is not None:
            cursor.execute(
                """
                SELECT TOP 1 i.ID, i.INV_NO, ISNULL(i.QTY, 0) AS QTY
                FROM ITEMS i
                WHERE i.CI_TYPE = 4 AND i.ID = ?
                """,
                (int(item_id),),
            )
        else:
            try:
                inv_no_float = float(str(inv_no).strip())
            except (TypeError, ValueError):
                result["message"] = "Invalid inv_no"
                return result
            cursor.execute(
                """
                SELECT TOP 1 i.ID, i.INV_NO, ISNULL(i.QTY, 0) AS QTY
                FROM ITEMS i
                WHERE i.CI_TYPE = 4 AND i.INV_NO = ?
                ORDER BY i.ID DESC
                """,
                (inv_no_float,),
            )

        row = cursor.fetchone()
        if not row:
            result["message"] = "Consumable not found"
            return result

        target_id = int(row[0])
        target_inv_no = str(row[1]).strip() if row[1] is not None else None
        qty_old = int(row[2]) if row[2] is not None else 0
        if qty_old < resolved_qty:
            result["item_id"] = target_id
            result["inv_no"] = target_inv_no
            result["qty_old"] = qty_old
            result["qty_new"] = qty_old
            result["message"] = "Insufficient consumable quantity"
            return result

        cursor.execute(
            """
            UPDATE ITEMS
            SET QTY = ISNULL(QTY, 0) - ?,
                CH_DATE = GETDATE(),
                CH_USER = ?
            WHERE ID = ?
              AND CI_TYPE = 4
              AND ISNULL(QTY, 0) >= ?
            """,
            (resolved_qty, changed_by or "IT-WEB", target_id, resolved_qty),
        )
        if cursor.rowcount <= 0:
            result["item_id"] = target_id
            result["inv_no"] = target_inv_no
            result["qty_old"] = qty_old
            result["qty_new"] = qty_old
            result["message"] = "Insufficient consumable quantity"
            return result

        cursor.execute("SELECT ISNULL(QTY, 0) FROM ITEMS WHERE ID = ?", (target_id,))
        next_row = cursor.fetchone()
        qty_new = int(next_row[0]) if next_row and next_row[0] is not None else max(qty_old - resolved_qty, 0)

        result["success"] = True
        result["item_id"] = target_id
        result["inv_no"] = target_inv_no
        result["qty_old"] = qty_old
        result["qty_new"] = qty_new
        result["message"] = "Consumable stock updated"
        return result


def set_consumable_stock_qty(
    *,
    db_id: Optional[str] = None,
    item_id: Optional[int] = None,
    inv_no: Optional[str] = None,
    qty: int = 0,
    changed_by: str = "IT-WEB",
) -> Dict[str, Any]:
    """Set exact consumable stock quantity (CI_TYPE=4)."""
    result: Dict[str, Any] = {
        "success": False,
        "item_id": None,
        "inv_no": None,
        "qty_old": None,
        "qty_new": None,
        "message": "",
    }

    try:
        resolved_qty = int(qty)
    except (TypeError, ValueError):
        result["message"] = "qty must be a non-negative integer"
        return result
    if resolved_qty < 0:
        result["message"] = "qty must be a non-negative integer"
        return result

    if item_id is None and not str(inv_no or "").strip():
        result["message"] = "item_id or inv_no is required"
        return result

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()

        if item_id is not None:
            cursor.execute(
                """
                SELECT TOP 1 i.ID, i.INV_NO, ISNULL(i.QTY, 0) AS QTY
                FROM ITEMS i
                WHERE i.CI_TYPE = 4 AND i.ID = ?
                """,
                (int(item_id),),
            )
        else:
            try:
                inv_no_float = float(str(inv_no).strip())
            except (TypeError, ValueError):
                result["message"] = "Invalid inv_no"
                return result
            cursor.execute(
                """
                SELECT TOP 1 i.ID, i.INV_NO, ISNULL(i.QTY, 0) AS QTY
                FROM ITEMS i
                WHERE i.CI_TYPE = 4 AND i.INV_NO = ?
                ORDER BY i.ID DESC
                """,
                (inv_no_float,),
            )

        row = cursor.fetchone()
        if not row:
            result["message"] = "Consumable not found"
            return result

        target_id = int(row[0])
        target_inv_no = str(row[1]).strip() if row[1] is not None else None
        qty_old = int(row[2]) if row[2] is not None else 0

        cursor.execute(
            """
            UPDATE ITEMS
            SET QTY = ?,
                CH_DATE = GETDATE(),
                CH_USER = ?
            WHERE ID = ?
              AND CI_TYPE = 4
            """,
            (resolved_qty, changed_by or "IT-WEB", target_id),
        )
        if cursor.rowcount <= 0:
            result["item_id"] = target_id
            result["inv_no"] = target_inv_no
            result["qty_old"] = qty_old
            result["qty_new"] = qty_old
            result["message"] = "Failed to update consumable quantity"
            return result

        result["success"] = True
        result["item_id"] = target_id
        result["inv_no"] = target_inv_no
        result["qty_old"] = qty_old
        result["qty_new"] = resolved_qty
        result["message"] = "Consumable quantity updated"
        return result


def transfer_equipment_by_inv_with_history(
    inv_no: str,
    new_employee_no: int,
    new_employee_name: str,
    new_branch_no: Optional[Any] = None,
    new_loc_no: Optional[Any] = None,
    changed_by: str = "IT-WEB",
    comment: Optional[str] = None,
    db_id: Optional[str] = None,
) -> dict:
    """
    Transfer one equipment unit by INV_NO and write CI_HISTORY.

    Returns:
        Dict with operation status and transferred item metadata.
    """
    result = {
        "success": False,
        "inv_no": str(inv_no or "").strip(),
        "message": "",
        "hist_id": None,
    }

    try:
        inv_no_float = float(inv_no) if inv_no not in (None, "") else None
    except (TypeError, ValueError):
        result["message"] = "Invalid inventory number"
        return result

    db = get_db(db_id)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1
                i.ID, i.INV_NO, i.SERIAL_NO, i.HW_SERIAL_NO, i.PART_NO,
                i.EMPL_NO, i.BRANCH_NO, i.LOC_NO, i.STATUS_NO,
                i.TYPE_NO, i.MODEL_NO, i.CI_TYPE, i.QTY,
                o.OWNER_DISPLAY_NAME AS OLD_EMPLOYEE_NAME,
                b.BRANCH_NAME AS BRANCH_NAME,
                l.DESCR AS LOCATION_NAME,
                t.TYPE_NAME AS TYPE_NAME,
                m.MODEL_NAME AS MODEL_NAME
            FROM ITEMS i
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
            LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
            WHERE i.CI_TYPE = 1 AND i.INV_NO = ?
            """,
            (inv_no_float,),
        )
        row = cursor.fetchone()
        if not row:
            result["message"] = f"Equipment with INV_NO {inv_no} not found"
            return result

        columns = [column[0] for column in cursor.description]
        current = dict(zip(columns, row))

        old_empl_no = current.get("EMPL_NO")
        old_branch_no = current.get("BRANCH_NO")
        old_loc_no = current.get("LOC_NO")
        old_status_no = current.get("STATUS_NO")
        old_serial_no = current.get("SERIAL_NO")
        old_inv_no = current.get("INV_NO")
        old_type_no = current.get("TYPE_NO")
        old_model_no = current.get("MODEL_NO")
        old_ci_type = current.get("CI_TYPE")
        old_qty = current.get("QTY") if current.get("QTY") is not None else 1

        final_branch_no = new_branch_no if new_branch_no is not None else old_branch_no
        final_loc_no = new_loc_no if new_loc_no is not None else old_loc_no
        new_qty = 1
        now = datetime.now()

        cursor.execute("SELECT ISNULL(MAX(HIST_ID), 0) + 1 FROM CI_HISTORY")
        hist_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO CI_HISTORY (
                HIST_ID,
                ITEM_ID,
                EMPL_NO_OLD, EMPL_NO_NEW,
                BRANCH_NO_OLD, BRANCH_NO_NEW,
                LOC_NO_OLD, LOC_NO_NEW,
                STATUS_NO_OLD, STATUS_NO_NEW,
                SERIAL_NO_OLD, SERIAL_NO_NEW,
                INV_NO_OLD, INV_NO_NEW,
                TYPE_NO_OLD, TYPE_NO_NEW,
                MODEL_NO_OLD, MODEL_NO_NEW,
                CI_TYPE_OLD, CI_TYPE_NEW,
                COMP_NO_OLD, COMP_NO_NEW,
                QTY_OLD, QTY_NEW,
                CH_DATE, CH_USER, CH_COMMENT
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hist_id,
                current.get("ID"),
                old_empl_no, new_employee_no,
                old_branch_no, final_branch_no,
                old_loc_no, final_loc_no,
                old_status_no, old_status_no,
                old_serial_no, old_serial_no,
                old_inv_no, old_inv_no,
                old_type_no, old_type_no,
                old_model_no, old_model_no,
                old_ci_type, old_ci_type,
                0, 0,
                old_qty, new_qty,
                now, changed_by or "IT-WEB", comment,
            ),
        )

        cursor.execute(
            """
            UPDATE ITEMS
            SET EMPL_NO = ?,
                BRANCH_NO = ?,
                LOC_NO = ?,
                QTY = ?,
                CH_DATE = ?,
                CH_USER = ?
            WHERE ID = ?
            """,
            (
                new_employee_no,
                final_branch_no,
                final_loc_no,
                new_qty,
                now,
                changed_by or "IT-WEB",
                current.get("ID"),
            ),
        )

        branch_name = current.get("BRANCH_NAME")
        location_name = current.get("LOCATION_NAME")

        if final_branch_no is not None:
            cursor.execute("SELECT TOP 1 BRANCH_NAME FROM BRANCHES WHERE BRANCH_NO = ?", (final_branch_no,))
            branch_row = cursor.fetchone()
            if branch_row and branch_row[0] is not None:
                branch_name = branch_row[0]

        if final_loc_no is not None:
            cursor.execute("SELECT TOP 1 DESCR FROM LOCATIONS WHERE LOC_NO = ?", (final_loc_no,))
            loc_row = cursor.fetchone()
            if loc_row and loc_row[0] is not None:
                location_name = loc_row[0]

        try:
            inv_text = str(int(round(float(old_inv_no)))) if old_inv_no is not None else str(inv_no)
        except (TypeError, ValueError):
            inv_text = str(inv_no)

        result.update(
            {
                "success": True,
                "hist_id": int(hist_id),
                "inv_no": inv_text,
                "serial_no": old_serial_no,
                "old_employee_no": old_empl_no,
                "old_employee_name": current.get("OLD_EMPLOYEE_NAME"),
                "new_employee_no": int(new_employee_no),
                "new_employee_name": new_employee_name,
                "branch_no": final_branch_no,
                "loc_no": final_loc_no,
                "branch_name": branch_name,
                "location_name": location_name,
                "type_name": current.get("TYPE_NAME"),
                "model_name": current.get("MODEL_NAME"),
                "part_no": current.get("PART_NO"),
                "message": "Transferred",
            }
        )
        return result


def _normalize_mac_for_lookup(value: Optional[str]) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", str(value or "")).upper()


def resolve_pc_context_by_mac_or_hostname(
    mac_address: Optional[str],
    hostname: Optional[str],
    db_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Resolve branch and owner context for a PC from SQL inventory.

    Priority:
    1. Exact MAC match (normalized)
    2. Exact hostname/netbios match (case-insensitive)
    """
    db = get_db(db_id)
    normalized_mac = _normalize_mac_for_lookup(mac_address)
    normalized_hostname = str(hostname or "").strip()

    if normalized_mac:
        query_mac = """
            SELECT TOP 1
                i.INV_NO as inv_no,
                i.MAC_ADDRESS as mac_address,
                i.NETBIOS_NAME as network_name,
                i.IP_ADDRESS as ip_address,
                i.BRANCH_NO as branch_no,
                i.LOC_NO as loc_no,
                b.BRANCH_NAME as branch_name,
                l.DESCR as location_name,
                i.EMPL_NO as empl_no,
                o.OWNER_DISPLAY_NAME as employee_name
            FROM ITEMS i
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            WHERE i.CI_TYPE = 1
              AND UPPER(REPLACE(REPLACE(COALESCE(i.MAC_ADDRESS, ''), ':', ''), '-', '')) = ?
            ORDER BY i.ID DESC
        """
        try:
            rows = db.execute_query(query_mac, (normalized_mac,))
            if rows:
                return rows[0]
        except Exception:
            # Some legacy snapshots may have schema differences; hostname fallback below.
            pass

    if normalized_hostname:
        candidates: List[str] = [normalized_hostname]
        short_name = normalized_hostname.split(".")[0].strip()
        if short_name and short_name.upper() != normalized_hostname.upper():
            candidates.append(short_name)

        query_host = """
            SELECT TOP 1
                i.INV_NO as inv_no,
                i.MAC_ADDRESS as mac_address,
                i.NETBIOS_NAME as network_name,
                i.IP_ADDRESS as ip_address,
                i.BRANCH_NO as branch_no,
                i.LOC_NO as loc_no,
                b.BRANCH_NAME as branch_name,
                l.DESCR as location_name,
                i.EMPL_NO as empl_no,
                o.OWNER_DISPLAY_NAME as employee_name
            FROM ITEMS i
            LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
            LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
            WHERE i.CI_TYPE = 1
              AND (
                    UPPER(COALESCE(i.NETBIOS_NAME, '')) = UPPER(?)
                 OR UPPER(COALESCE(i.DOMAIN_NAME, '')) = UPPER(?)
              )
            ORDER BY i.ID DESC
        """
        for candidate in candidates:
            try:
                rows = db.execute_query(query_host, (candidate, candidate))
                if rows:
                    return rows[0]
            except Exception:
                continue

    return None

