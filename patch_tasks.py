import pathlib

# ── 1. hub_service.py ──
p = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\backend\services\hub_service.py')
c = p.read_text(encoding='utf-8')

# 1a. Add priority column to _ensure_schema
c = c.replace(
    """                    review_comment TEXT NULL
                );""",
    """                    review_comment TEXT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal'
                );"""
)

# 1b. After _ensure_task_controller_columns, add priority column migration
c = c.replace(
    """            self._ensure_task_controller_columns(conn)
            conn.commit()""",
    """            self._ensure_task_controller_columns(conn)
            self._ensure_task_priority_column(conn)
            self._ensure_task_comments_table(conn)
            conn.commit()"""
)

# 1c. Add the _ensure_task_priority_column and _ensure_task_comments_table methods
# Insert them right after _backfill_task_controllers method (before _ensure_schema)
c = c.replace(
    """    def _ensure_schema(self) -> None:""",
    """    def _ensure_task_priority_column(self, conn: sqlite3.Connection) -> None:
        cols = self._table_columns(conn, self._TASKS_TABLE)
        if "priority" not in cols:
            conn.execute(f"ALTER TABLE {self._TASKS_TABLE} ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")

    _TASK_COMMENTS_TABLE = "hub_task_comments"

    def _ensure_task_comments_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(f\"\"\"
            CREATE TABLE IF NOT EXISTS {self._TASK_COMMENTS_TABLE} (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        \"\"\")
        conn.execute(f\"\"\"
            CREATE INDEX IF NOT EXISTS idx_{self._TASK_COMMENTS_TABLE}_task
                ON {self._TASK_COMMENTS_TABLE}(task_id, created_at ASC)
        \"\"\")

    def _ensure_task_status_log_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS hub_task_status_log (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                old_status TEXT NOT NULL DEFAULT '',
                new_status TEXT NOT NULL DEFAULT '',
                changed_by_user_id INTEGER NOT NULL,
                changed_by_username TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL
            )
        \"\"\")
        conn.execute(\"\"\"
            CREATE INDEX IF NOT EXISTS idx_hub_task_status_log_task
                ON hub_task_status_log(task_id, changed_at ASC)
        \"\"\")

    def _log_status_change(self, conn: sqlite3.Connection, *, task_id: str, old_status: str, new_status: str, user_id: int, username: str) -> None:
        import uuid as _uuid
        now_iso = _utc_now_iso()
        conn.execute(
            "INSERT INTO hub_task_status_log (id, task_id, old_status, new_status, changed_by_user_id, changed_by_username, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), task_id, old_status, new_status, user_id, username, now_iso),
        )

    def list_task_comments(self, task_id: str) -> list[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self._TASK_COMMENTS_TABLE} WHERE task_id = ? ORDER BY created_at ASC",
                (normalized_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_task_comment(self, *, task_id: str, user: dict[str, Any], body: str) -> Optional[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        body_text = _normalize_text(body)
        if not normalized_id or not body_text:
            return None
        user_id = self._as_int(user.get("id"))
        now_iso = _utc_now_iso()
        comment_id = str(uuid.uuid4())
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT id FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                f"INSERT INTO {self._TASK_COMMENTS_TABLE} (id, task_id, user_id, username, full_name, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (comment_id, normalized_id, user_id, _normalize_text(user.get("username")), _normalize_text(user.get("full_name")), body_text, now_iso),
            )
            conn.execute(f"UPDATE {self._TASKS_TABLE} SET updated_at = ? WHERE id = ?", (now_iso, normalized_id))
            conn.commit()
            created = conn.execute(f"SELECT * FROM {self._TASK_COMMENTS_TABLE} WHERE id = ?", (comment_id,)).fetchone()
            return dict(created) if created else None

    def list_task_status_log(self, task_id: str) -> list[dict[str, Any]]:
        normalized_id = _normalize_text(task_id)
        if not normalized_id:
            return []
        with self._lock, self._connect() as conn:
            self._ensure_task_status_log_table(conn)
            rows = conn.execute(
                "SELECT * FROM hub_task_status_log WHERE task_id = ? ORDER BY changed_at ASC",
                (normalized_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_schema(self) -> None:"""
)

