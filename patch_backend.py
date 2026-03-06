import pathlib
import sys

p1 = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\backend\api\v1\networks.py')
c1 = p1.read_text(encoding='utf-8')
old1 = """    is_uniform = payload.panels is None or len(payload.panels) == 0

    if is_uniform:
        # Uniform mode: validate panel_count and ports_per_panel
        if payload.panel_count is None or payload.ports_per_panel is None:
            raise HTTPException(
                status_code=400,
                detail="panel_count and ports_per_panel required for uniform mode"
            )"""
new1 = """    is_uniform = payload.panels is None or len(payload.panels) == 0

    if is_uniform and (payload.panel_count is not None or payload.ports_per_panel is not None):
        if payload.panel_count is None or payload.ports_per_panel is None:
            raise HTTPException(
                status_code=400,
                detail="Both panel_count and ports_per_panel required for uniform mode if provided"
            )"""
c1 = c1.replace(old1, new1)
p1.write_text(c1, encoding='utf-8')


p2 = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\backend\services\network_service.py')
c2 = p2.read_text(encoding='utf-8')

old2 = """        # Determine mode: uniform or heterogeneous
        is_uniform = panels is None or len(panels) == 0

        if is_uniform:
            # Uniform mode: validate panel_count and ports_per_panel
            if panel_count is None or ports_per_panel is None:
                raise ValueError("panel_count and ports_per_panel required for uniform mode")
            if int(panel_count) <= 0 or int(ports_per_panel) <= 0:
                raise ValueError("panel_count and ports_per_panel must be positive")
        else:
            # Heterogeneous mode: validate panels
            if not panels or len(panels) == 0:
                raise ValueError("panels list cannot be empty for heterogeneous mode")
            for panel in panels:
                panel_index = int(panel.get("panel_index", 0))
                port_count = int(panel.get("port_count", 0))
                if panel_index <= 0 or port_count <= 0:
                    raise ValueError("panel_index and port_count must be positive")

            # Set profile to total panel count and max ports per panel for backward compat
            panel_count = len(panels)
            ports_per_panel = max((int(p.get("port_count", 0)) for p in panels), default=1)"""

new2 = """        has_profile = False
        is_uniform = panels is None or len(panels) == 0

        if is_uniform:
            if panel_count is not None and ports_per_panel is not None and int(panel_count) > 0 and int(ports_per_panel) > 0:
                has_profile = True
        else:
            if not panels or len(panels) == 0:
                raise ValueError("panels list cannot be empty for heterogeneous mode")
            for panel in panels:
                panel_index = int(panel.get("panel_index", 0))
                port_count = int(panel.get("port_count", 0))
                if panel_index <= 0 or port_count <= 0:
                    raise ValueError("panel_index and port_count must be positive")

            panel_count = len(panels)
            ports_per_panel = max((int(p.get("port_count", 0)) for p in panels), default=1)
            has_profile = True"""
c2 = c2.replace(old2, new2)

old3 = """            profile_result = self._upsert_socket_profile_in_conn(
                conn,
                branch_id=branch_id,
                panel_count=int(panel_count) if isinstance(panel_count, (str, int)) else 0,
                ports_per_panel=int(ports_per_panel) if isinstance(ports_per_panel, (str, int)) else 0,
                panels=panels,
            )
            bootstrap_result = self._bootstrap_sockets_for_branch_in_conn(conn, branch_id=branch_id)"""

new3 = """            if has_profile:
                profile_result = self._upsert_socket_profile_in_conn(
                    conn,
                    branch_id=branch_id,
                    panel_count=int(panel_count) if isinstance(panel_count, (str, int)) else 0,
                    ports_per_panel=int(ports_per_panel) if isinstance(ports_per_panel, (str, int)) else 0,
                    panels=panels,
                )
                bootstrap_result = self._bootstrap_sockets_for_branch_in_conn(conn, branch_id=branch_id)
            else:
                profile_result, bootstrap_result = None, None"""
c2 = c2.replace(old3, new3)
p2.write_text(c2, encoding='utf-8')
