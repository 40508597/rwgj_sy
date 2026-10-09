"""Project-local cooperative state, immutable byte snapshots, and event history.

SQLite serializes cooperating metadata writers. Filesystem updates performed by
callers remain guarded, journaled best-effort operations, not an OS sandbox or
a transaction spanning unrelated editors. No third-party dependencies.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any

import _archlib


class ToolchainError(ValueError):
    def __init__(self, message: str, status: str = "unknown"):
        super().__init__(message)
        self.status = status
        self.code = 1 if status == "fail" else 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _containment_path(path: PurePath) -> PurePath:
    """Compare resolved DOS/UNC anchors without changing the path used for I/O.

    Windows non-strict realpath can retain its extended prefix when a missing
    parent is created concurrently (the initial and final Winerrors differ).
    Only known DOS-drive and UNC aliases are equivalent; device/volume
    namespaces are not project paths. POSIX paths keep their original meaning.
    """
    if not isinstance(path, PureWindowsPath):
        return path
    value, drive = str(path), path.drive
    if path.root == "\\" and re.fullmatch(r"[A-Za-z]:", drive):
        return path
    if path.root == "\\" and re.fullmatch(r"\\\\\?\\[A-Za-z]:", drive):
        return PureWindowsPath(value[4:])

    def ordinary_unc(anchor: str) -> bool:
        parts = anchor[2:].split("\\") if anchor.startswith("\\\\") else []
        return (len(parts) == 2 and all(parts) and parts[0] not in (".", "?")
                and all(":" not in part for part in parts))

    if path.root == "\\" and drive[:8].casefold() == "\\\\?\\unc\\":
        if ordinary_unc("\\\\" + drive[8:]):
            return PureWindowsPath("\\\\" + value[8:])
    elif path.root == "\\" and ordinary_unc(drive):
        return path
    raise ToolchainError("Windows 路径命名空间不可识别")


def safe_path(project: Path, rel: str) -> Path:
    project = Path(project).resolve()
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        raise ToolchainError("路径必须为非空项目相对路径")
    normalized = rel.replace("\\", "/")
    parts = normalized.split("/")
    if (normalized.startswith("/") or ":" in normalized or
            any(p in ("", "..") for p in parts) or
            any(p.endswith((".", " ")) and p != "." for p in parts)):
        raise ToolchainError(f"路径必须位于项目内，禁止绝对路径、穿越和别名: {rel}")
    target = project.joinpath(*parts)
    cursor = project
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
            raise ToolchainError(f"路径包含链接目录或文件: {rel}")
    try:
        _containment_path(target.resolve()).relative_to(_containment_path(project))
    except ValueError as exc:
        raise ToolchainError(f"路径超出项目: {rel}") from exc
    return target


def source_path(project: Path, rel: str) -> Path:
    target = safe_path(project, rel)
    if target.relative_to(Path(project).resolve()).as_posix().casefold().startswith("architecture/toolchain/"):
        raise ToolchainError("变更或恢复不得写入工具链自身状态")
    return target


def file_state(project: Path, rel: str) -> dict:
    path = safe_path(project, rel)
    if not path.exists():
        return {"exists": False, "sha256": None, "size": 0}
    if not path.is_file():
        raise ToolchainError(f"需要普通文件: {rel}")
    raw = path.read_bytes()
    return {"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def replace_file(project: Path, rel: str, raw: bytes | None, expected: dict) -> None:
    """Check preimage and replace one ordinary file; no strong cross-file CAS."""
    path = source_path(project, rel)
    if file_state(project, rel) != expected:
        raise ToolchainError(f"文件已变化，拒绝覆盖: {rel}", "fail")
    if path.exists() and path.stat().st_nlink > 1:
        raise ToolchainError(f"拒绝修改硬链接文件: {rel}", "fail")
    if raw is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".taskarch-", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if file_state(project, rel) != expected:
            raise ToolchainError(f"文件已变化，拒绝覆盖: {rel}", "fail")
        source_path(project, rel)  # recheck path components immediately before replace
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


class Store:
    def __init__(self, project: Path, create: bool = False):
        self.project = Path(project).resolve()
        self.create = create
        self.root = safe_path(self.project, "architecture/toolchain")
        self.path = safe_path(self.project, "architecture/toolchain/state.sqlite3")
        if create:
            package_markers = ("SKILL.md", "shared/scripts/_archlib.py", "shared/assets/schema/architecture.schema.json", "skills/task-architecture/LAYER.md")
            if _archlib.is_capability_package(self.project) or all((self.project / p).is_file() for p in package_markers):
                raise ToolchainError("能力包不承载调用方工具链状态；请指定业务项目")
            if not self.project.is_dir():
                raise ToolchainError("项目目录不存在")
            self.root.mkdir(parents=True, exist_ok=True)
            with self._connection(write=True) as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise ToolchainError(f"工具链状态版本不可识别: {version}")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS documents (
                        kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                        body TEXT NOT NULL, PRIMARY KEY(kind,id));
                    CREATE TABLE IF NOT EXISTS events (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                        subject TEXT NOT NULL, actor TEXT, timestamp TEXT NOT NULL,
                        data TEXT NOT NULL, prev_hash TEXT NOT NULL, sha256 TEXT NOT NULL);
                    PRAGMA user_version=1;
                """)

    @contextlib.contextmanager
    def _connection(self, write: bool = False):
        safe_path(self.project, "architecture/toolchain/state.sqlite3")
        if self.path.exists() and self.path.stat().st_nlink > 1:
            raise ToolchainError("工具链数据库不得为硬链接")
        if not self.path.exists() and not write:
            yield None
            return
        if write and not self.create:
            raise ToolchainError("只读 Store 不允许写入")
        uri = self.path.as_uri() + ("?mode=rwc" if write else "?mode=ro")
        conn = sqlite3.connect(uri, uri=True, timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=20000")
            if not write and conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ToolchainError("工具链数据库版本不可识别")
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self):
        with self._connection(write=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            else:
                conn.commit()

    def get(self, kind: str, id: str, conn=None) -> dict | None:
        if conn is None:
            with self._connection() as read:
                return self.get(kind, id, read) if read is not None else None
        row = conn.execute("SELECT body,revision FROM documents WHERE kind=? AND id=?", (kind, id)).fetchone()
        if row is None:
            return None
        result = _archlib.strict_json_loads(row["body"])
        if not isinstance(result, dict) or type(result.get("revision")) is not int or result.get("revision") != row["revision"]:
            raise ToolchainError("工具链记录损坏")
        return result

    def put(self, kind: str, id: str, document: dict, expected_revision=None, conn=None) -> dict:
        if not isinstance(document, dict) or not isinstance(kind, str) or not kind or not isinstance(id, str) or not id:
            raise ToolchainError("状态需要非空类型/编号和对象正文")
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
            raise ToolchainError("expected_revision 必须是非负整数")
        if conn is None:
            with self.transaction() as tx:
                return self.put(kind, id, document, expected_revision, tx)
        old = self.get(kind, id, conn)
        revision = old["revision"] if old else 0
        if expected_revision is not None and revision != expected_revision:
            raise ToolchainError(f"记录已变化: {kind}/{id}", "fail")
        result = dict(document)
        result["revision"] = revision + 1
        body = encoded(result).decode("utf-8")
        conn.execute("INSERT INTO documents(kind,id,revision,body) VALUES(?,?,?,?) "
                     "ON CONFLICT(kind,id) DO UPDATE SET revision=excluded.revision,body=excluded.body",
                     (kind, id, revision + 1, body))
        return result

    def list(self, kind: str, conn=None) -> list[dict]:
        if conn is None:
            with self._connection() as read:
                return self.list(kind, read) if read is not None else []
        return [self.get(kind, row["id"], conn) for row in
                conn.execute("SELECT id FROM documents WHERE kind=? ORDER BY id", (kind,))]

    def event(self, event_type: str, subject: str, data: dict, actor=None, conn=None) -> dict:
        if conn is None:
            with self.transaction() as tx:
                return self.event(event_type, subject, data, actor, tx)
        last = conn.execute("SELECT seq,sha256 FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        record = {"seq": (last["seq"] + 1) if last else 1,
                  "event_type": event_type, "subject": subject, "actor": actor,
                  "timestamp": now(), "data": data, "prev_hash": last["sha256"] if last else ""}
        record["sha256"] = hashlib.sha256(encoded(record)).hexdigest()
        conn.execute("INSERT INTO events(seq,event_type,subject,actor,timestamp,data,prev_hash,sha256) "
                     "VALUES(?,?,?,?,?,?,?,?)", (record["seq"], event_type, subject, actor,
                     record["timestamp"], encoded(data).decode("utf-8"), record["prev_hash"], record["sha256"]))
        return record

    def events(self, after: int = 0, limit: int = 100, subject=None) -> dict:
        if type(after) is not int or type(limit) is not int or after < 0 or limit < 1:
            raise ToolchainError("事件分页需要 after>=0、limit>=1")
        with self._connection() as conn:
            records = []
            previous = ""
            expected = 1
            if conn is not None:
                for row in conn.execute("SELECT * FROM events ORDER BY seq"):
                    value = dict(row)
                    value["data"] = _archlib.strict_json_loads(value["data"])
                    digest = value.pop("sha256")
                    if (value["seq"] != expected or value["prev_hash"] != previous or
                            hashlib.sha256(encoded(value)).hexdigest() != digest):
                        raise ToolchainError("事件链校验失败", "fail")
                    value["sha256"] = digest
                    records.append(value)
                    previous, expected = digest, expected + 1
        matching = [v for v in records if v["seq"] > after and (subject is None or v["subject"] == subject)]
        selected = matching[:limit]
        return {"items": selected, "total": len(matching), "after": after, "limit": limit,
                "has_more": len(matching) > limit,
                "next_after": selected[-1]["seq"] if selected else after,
                "integrity": "pass", "limitations": ["哈希链可检测意外篡改，不是签名或身份认证"]}

    def _put_blob(self, raw: bytes) -> str:
        if not self.create:
            raise ToolchainError("只读 Store 不允许保存快照")
        sha = hashlib.sha256(raw).hexdigest()
        target = safe_path(self.project, f"architecture/toolchain/blobs/{sha}")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ToolchainError("已有内容快照损坏", "fail")
        return sha

    def capture(self, files: list[str]) -> dict:
        if not self.create:
            raise ToolchainError("只读 Store 不允许保存快照")
        if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
            raise ToolchainError("快照范围必须为路径字符串数组")
        result = {}
        for rel in sorted(set(files)):
            path = safe_path(self.project, rel)
            if not path.exists():
                result[rel] = {"exists": False, "sha256": None, "size": 0}
            elif not path.is_file():
                raise ToolchainError(f"快照需要普通文件: {rel}")
            else:
                raw = path.read_bytes()
                sha = self._put_blob(raw)
                result[rel] = {"exists": True, "sha256": sha, "size": len(raw)}
        return result

    def blob(self, sha: str) -> bytes:
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ToolchainError("快照摘要格式无效")
        target = safe_path(self.project, f"architecture/toolchain/blobs/{sha}")
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ToolchainError("内容快照哈希不匹配", "fail")
        return raw