# 1d. Update create_task to include priority
c = c.replace(
    """                INSERT INTO {self._TASKS_TABLE}
                (id, title, description, status, due_at, assignee_user_id, assignee_username, assignee_full_name,
                 controller_user_id, controller_username, controller_full_name,
                 created_by_user_id, created_by_username, created_by_full_name, created_at, updated_at)
                VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    """                INSERT INTO {self._TASKS_TABLE}
                (id, title, description, status, due_at, priority, assignee_user_id, assignee_username, assignee_full_name,
                 controller_user_id, controller_username, controller_full_name,
                 created_by_user_id, created_by_username, created_by_full_name, created_at, updated_at)
                VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
)

# 1e. Add priority param to the INSERT values
c = c.replace(
    """                (
                    task_id,
                    title_text,
                    _normalize_text(description),
                    _normalize_text(due_at) or None,
                    self._as_int(assignee.get("id")),""",
    """                (
                    task_id,
                    title_text,
                    _normalize_text(description),
                    _normalize_text(due_at) or None,
                    _normalize_text(priority) if priority else "normal",
                    self._as_int(assignee.get("id")),"""
)

# 1f. Add priority parameter to create_task signature
c = c.replace(
    """    def create_task(
        self,
        *,
        title: str,
        description: str,
        assignee_user_id: int,
        controller_user_id: int,
        due_at: Optional[str],
        actor: dict[str, Any],
    ) -> dict[str, Any]:""",
    """    def create_task(
        self,
        *,
        title: str,
        description: str,
        assignee_user_id: int,
        controller_user_id: int,
        due_at: Optional[str],
        priority: Optional[str] = "normal",
        actor: dict[str, Any],
    ) -> dict[str, Any]:"""
)

# 1g. Add priority to update_task allowed fields
c = c.replace(
    """        for key in ("title", "description", "due_at", "assignee_user_id", "controller_user_id"):""",
    """        for key in ("title", "description", "due_at", "priority", "assignee_user_id", "controller_user_id"):"""
)

# Also handle priority in update_task body — add priority validation block
c = c.replace(
    """            elif key == "due_at":
                updates.append("due_at = ?")
                params.append(_normalize_text(payload.get(key)) or None)
            else:
                value = _normalize_text(payload.get(key))
                if key == "title" and len(value) < 3:
                    raise ValueError("Task title must contain at least 3 characters")
                updates.append(f"{key} = ?")
                params.append(value)""",
    """            elif key == "due_at":
                updates.append("due_at = ?")
                params.append(_normalize_text(payload.get(key)) or None)
            elif key == "priority":
                pval = _normalize_text(payload.get(key), "normal").lower()
                if pval not in {"low", "normal", "high", "urgent"}:
                    pval = "normal"
                updates.append("priority = ?")
                params.append(pval)
            else:
                value = _normalize_text(payload.get(key))
                if key == "title" and len(value) < 3:
                    raise ValueError("Task title must contain at least 3 characters")
                updates.append(f"{key} = ?")
                params.append(value)"""
)

# 1h. Allow admin to delete tasks — change delete_task
c = c.replace(
    """    def delete_task(self, *, task_id: str, actor_user_id: int) -> bool:""",
    """    def delete_task(self, *, task_id: str, actor_user_id: int, is_admin: bool = False) -> bool:"""
)
c = c.replace(
    """            if self._as_int(row["created_by_user_id"]) != actor_id:
                raise PermissionError("Only task creator can delete it")""",
    """            if not is_admin and self._as_int(row["created_by_user_id"]) != actor_id:
                raise PermissionError("Only task creator or admin can delete it")"""
)

# Also delete comments when deleting a task
c = c.replace(
    """            conn.execute(f"DELETE FROM {self._TASK_ATTACH_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASK_REPORTS_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,))""",
    """            conn.execute(f"DELETE FROM {self._TASK_ATTACH_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASK_REPORTS_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASK_COMMENTS_TABLE} WHERE task_id = ?", (normalized_id,))
            conn.execute("DELETE FROM hub_task_status_log WHERE task_id = ?", (normalized_id,))
            conn.execute(f"DELETE FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,))"""
)

