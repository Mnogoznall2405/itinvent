"""
Correct SQL queries matching actual ITINVENT database schema.
Based on universal_database.py
"""

# Get all equipment with all fields, grouped by branch and location
QUERY_GET_ALL_EQUIPMENT = """
    SELECT
        i.ID,
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        i.PART_NO,
        i.DESCR as description,
        i.IP_ADDRESS,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as vendor_name,
        s.DESCR as status,
        o.OWNER_NO as empl_no,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        b.BRANCH_NO as branch_no,
        b.BRANCH_NAME as branch_name,
        l.LOC_NO as loc_no,
        l.DESCR as location
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1
    ORDER BY b.BRANCH_NAME, l.DESCR, i.INV_NO
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_COUNT_ALL_EQUIPMENT = """
    SELECT COUNT(*) as total
    FROM ITEMS i
    WHERE i.CI_TYPE = 1
"""

QUERY_COUNT_ALL_CONSUMABLES = """
    SELECT COUNT(*) as total
    FROM ITEMS i
    WHERE i.CI_TYPE = 4
"""

QUERY_GET_ALL_BRANCHES = """
    SELECT DISTINCT
        b.BRANCH_NO,
        b.BRANCH_NAME
    FROM BRANCHES b
    WHERE b.BRANCH_NAME IS NOT NULL
    ORDER BY b.BRANCH_NAME
"""

QUERY_GET_LOCATIONS_BY_BRANCH = """
    SELECT DISTINCT
        i.LOC_NO as LOC_NO,
        l.DESCR as LOC_NAME
    FROM ITEMS i
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1
      AND i.BRANCH_NO = ?
      AND i.LOC_NO IS NOT NULL
    ORDER BY l.DESCR
"""

# Get equipment grouped by branch and location
QUERY_GET_EQUIPMENT_GROUPED = """
    SELECT
        i.ID,
        i.TYPE_NO as type_no,
        i.MODEL_NO as model_no,
        i.STATUS_NO as status_no,
        i.EMPL_NO as empl_no,
        i.BRANCH_NO as branch_no,
        i.LOC_NO as loc_no,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location,
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        i.PART_NO as part_no,
        i.QTY as qty,
        i.IP_ADDRESS as ip_address,
        i.MAC_ADDRESS as mac_address,
        i.NETBIOS_NAME as network_name,
        i.DOMAIN_NAME as domain_name,
        i.DESCR as DESCRIPTION,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as manufacturer,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        s.DESCR as status
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1
    ORDER BY b.BRANCH_NAME, l.DESCR, i.INV_NO
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

# Same query without pagination — use when you need ALL equipment in one shot
QUERY_GET_EQUIPMENT_GROUPED_ALL = """
    SELECT
        i.ID,
        i.TYPE_NO as type_no,
        i.MODEL_NO as model_no,
        i.STATUS_NO as status_no,
        i.EMPL_NO as empl_no,
        i.BRANCH_NO as branch_no,
        i.LOC_NO as loc_no,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location,
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        i.PART_NO as part_no,
        i.QTY as qty,
        i.IP_ADDRESS as ip_address,
        i.MAC_ADDRESS as mac_address,
        i.NETBIOS_NAME as network_name,
        i.DOMAIN_NAME as domain_name,
        i.DESCR as DESCRIPTION,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as manufacturer,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        s.DESCR as status
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1
    ORDER BY b.BRANCH_NAME, l.DESCR, i.INV_NO
"""

# Get consumables grouped by branch and location (CI_TYPE = 4)
QUERY_GET_CONSUMABLES_GROUPED = """
    SELECT
        i.ID,
        i.TYPE_NO as type_no,
        i.MODEL_NO as model_no,
        i.STATUS_NO as status_no,
        i.EMPL_NO as empl_no,
        i.BRANCH_NO as branch_no,
        i.LOC_NO as loc_no,
        b.BRANCH_NAME as branch_name,
        l.DESCR as location,
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        i.PART_NO as part_no,
        i.QTY as qty,
        i.IP_ADDRESS as ip_address,
        i.MAC_ADDRESS as mac_address,
        i.NETBIOS_NAME as network_name,
        i.DOMAIN_NAME as domain_name,
        i.DESCR as DESCRIPTION,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as manufacturer,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        s.DESCR as status
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 4
    ORDER BY b.BRANCH_NAME, l.DESCR, i.INV_NO
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_GET_EQUIPMENT_BY_BRANCH = """
    SELECT
        i.ID,
        i.INV_NO,
        i.SERIAL_NO,
        i.HW_SERIAL_NO,
        i.PART_NO,
        i.DESCR as description,
        i.IP_ADDRESS,
        t.TYPE_NAME as type_name,
        m.MODEL_NAME as model_name,
        v.VENDOR_NAME as vendor_name,
        s.DESCR as status,
        o.OWNER_NO as empl_no,
        o.OWNER_DISPLAY_NAME as employee_name,
        o.OWNER_DEPT as employee_dept,
        b.BRANCH_NO as branch_no,
        b.BRANCH_NAME as branch_name,
        l.LOC_NO as loc_no,
        l.DESCR as location
    FROM ITEMS i
    LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
    LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
    LEFT JOIN VENDORS v ON m.VENDOR_NO = v.VENDOR_NO
    LEFT JOIN STATUS s ON i.STATUS_NO = s.STATUS_NO
    LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    LEFT JOIN LOCATIONS l ON i.LOC_NO = l.LOC_NO
    WHERE i.CI_TYPE = 1 AND b.BRANCH_NAME = ?
    ORDER BY l.DESCR, i.INV_NO
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_COUNT_BY_BRANCH = """
    SELECT COUNT(*) as total
    FROM ITEMS i
    LEFT JOIN BRANCHES b ON i.BRANCH_NO = b.BRANCH_NO
    WHERE i.CI_TYPE = 1 AND b.BRANCH_NAME = ?
"""

QUERY_GET_ALL_EQUIPMENT_TYPES = """
    SELECT
        t.CI_TYPE,
        t.TYPE_NO,
        t.TYPE_NAME
    FROM CI_TYPES t
    WHERE t.CI_TYPE IS NOT NULL AND t.TYPE_NO IS NOT NULL
    ORDER BY t.TYPE_NAME
"""
