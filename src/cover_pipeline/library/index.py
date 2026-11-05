"""资源库：模型、素材、音源、成品，用 SQLite 建索引。

不做复杂检索，目标只有一个：界面上能一眼看到「我有哪些东西、占了多少空间」。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,          -- model / song / output / source
  name TEXT NOT NULL,
  path TEXT NOT NULL,
  size_bytes INTEGER DEFAULT 0,
  mtime REAL DEFAULT 0,
  extra TEXT DEFAULT '',
  updated_at REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_kind_path ON items(kind, path);
CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
CREATE TABLE IF NOT EXISTS favorites (
  path TEXT PRIMARY KEY,
  added_at REAL
);
"""

AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aiff"}


class Library:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """关掉连接（Windows 上不关就删不掉 db 文件）。"""
        try:
            self._conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ 扫描

    def scan(self, cfg: dict[str, Any]) -> dict[str, int]:
        project = cfg.get("project", {})
        counts = {
            "model": self._scan_models(project, cfg),
            "song": self._scan_songs(project),
            "output": self._scan_outputs(project),
            "source": self._scan_sources(cfg),
        }
        self._conn.commit()
        return counts

    def _scan_models(self, project: dict[str, Any], cfg: dict[str, Any]) -> int:
        count = 0
        models_dir = Path(project.get("models_dir") or "./models")
        if models_dir.exists():
            for path in models_dir.glob("*.pth"):
                count += self._upsert("model", path)
        rvc_dir = ((cfg.get("local") or {}).get("rvc") or {}).get("dir")
        if rvc_dir:
            weight_dir = Path(rvc_dir) / "assets" / "weights"
            if weight_dir.exists():
                for path in weight_dir.glob("*.pth"):
                    count += self._upsert("model", path, extra="rvc")
        return count

    def _scan_songs(self, project: dict[str, Any]) -> int:
        count = 0
        work_dir = Path(project.get("work_dir") or "./work")
        if not work_dir.exists():
            return 0
        for song_dir in work_dir.iterdir():
            if not song_dir.is_dir() or song_dir.name.startswith("_"):
                continue
            size = _dir_size(song_dir)
            self._upsert_dir("song", song_dir, size)
            count += 1
        return count

    def _scan_outputs(self, project: dict[str, Any]) -> int:
        count = 0
        output_dir = Path(project.get("output_dir") or "./output")
        if output_dir.exists():
            for path in output_dir.rglob("*"):
                if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES:
                    count += self._upsert("output", path)
        return count

    def _scan_sources(self, cfg: dict[str, Any]) -> int:
        count = 0
        dirs = (cfg.get("source") or {}).get("search_dirs") or []
        for raw in dirs:
            root = Path(str(raw)).expanduser()
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES:
                    count += self._upsert("source", path)
        return count

    # ------------------------------------------------------------------ 查询

    def list(self, kind: str | None = None, query: str = "", limit: int = 50, page: int = 1) -> list[dict[str, Any]]:
        page = max(1, int(page))
        offset = (page - 1) * max(1, int(limit))
        sql = (
            "SELECT items.kind, items.name, items.path, items.size_bytes, items.mtime, items.extra, "
            "CASE WHEN favorites.path IS NULL THEN 0 ELSE 1 END AS favorite "
            "FROM items LEFT JOIN favorites ON favorites.path = items.path"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if query:
            clauses.append("name LIKE ?")
            params.append(f"%{query}%")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY mtime DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), offset])
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count(self, kind: str | None = None, query: str = "") -> int:
        sql = "SELECT COUNT(*) AS n FROM items"
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if query:
            clauses.append("name LIKE ?")
            params.append(f"%{query}%")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        row = self._conn.execute(sql, params).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------ 单条操作

    def detail(self, path: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT items.kind, items.name, items.path, items.size_bytes, items.mtime, items.extra, "
            "CASE WHEN favorites.path IS NULL THEN 0 ELSE 1 END AS favorite "
            "FROM items LEFT JOIN favorites ON favorites.path = items.path WHERE items.path = ?",
            (str(path),),
        ).fetchone()
        if row:
            return dict(row)
        target = Path(path)
        if target.exists():
            stat = target.stat()
            return {
                "kind": "song" if target.is_dir() else "file",
                "name": target.name,
                "path": str(target),
                "size_bytes": 0 if target.is_dir() else stat.st_size,
                "mtime": stat.st_mtime,
                "extra": "",
                "favorite": self.is_favorite(str(target)),
            }
        return None

    def is_favorite(self, path: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM favorites WHERE path = ?", (str(path),)).fetchone()
        return bool(row)

    def set_favorite(self, path: str, on: bool = True) -> bool:
        if on:
            self._conn.execute(
                "INSERT OR REPLACE INTO favorites(path, added_at) VALUES(?, ?)", (str(path), time.time())
            )
        else:
            self._conn.execute("DELETE FROM favorites WHERE path = ?", (str(path),))
        self._conn.commit()
        return on

    def favorites(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT items.kind, items.name, items.path, items.size_bytes, items.mtime "
            "FROM favorites LEFT JOIN items ON items.path = favorites.path ORDER BY favorites.added_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, path: str, trash_dir: Path) -> Path | None:
        """不真删，挪到 work/_trash/时间戳/ 下，后悔还能捞回来。"""
        target = Path(path)
        if not target.exists():
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest_dir = Path(trash_dir) / stamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / target.name
        try:
            target.rename(dest)
        except OSError:
            import shutil

            if target.is_dir():
                shutil.copytree(target, dest)
                shutil.rmtree(target, ignore_errors=True)
            else:
                shutil.copy2(target, dest)
                target.unlink(missing_ok=True)
        self._conn.execute("DELETE FROM items WHERE path = ?", (str(target),))
        self._conn.execute("DELETE FROM favorites WHERE path = ?", (str(target),))
        self._conn.commit()
        return dest

    def stats(self) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT kind, COUNT(*) AS n, SUM(size_bytes) AS bytes FROM items GROUP BY kind"
        ).fetchall()
        by_kind = {row["kind"]: {"count": row["n"], "bytes": row["bytes"] or 0} for row in rows}
        total = sum(item["bytes"] for item in by_kind.values())
        return {"by_kind": by_kind, "total_bytes": total, "items": sum(item["count"] for item in by_kind.values())}

    def remove(self, kind: str, path: str) -> bool:
        cur = self._conn.execute("DELETE FROM items WHERE kind = ? AND path = ?", (kind, path))
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------ 内部

    def _upsert(self, kind: str, path: Path, extra: str = "") -> int:
        try:
            stat = path.stat()
        except OSError:
            return 0
        self._conn.execute(
            """INSERT INTO items(kind, name, path, size_bytes, mtime, extra, updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(kind, path) DO UPDATE SET
                 name=excluded.name, size_bytes=excluded.size_bytes,
                 mtime=excluded.mtime, extra=excluded.extra, updated_at=excluded.updated_at""",
            (kind, path.name, str(path), stat.st_size, stat.st_mtime, extra, time.time()),
        )
        return 1

    def _upsert_dir(self, kind: str, path: Path, size: int) -> int:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        self._conn.execute(
            """INSERT INTO items(kind, name, path, size_bytes, mtime, extra, updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(kind, path) DO UPDATE SET
                 size_bytes=excluded.size_bytes, mtime=excluded.mtime, updated_at=excluded.updated_at""",
            (kind, path.name, str(path), size, mtime, "", time.time()),
        )
        return 1


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}TB"