# 1i. Log status changes in start_task
c = c.replace(
    """            conn.execute(
                f"UPDATE {self._TASKS_TABLE} SET status = 'in_progress', updated_at = ? WHERE id = ?",
                (now_iso, normalized_id),
            )
            conn.commit()
            updated = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, updated) if updated else None""",
    """            old_status = _normalize_text(task.get("status"))
            conn.execute(
                f"UPDATE {self._TASKS_TABLE} SET status = 'in_progress', updated_at = ? WHERE id = ?",
                (now_iso, normalized_id),
            )
            self._ensure_task_status_log_table(conn)
            self._log_status_change(conn, task_id=normalized_id, old_status=old_status, new_status="in_progress", user_id=user_id, username=_normalize_text(user.get("username")))
            conn.commit()
            updated = conn.execute(f"SELECT * FROM {self._TASKS_TABLE} WHERE id = ?", (normalized_id,)).fetchone()
            return self._task_with_latest_report(conn, updated) if updated else None"""
)

p.write_text(c, encoding='utf-8')
print("hub_service.py patched successfully")

# ── 2. hub.py — pass is_admin and priority ──
p2 = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\backend\api\v1\hub.py')
c2 = p2.read_text(encoding='utf-8')

# 2a. Pass is_admin to delete_task
c2 = c2.replace(
    """        ok = hub_service.delete_task(
            task_id=task_id,
            actor_user_id=int(current_user.id),
        )""",
    """        is_admin = str(getattr(current_user, "role", "") or "").lower() == "admin"
        ok = hub_service.delete_task(
            task_id=task_id,
            actor_user_id=int(current_user.id),
            is_admin=is_admin,
        )"""
)

# 2b. Pass priority to create_task
c2 = c2.replace(
    """                hub_service.create_task(
                    title=_normalize_text(payload.get("title")),
                    description=_normalize_text(payload.get("description")),
                    assignee_user_id=int(assignee_id),
                    controller_user_id=controller_user_id,
                    due_at=_normalize_text(payload.get("due_at")) or None,
                    actor=_actor_dict(current_user),
                )""",
    """                hub_service.create_task(
                    title=_normalize_text(payload.get("title")),
                    description=_normalize_text(payload.get("description")),
                    assignee_user_id=int(assignee_id),
                    controller_user_id=controller_user_id,
                    due_at=_normalize_text(payload.get("due_at")) or None,
                    priority=_normalize_text(payload.get("priority"), "normal"),
                    actor=_actor_dict(current_user),
                )"""
)

# 2c. Add comments & status log endpoints before the notifications section
c2 = c2.replace(
    """@router.get("/notifications/poll")""",
    """@router.get("/tasks/{task_id}/comments")
async def get_task_comments(
    task_id: str,
    _: User = Depends(require_permission(PERM_TASKS_READ)),
):
    return {"items": hub_service.list_task_comments(task_id)}


@router.post("/tasks/{task_id}/comments")
async def create_task_comment(
    task_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(require_permission(PERM_TASKS_READ)),
):
    body = _normalize_text(payload.get("body"))
    if len(body) < 1:
        raise HTTPException(status_code=400, detail="Comment body is required")
    result = hub_service.add_task_comment(
        task_id=task_id,
        user=_actor_dict(current_user),
        body=body,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.get("/tasks/{task_id}/status-log")
async def get_task_status_log(
    task_id: str,
    _: User = Depends(require_permission(PERM_TASKS_READ)),
):
    return {"items": hub_service.list_task_status_log(task_id)}


@router.get("/notifications/poll")"""
)

p2.write_text(c2, encoding='utf-8')
print("hub.py patched successfully")

# ── 3. client.js — add new API methods ──
p3 = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\frontend\src\api\client.js')
c3 = p3.read_text(encoding='utf-8')

# Add comments and status-log methods to hubAPI
c3 = c3.replace(
    """  pollNotifications: async (params = {}) => {""",
    """  getTaskComments: async (taskId) => {
    const response = await apiClient.get(`/hub/tasks/${encodeURIComponent(taskId)}/comments`);
    return response.data;
  },

  addTaskComment: async (taskId, body) => {
    const response = await apiClient.post(`/hub/tasks/${encodeURIComponent(taskId)}/comments`, { body });
    return response.data;
  },

  getTaskStatusLog: async (taskId) => {
    const response = await apiClient.get(`/hub/tasks/${encodeURIComponent(taskId)}/status-log`);
    return response.data;
  },

  pollNotifications: async (params = {}) => {"""
)

p3.write_text(c3, encoding='utf-8')
print("client.js patched successfully")
