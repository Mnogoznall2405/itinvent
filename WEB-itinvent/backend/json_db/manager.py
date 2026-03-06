#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compatibility JSON manager backed by shared SQLite storage.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from local_store import get_local_store

logger = logging.getLogger(__name__)


class JSONDataManager:
    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            backend_dir = Path(__file__).parent.parent
            data_dir = backend_dir.parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = get_local_store(data_dir=self.data_dir)
        logger.info("JSONDataManager initialized with SQLite store at %s", self.store.db_path)

    def _get_file_path(self, filename: str) -> Path:
        return self.data_dir / Path(filename).name

    def _ensure_file_exists(self, file_path: Path, default_content: Any = None):
        # In SQLite mode bootstrap happens by loading with default.
        self.load_json(file_path.name, default_content=default_content)

    def load_json(self, filename: str, default_content: Any = None):
        return self.store.load_json(Path(filename).name, default_content=default_content)

    def save_json(self, filename: str, data: Any) -> bool:
        return self.store.save_json(Path(filename).name, data)

    def append_to_json(self, filename: str, record: Any) -> bool:
        return self.store.append_to_json(Path(filename).name, record)

    def update_json_array(self, filename: str, predicate, updater) -> int:
        return self.store.update_json_array(Path(filename).name, predicate, updater)

    def get_json_files(self):
        return self.store.get_json_files()

