"""Project collaboration, operation debugging and guarded checkpoint recovery.

These records describe tool operations and project bytes, never hidden reasoning.
Leases serialize cooperating clients; they are not an operating-system sandbox.
File restore has a durable preimage journal and guarded recovery, not a claim of
atomicity across multiple filesystem paths or external services.
"""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import html
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _toolchain_store import Store, ToolchainError, file_state, now, replace_file, safe_path, uid

PROTOCOL_VERSION = 1


def _runtime_reference() -> dict:
    return {"protocol_version": PROTOCOL_VERSION,
            "runtime_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _fail(message: str):
    raise ToolchainError(message, status="fail")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\x00\r\n"):
        raise ToolchainError(label + " must be a nonempty single-line string")
    return value


def _list(value: Any, label: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not empty and not value):
        raise ToolchainError(label + " must be an array" + ("" if empty else " with at least one item"))
    result = [_text(item, label) for item in value]
    if len(result) != len(set(result)):
        raise ToolchainError(label + " contains duplicate entries")
    return result


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("naive timestamp")
        return result.astimezone(timezone.utc)
    except (ValueError, AttributeError) as exc:
        raise ToolchainError("invalid timezone-aware timestamp: " + str(value)) from exc


def _ttl(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= 86400:
        raise ToolchainError("ttl_seconds must be an integer from 1 to 86400")
    return value


def _index(project: Path, architecture: str) -> dict:
    from _toolchain_query import build_index
    return build_index(project, architecture)


def _graph(project: Path, architecture: str) -> tuple[dict, dict[str, set[str]]]:
    index = _index(project, architecture)
    modules = {item["key"]: item for item in index["objects"] if item["kind"] == "module"}
    ids = {item["id"]: key for key, item in modules.items()}
    descendants = {key: {key} for key in modules}
    children = {key: set() for key in modules}
    for edge in index["relationships"]:
        if edge["type"] == "contains" and edge["source"] in ids and edge["target"] in ids:
            children[ids[edge["source"]]].add(ids[edge["target"]])
    for module in modules:
        pending = list(children[module])
        while pending:
            child = pending.pop()
            if child == module:
                _fail("cyclic module containment prevents collaboration scope: " + module)
            if child not in descendants[module]:
                descendants[module].add(child)
                pending.extend(children[child])
    return index, descendants


def _scope(project: Path, architecture: str, modules: Any) -> tuple[dict, dict, list[str]]:
    modules = _list(modules, "modules")
    index, descendants = _graph(project, architecture)
    missing = sorted(set(modules) - set(descendants))
    if missing:
        raise ToolchainError("unknown module IDs: " + ", ".join(missing))
    return index, descendants, modules


def _active_lease(document: dict) -> bool:
    return document.get("status") == "active" and _timestamp(document["expires_at"]) > _timestamp(now())


def _overlaps(left: list[str], right: list[str], descendants: dict[str, set[str]]) -> bool:
    return any(a == b or b in descendants.get(a, ()) or a in descendants.get(b, ())
               for a in left for b in right)


def lease_conflicts(store: Store, modules: list[str], actor: str | None = None,
                    conn=None, architecture: str = "architecture.json") -> list[dict]:
    """Return active parent/child ownership conflicts, ignoring actor's own leases.

    Unknown historical lease modules conservatively conflict when their recorded
    architecture scope cannot be compared after structural edits.
    """
    _, descendants, modules = _scope(store.project, architecture, modules)
    result = []
    for lease in store.list("lease", conn=conn):
        if not _active_lease(lease) or actor is not None and lease["actor"] == actor:
            continue
        unknown = set(lease["modules"]) - set(descendants)
        if unknown or _overlaps(modules, lease["modules"], descendants):
            result.append(lease)
    return result


def claim_lease(project: Path, architecture: str, actor: str, modules: list[str],
                ttl_seconds: int = 300) -> dict:
    actor = _text(actor, "actor")
    ttl_seconds = _ttl(ttl_seconds)
    _, _, modules = _scope(project, architecture, modules)
    store = Store(project, create=True)
    with store.transaction() as tx:
        conflicts = lease_conflicts(store, modules, conn=tx, architecture=architecture)
        if conflicts:
            _fail("module scope already leased: " + ", ".join(item["id"] for item in conflicts))
        lease_id = uid("lease")
        result = store.put("lease", lease_id, {
            "id": lease_id, "token": uid("lease-token"), "actor": actor,
            "modules": modules, "architecture": architecture, "status": "active",
            "created_at": now(), "expires_at": (_timestamp(now()) + timedelta(seconds=ttl_seconds)).isoformat(),
            "limitations": ["cooperating-client ownership registration; no operating-system write isolation"],
        }, expected_revision=0, conn=tx)
        store.event("lease.claimed", lease_id, result, actor=actor, conn=tx)
    return result


def _owned(store: Store, kind: str, identifier: str, actor: str, conn=None) -> dict:
    actor = _text(actor, "actor")
    document = store.get(kind, _text(identifier, kind + " ID"), conn=conn)
    if document is None:
        raise ToolchainError(kind + " does not exist: " + identifier)
    if document.get("actor") != actor:
        _fail(kind + " belongs to another actor")
    return document


def _lease_mutate(project: Path, action: str, identifier: str, actor: str,
                  token: str, ttl_seconds: int = 300) -> dict:
    token = _text(token, "token")
    if action == "renew":
        ttl_seconds = _ttl(ttl_seconds)
    store = Store(project, create=True)
    with store.transaction() as tx:
        lease = _owned(store, "lease", identifier, actor, tx)
        if lease["token"] != token:
            _fail("lease token mismatch")
        if not _active_lease(lease):
            _fail("lease is released or expired; claim a new lease")
        if action == "renew":
            conflicts = lease_conflicts(store, lease["modules"], actor=actor, conn=tx,
                                        architecture=lease["architecture"])
            if conflicts:
                _fail("lease scope conflicts after architecture change")
            lease["expires_at"] = (_timestamp(now()) + timedelta(seconds=ttl_seconds)).isoformat()
        else:
            lease["status"] = "released"
            lease["released_at"] = now()
        result = store.put("lease", identifier, lease, expected_revision=lease["revision"], conn=tx)
        store.event("lease." + ("renewed" if action == "renew" else "released"), identifier,
                    result, actor=actor, conn=tx)
    return result


def _source_files(index: dict, modules: list[str] | None = None, *, owned_only: bool = False) -> list[str]:
    result = set(index["input_hashes"])
    for item in index.get("files", []):
        if (modules is None or item.get("module") in modules) and (not owned_only or item.get("ownership") is True):
            result.add(item["path"])
    return sorted(result)


def _expand_paths(project: Path, paths: list[str]) -> tuple[list[str], dict]:
    """Expand explicitly declared directories, binding their complete inventory.

    Toolchain metadata is never project source and is excluded from directory
    enumeration, including a project-root source declaration. Every encountered
    path still goes through the shared symlink/junction containment guard.
    """
    project = Path(project).resolve()
    files, directories = set(), {}
    for relative in sorted(set(paths)):
        path = safe_path(project, relative)
        normalized = path.relative_to(project).as_posix().casefold()
        if normalized == "architecture/toolchain" or normalized.startswith("architecture/toolchain/"):
            raise ToolchainError("project source snapshots cannot include toolchain metadata")
        if not path.is_dir():
            files.add(path.relative_to(project).as_posix())
            continue
        inventory_files, inventory_directories = [], []
        pending = [path]
        while pending:
            directory = pending.pop()
            for child in sorted(directory.iterdir(), key=lambda item: item.name):
                child_relative = child.relative_to(project).as_posix()
                normalized = child_relative.casefold()
                if normalized == "architecture/toolchain" or normalized.startswith("architecture/toolchain/"):
                    continue
                safe_path(project, child_relative)
                if child.is_dir():
                    inventory_directories.append(child_relative)
                    pending.append(child)
                elif child.is_file():
                    inventory_files.append(child_relative)
                    files.add(child_relative)
                else:
                    raise ToolchainError("declared directory contains a non-regular entry: " + child_relative)
        directories[path.relative_to(project).as_posix()] = {
            "files": sorted(inventory_files), "directories": sorted(inventory_directories)}
    return sorted(files), directories


def _guard_directories(project: Path, expected: dict) -> None:
    if not expected:
        return
    _, current = _expand_paths(project, list(expected))
    if current != expected:
        _fail("declared directory inventory changed after snapshot")


def _fingerprints(project: Path, paths: list[str]) -> dict:
    return {relative: file_state(project, relative) for relative in paths}


def _matches(expected: dict, actual: dict) -> bool:
    return set(expected) == set(actual) and all(expected[path].get("exists") == actual[path]["exists"]
            and expected[path].get("sha256") == actual[path]["sha256"] for path in actual)


def _current_guard(project: Path, expected: dict) -> dict:
    actual = _fingerprints(project, sorted(expected))
    if not _matches(expected, actual):
        changed = [path for path in actual if expected[path].get("exists") != actual[path]["exists"]
                   or expected[path].get("sha256") != actual[path]["sha256"]]
        _fail("stale project inputs: " + ", ".join(changed))
    return actual


def _scoped_changes(store: Store, conn, modules: list[str], descendants: dict) -> list[dict]:
    return [item for item in store.list("change", conn=conn)
            if item.get("status") not in ("accepted", "aborted")
            and _overlaps(modules, item.get("scope", item.get("modules", [])), descendants)]


def _check_pending_writes(store: Store, conn) -> None:
    pending = ["change/" + item["id"] for item in store.list("change", conn=conn)
               if item.get("status") in ("prepared", "applying", "recovery_required")]
    pending += ["checkpoint-restore/" + item["id"] for item in store.list("checkpoint-restore", conn=conn)
                if item.get("status") in ("prepared", "restoring", "recovery_required")]
    if pending:
        _fail("recover incomplete project writes first: " + ", ".join(pending))


def handoff_export(project: Path, architecture: str, actor: str, modules: list[str],
                   next_step: str, unresolved: list[str] | None = None,
                   constraints: list[str] | None = None, to_actor: str | None = None) -> dict:
    from _toolchain_query import context
    actor = _text(actor, "actor")
    next_step = _text(next_step, "next_step")
    if to_actor is not None:
        to_actor = _text(to_actor, "to_actor")
    unresolved = _list(unresolved or [], "unresolved", empty=True)
    constraints = _list(constraints or [], "constraints", empty=True)
    index, descendants, modules = _scope(project, architecture, modules)
    expanded = sorted(set().union(*(descendants[module] for module in modules)))
    contexts = [context(index, module) for module in modules]
    paths = set(_source_files(index, expanded))
    for item in contexts:
        paths.update(item.get("input_versions", {}))
    files, directory_inventory = _expand_paths(project, sorted(paths))
    store = Store(project, create=True)
    with store.transaction() as tx:
        _check_pending_writes(store, tx)
        changes = _scoped_changes(store, tx, expanded, descendants)
        snapshots = store.capture(files)
        _guard_directories(project, directory_inventory)
        # Reject a handoff assembled from already-stale architecture facts.
        for relative, sha in index["input_hashes"].items():
            if snapshots.get(relative, {}).get("sha256") != sha:
                _fail("architecture changed while building handoff: " + relative)
        identifier = uid("handoff")
        result = store.put("handoff", identifier, {
            "id": identifier, "actor": actor, "to_actor": to_actor, "modules": modules,
            "runtime_reference": _runtime_reference(),
            "architecture": architecture, "created_at": now(), "status": "exported",
            "snapshots": snapshots, "contexts": contexts, "changes": changes,
            "directory_inventory": directory_inventory,
            "unresolved": unresolved, "constraints": constraints, "next_step": next_step,
            "limitations": ["handoff is an explicit project snapshot, not proof of independent AI execution"],
        }, expected_revision=0, conn=tx)
        store.event("handoff.exported", identifier, result, actor=actor, conn=tx)
    return result


def handoff_resume(project: Path, identifier: str, actor: str) -> dict:
    actor = _text(actor, "actor")
    identifier = _text(identifier, "handoff ID")
    store = Store(project, create=True)
    with store.transaction() as tx:
        document = store.get("handoff", identifier, conn=tx)
        if document is None:
            raise ToolchainError("handoff does not exist: " + str(identifier))
        if document.get("to_actor") not in (None, actor):
            _fail("handoff is addressed to another actor")
        _current_guard(project, document["snapshots"])
        _guard_directories(project, document.get("directory_inventory", {}))
        _, descendants, modules = _scope(project, document["architecture"], document["modules"])
        current_changes = _scoped_changes(store, tx, modules, descendants)
        if {item["id"]: item["revision"] for item in current_changes} != {
                item["id"]: item["revision"] for item in document["changes"]}:
            _fail("active change inventory changed after handoff")
        conflicts = lease_conflicts(store, document["modules"], actor=actor, conn=tx,
                                   architecture=document["architecture"])
        result = {"id": uid("resume"), "handoff": identifier, "actor": actor, "resumed_at": now(),
                  "source_actor": document["actor"], "handoff_revision": document["revision"],
                  "export_runtime_reference": document["runtime_reference"],
                  "resume_runtime_reference": _runtime_reference(),
                  "modules": document["modules"], "next_step": document["next_step"],
                  "constraints": document["constraints"], "unresolved": document["unresolved"],
                  "contexts": document["contexts"], "snapshots": document["snapshots"],
                  "directory_inventory": document.get("directory_inventory", {}),
                  "changes": document["changes"], "status": "resumed",
                  "write_scope_ready": not conflicts,
                  "lease_conflicts": [{key: value for key, value in lease.items() if key != "token"}
                                      for lease in conflicts]}
        result = store.put("handoff-resume", result["id"], result, expected_revision=0, conn=tx)
        store.event("handoff.resumed", identifier, result, actor=actor, conn=tx)
    return result


def run_begin(project: Path, actor: str, goal: str, breakpoints: list[str] | None = None) -> dict:
    actor, goal = _text(actor, "actor"), _text(goal, "goal")
    breakpoints = _list(breakpoints or [], "breakpoints", empty=True)
    store = Store(project, create=True)
    with store.transaction() as tx:
        identifier = uid("run")
        result = store.put("run", identifier, {
            "id": identifier, "actor": actor, "goal": goal, "status": "running", "created_at": now(),
            "runtime_reference": _runtime_reference(),
            "breakpoints": breakpoints, "active_operation": None, "pending_operation": None,
            "single_step": False, "bypass_pending": False, "pause_requested": False, "completed_steps": 0,
            "limitations": ["records visible tool inputs and results; does not record hidden reasoning"],
        }, expected_revision=0, conn=tx)
        store.event("run.began", identifier, result, actor=actor, conn=tx)
    return result


def run_control(project: Path, identifier: str, actor: str, action: str,
                 result: Any = None, breakpoints: list[str] | None = None) -> dict:
    store = Store(project, create=True)
    with store.transaction() as tx:
        run = _owned(store, "run", identifier, actor, tx)
        if run["status"] == "ended":
            _fail("run already ended")
        if action in ("resume", "step", "end") and run["active_operation"] is not None:
            _fail("operation is in progress; record its result before " + action)
        if breakpoints is not None:
            run["breakpoints"] = _list(breakpoints, "breakpoints", empty=True)
        if action == "pause":
            if run["active_operation"] is not None:
                run["pause_requested"] = True
            else:
                run["status"] = "paused"
        elif action in ("resume", "step"):
            run["status"] = "running"
            run["pause_requested"] = False
            run["single_step"] = action == "step"
            run["bypass_pending"] = run["pending_operation"] is not None
        elif action == "end":
            run["status"], run["ended_at"], run["result"] = "ended", now(), result
        else:
            raise ToolchainError("unknown run control: " + action)
        document = store.put("run", identifier, run, expected_revision=run["revision"], conn=tx)
        store.event("run." + action, identifier, document, actor=actor, conn=tx)
    return document


def run_guard(project: Path, identifier: str, actor: str, operation: str, inputs: Any) -> dict:
    operation = _text(operation, "operation")
    store = Store(project, create=True)
    with store.transaction() as tx:
        run = _owned(store, "run", identifier, actor, tx)
        if run["status"] == "ended":
            _fail("run already ended")
        if run["active_operation"] is not None:
            _fail("another operation is active in this run")
        candidate = {"operation": operation, "inputs": inputs}
        if run["pending_operation"] is not None and candidate != run["pending_operation"]:
            _fail("pending breakpoint operation differs; resume the exact operation or end this run")
        paused = run["status"] == "paused"
        hit = any(fnmatch.fnmatchcase(operation, pattern) for pattern in run["breakpoints"])
        if paused or hit and not run["bypass_pending"] and not run["single_step"]:
            run["status"], run["pending_operation"] = "paused", candidate
            run = store.put("run", identifier, run, expected_revision=run["revision"], conn=tx)
            store.event("run.breakpoint" if hit else "run.waiting", identifier,
                        {"operation": operation, "inputs": inputs}, actor=actor, conn=tx)
            return {"permitted": False, "operation_id": None, "run": run}
        operation_id = uid("operation")
        run["active_operation"] = {"id": operation_id, **candidate, "started_at": now()}
        run["pending_operation"], run["bypass_pending"] = None, False
        run = store.put("run", identifier, run, expected_revision=run["revision"], conn=tx)
        store.event("operation.started", identifier, run["active_operation"], actor=actor, conn=tx)
    return {"permitted": True, "operation_id": operation_id, "run": run}


def run_record(project: Path, identifier: str, actor: str, operation_id: str,
               result: Any, status: str = "pass") -> dict:
    if status not in ("pass", "fail", "unknown"):
        raise ToolchainError("operation status must be pass, fail or unknown")
    store = Store(project, create=True)
    with store.transaction() as tx:
        run = _owned(store, "run", identifier, actor, tx)
        operation = run.get("active_operation")
        if operation is None or operation["id"] != operation_id:
            _fail("operation ID is not active in this run")
        event = store.event("operation.completed", identifier,
                            {**operation, "finished_at": now(), "status": status, "result": result},
                            actor=actor, conn=tx)
        run["active_operation"] = None
        run["completed_steps"] += 1
        if run["single_step"] or run["pause_requested"]:
            run["status"] = "paused"
        run["single_step"], run["pause_requested"] = False, False
        run = store.put("run", identifier, run, expected_revision=run["revision"], conn=tx)
    return {"run": run, "event": event}


def _checkpoint_paths(project: Path, index: dict, files: list[str]) -> list[str]:
    # Behavioral placements and test references are read dependencies, not
    # write ownership. They cannot authorize later checkpoint deletions.
    paths = set(_source_files(index, owned_only=True))
    for relative in files:
        target = safe_path(project, relative)
        paths.add(target.relative_to(project.resolve()).as_posix())
    for relative in paths:
        normalized = relative.replace("\\", "/").casefold()
        if normalized == "architecture/toolchain" or normalized.startswith("architecture/toolchain/"):
            raise ToolchainError("checkpoints cannot capture or restore toolchain metadata")
        safe_path(project, relative)
    return sorted(paths)


def checkpoint_capture(project: Path, architecture: str, actor: str, label: str,
                       files: list[str] | None = None) -> dict:
    actor, label = _text(actor, "actor"), _text(label, "label")
    files = _list(files or [], "files", empty=True)
    index = _index(project, architecture)
    paths = _checkpoint_paths(project, index, files)
    paths, directory_inventory = _expand_paths(project, paths)
    store = Store(project, create=True)
    with store.transaction() as tx:
        _check_pending_writes(store, tx)
        snapshots = store.capture(paths)
        _guard_directories(project, directory_inventory)
        for relative, sha in index["input_hashes"].items():
            if snapshots[relative]["sha256"] != sha:
                _fail("architecture changed while capturing checkpoint")
        identifier = uid("checkpoint")
        document = store.put("checkpoint", identifier, {
            "id": identifier, "actor": actor, "architecture": architecture, "label": label,
            "runtime_reference": _runtime_reference(),
            "created_at": now(), "snapshots": snapshots,
            "directory_inventory": directory_inventory,
            "modules": [item["key"] for item in index["objects"] if item["kind"] == "module"],
            "limitations": ["captures architecture and manifest-owned files (including registered tests), plus explicit files",
                            "does not capture undeclared later files or restore external effects"],
        }, expected_revision=0, conn=tx)
        store.event("checkpoint.captured", identifier, document, actor=actor, conn=tx)
    return document


def _unregistered_paths(project: Path, managed: set[str]) -> dict:
    from _module_tree import DEFAULT_IGNORE_DIRS
    preserved, unknown, excluded = [], [], set(DEFAULT_IGNORE_DIRS)
    def walk_error(error):
        unknown.append({"path": str(getattr(error, "filename", "")), "reason": str(error)})
    for directory, dirs, files in os.walk(project, followlinks=False, onerror=walk_error):
        allowed = []
        for name in sorted(dirs):
            path = Path(directory) / name
            relative = path.relative_to(project).as_posix()
            if name in excluded or relative.casefold() == "architecture/toolchain":
                continue
            try:
                safe_path(project, relative)
                allowed.append(name)
            except ToolchainError as exc:
                unknown.append({"path": relative, "reason": str(exc)})
        dirs[:] = allowed
        for name in sorted(files):
            relative = (Path(directory) / name).relative_to(project).as_posix()
            if relative in managed:
                continue
            try:
                path = safe_path(project, relative)
                if path.is_file():
                    preserved.append(relative)
                else:
                    unknown.append({"path": relative, "reason": "not a regular file"})
            except ToolchainError as exc:
                unknown.append({"path": relative, "reason": str(exc)})
    return {"preserved_unregistered": sorted(preserved), "preserved_unknown": unknown,
            "scan_scope": {"project": str(project), "excluded_directory_names": sorted(excluded),
                           "excluded_paths": ["architecture/toolchain"], "follow_links": False}}


def _restore_plan(project: Path, checkpoint: dict) -> dict:
    target = dict(checkpoint["snapshots"])
    mode, diagnostics, newly_registered = "managed_tree", [], []
    current_versions, current_directories = {}, {}
    try:
        index = _index(project, checkpoint["architecture"])
        paths = _checkpoint_paths(project, index, [])
        paths, current_directories = _expand_paths(project, paths)
        current_versions = index["input_hashes"]
        newly_registered = sorted(set(paths) - set(target))
        for relative in newly_registered:
            target[relative] = {"exists": False, "sha256": None, "size": 0}
    except (OSError, ValueError) as exc:
        # Captured ordinary files remain recoverable even if their present
        # architecture is malformed. Unknown current ownership never authorizes
        # deleting additional paths.
        mode = "captured_only"
        diagnostics.append({"status": "unknown", "reason": str(exc),
                            "consequence": "current ownership inventory unavailable; later paths are preserved"})
    current = _fingerprints(project, sorted(target))
    if mode == "managed_tree":
        for relative, sha in current_versions.items():
            if current.get(relative, {}).get("sha256") != sha:
                _fail("architecture changed while preparing checkpoint restore plan")
        _guard_directories(project, current_directories)
    return {"mode": mode, "expected_current": current, "target": target,
            "changed_files": [path for path in current if current[path] != target[path]],
            "newly_registered_paths": newly_registered,
            "delete_files": [path for path in current if current[path]["exists"] and not target[path]["exists"]],
            "current_input_versions": current_versions, "current_directory_inventory": current_directories,
            "diagnostics": diagnostics, **_unregistered_paths(project, set(target)),
            "limitations": ["only confirmed managed ordinary files are deleted; directories and unknown/unregistered paths are preserved",
                            "external side effects are not restored; restored project requires fresh verification"]}


def checkpoint_preview(project: Path, identifier: str) -> dict:
    store = Store(project)
    document = store.get("checkpoint", identifier)
    if document is None:
        raise ToolchainError("checkpoint does not exist: " + str(identifier))
    return {"checkpoint": identifier, **_restore_plan(project, document)}


def _write_image(project: Path, relative: str, image: dict, store: Store,
                 expected: dict | None = None) -> None:
    payload = store.blob(image["sha256"]) if image["exists"] else None
    replace_file(project, relative, payload, expected if expected is not None else file_state(project, relative))


def _restore_order(paths: list[str]) -> list[str]:
    return sorted(paths, key=lambda relative: (Path(relative).name != "architecture.json", relative))


def _rollback(project: Path, journal: dict, store: Store) -> list[str]:
    conflicts = []
    for relative in reversed(_restore_order(list(journal["before"]))):
        try:
            current = _fingerprints(project, [relative])[relative]
            before, after = journal["before"][relative], journal["after"][relative]
            if current == before:
                continue
            if current != after:
                conflicts.append(relative)
                continue
            _write_image(project, relative, before, store, current)
        except (OSError, ValueError, ToolchainError) as exc:
            conflicts.append(relative + ": " + str(exc))
    return conflicts


def _expected(value: Any, paths: list[str]) -> dict:
    if not isinstance(value, dict) or set(value) != set(paths):
        raise ToolchainError("expected_current must contain exactly the checkpoint paths; use checkpoint.preview")
    result = {}
    for path in paths:
        item = value[path]
        if not isinstance(item, dict) or type(item.get("exists")) is not bool:
            raise ToolchainError("invalid expected_current fingerprint: " + path)
        sha = item.get("sha256")
        if item["exists"] and (not isinstance(sha, str) or len(sha) != 64
                                or any(c not in "0123456789abcdef" for c in sha)):
            raise ToolchainError("invalid expected SHA256: " + path)
        if not item["exists"] and sha is not None:
            raise ToolchainError("absent expected file must have a null SHA256")
        result[path] = {"exists": item["exists"], "sha256": sha, "size": item.get("size", 0)}
    return result


def checkpoint_restore(project: Path, identifier: str, actor: str, expected_current: dict) -> dict:
    actor = _text(actor, "actor")
    identifier = _text(identifier, "checkpoint ID")
    store = Store(project, create=True)
    with store.transaction() as tx:
        checkpoint = store.get("checkpoint", identifier, conn=tx)
        if checkpoint is None:
            raise ToolchainError("checkpoint does not exist: " + str(identifier))
        plan = _restore_plan(project, checkpoint)
        expected = _expected(expected_current, sorted(plan["target"]))
        _current_guard(project, expected)
        # Validate all paths and all immutable blobs before touching any file.
        for relative, image in plan["target"].items():
            _checkpoint_paths(project, {"input_hashes": {}, "files": []}, [relative])
            if image["exists"]:
                store.blob(image["sha256"])
        # This checkpoint spans the whole declared project. Refuse other actors'
        # active leases without reparsing possibly broken current architecture.
        conflicts = [item for item in store.list("lease", conn=tx)
                     if _active_lease(item) and item["actor"] != actor]
        if conflicts:
            _fail("checkpoint restore conflicts with active module leases")
        _check_pending_writes(store, tx)
        restore_id = uid("restore")
        journal = store.put("checkpoint-restore", restore_id, {
            "id": restore_id, "actor": actor, "checkpoint": identifier, "architecture": checkpoint["architecture"],
            "status": "prepared", "created_at": now(), "before": store.capture(sorted(expected)),
            "after": plan["target"], "branch": uid("branch"), "conflicts": [],
            "restore_mode": plan["mode"], "newly_registered_paths": plan["newly_registered_paths"],
            "preserved_unregistered": plan["preserved_unregistered"], "preserved_unknown": plan["preserved_unknown"],
            "diagnostics": plan["diagnostics"], "limitations": plan["limitations"],
        }, expected_revision=0, conn=tx)
        store.event("checkpoint.restore.prepared", restore_id, journal, actor=actor, conn=tx)
    # Preparation is durably committed before filesystem writes. A process crash
    # leaves a recoverable journal even if the following SQL transaction aborts.
    writes_started = False
    try:
        with store.transaction() as tx:
            _current_guard(project, journal["before"])
            if any(_active_lease(item) and item["actor"] != actor for item in store.list("lease", conn=tx)):
                _fail("checkpoint restore conflicts with a newly claimed module lease")
            journal["status"] = "restoring"
            writes_started = True
            for relative in _restore_order(list(journal["after"])):
                _write_image(project, relative, journal["after"][relative], store, journal["before"][relative])
            _current_guard(project, journal["after"])
            journal["status"], journal["finished_at"] = "restored", now()
            document = store.put("checkpoint-restore", restore_id, journal,
                                 expected_revision=journal["revision"], conn=tx)
            branch = store.put("branch", journal["branch"], {
                "id": journal["branch"], "actor": actor, "created_at": now(),
                "checkpoint": identifier, "restore": restore_id, "snapshots": journal["after"],
                "verification_status": "unknown",
                "limitations": ["restored bytes require fresh verification; external effects were not restored"],
            }, expected_revision=0, conn=tx)
            store.event("branch.created", branch["id"], branch, actor=actor, conn=tx)
            store.event("checkpoint.restored", restore_id, document, actor=actor, conn=tx)
        return document
    except (OSError, ValueError, ToolchainError) as exc:
        with store.transaction() as tx:
            conflicts = _rollback(project, journal, store) if writes_started else []
            journal["status"] = ("recovery_required" if conflicts else "failed_rolled_back") if writes_started else "rejected_before_write"
            journal["conflicts"], journal["error"] = conflicts, str(exc)
            store.put("checkpoint-restore", restore_id, journal, expected_revision=journal["revision"], conn=tx)
            store.event("checkpoint.restore.failed", restore_id, journal, actor=actor, conn=tx)
        _fail("checkpoint restore failed; " + journal["status"] + "; journal=" + restore_id + "; " + str(exc))


def checkpoint_recover(project: Path, identifier: str, actor: str) -> dict:
    store = Store(project, create=True)
    with store.transaction() as tx:
        journal = _owned(store, "checkpoint-restore", identifier, actor, tx)
        if journal["status"] not in ("prepared", "restoring", "recovery_required"):
            _fail("restore journal is already terminal")
        if any(_active_lease(item) and item["actor"] != actor for item in store.list("lease", conn=tx)):
            _fail("checkpoint recovery conflicts with active module leases")
        conflicts = _rollback(project, journal, store)
        journal["conflicts"] = conflicts
        journal["status"] = "recovery_required" if conflicts else "recovered_rolled_back"
        document = store.put("checkpoint-restore", identifier, journal,
                             expected_revision=journal["revision"], conn=tx)
        store.event("checkpoint.restore.recovered", identifier, document, actor=actor, conn=tx)
        if conflicts:
            # Commit the conflict evidence before reporting a failed recovery.
            error = "restore recovery refuses concurrent file edits: " + ", ".join(conflicts)
        else:
            error = None
    if error:
        _fail(error)
    return document


def _event_summary(event: dict) -> tuple[str, str]:
    """Describe visible recorded facts without inventing verification verdicts."""
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
    status = data.get("status", result.get("status", verification.get("status")))
    status = str(status) if isinstance(status, (str, bool, int)) else "未记录状态"
    parts = []
    for key, label in (("operation", "操作"), ("file", "文件"), ("goal", "目标"),
                       ("next_step", "下一步"), ("label", "检查点"), ("error", "错误")):
        value = data.get(key)
        if isinstance(value, str) and value:
            parts.append(label + "：" + value)
    for key, label in (("scope", "模块"), ("modules", "模块"), ("files", "文件"),
                       ("operations", "暂存操作"), ("inputs", "输入文件"), ("snapshots", "快照文件"),
                       ("images", "变更文件"), ("unresolved", "未决项")):
        value = data.get(key)
        if isinstance(value, (dict, list)):
            parts.append(label + " " + str(len(value)) + " 项")
    if not parts and result:
        if isinstance(result.get("error"), str):
            parts.append("结果：" + result["error"])
        elif "code" in result:
            parts.append("返回码：" + str(result["code"]))
    if not parts:
        parts.append("完整原始记录保留在下方，点击展开查看")
    description = " · ".join(parts)
    if len(description) > 420:
        description = description[:420] + "…（完整内容展开查看）"
    return status, description


def _timeline_html(page: dict) -> str:
    # Raw records occur only in escaped text nodes. The fixed script reads
    # textContent; it never converts event data into executable HTML or code.
    events = page.get("items", page.get("events", []))
    sections, counts = [], {}
    for event in events:
        label = str(event.get("event_type", event.get("type", "event")))
        counts[label] = counts.get(label, 0) + 1
        seq = event.get("sequence", event.get("seq", event.get("id", "")))
        status, description = _event_summary(event)
        status_class = status if status in ("pass", "fail", "unknown") else "neutral"
        sections.append('<details class="timeline-event" data-event-type="' + html.escape(label, quote=True)
                        + '"><summary><span class="event-heading"><span class="sequence">#' + html.escape(str(seq))
                        + '</span><span class="event-type">' + html.escape(label) + '</span><span class="badge '
                        + status_class + '">' + html.escape(status) + '</span></span><span class="event-meta"><time>'
                        + html.escape(str(event.get("timestamp", "未记录时间"))) + '</time><span>操作者：'
                        + html.escape(str(event.get("actor") or "未记录")) + '</span><span class="subject">对象：'
                        + html.escape(str(event.get("subject") or "未记录")) + '</span></span><span class="event-description">'
                        + html.escape(description) + '</span></summary><div class="raw-label">完整原始记录 · 输入、结果、版本和哈希</div><pre>'
                        + html.escape(json.dumps(event, ensure_ascii=False, indent=2))
                        + "</pre></details>")
    pagination = {key: value for key, value in page.items() if key not in ("events", "items")}
    options = '<option value="">全部事件类型</option>' + "".join(
        '<option value="' + html.escape(label, quote=True) + '">' + html.escape(label) + '（' + str(count)
        + '）</option>' for label, count in sorted(counts.items()))
    more = "仍有后续事件" if page.get("has_more") else "本次查询已无后续事件"
    integrity = {"pass": "通过", "fail": "失败", "unknown": "未验证"}.get(page.get("integrity"), str(page.get("integrity", "未提供")))
    page_text = ("本页 " + str(len(events)) + " 条 · 当前游标 " + str(page.get("after", 0))
                 + " · 请求上限 " + str(page.get("limit", len(events))) + " 条 · 当前游标后的匹配事件共 "
                 + str(page.get("total", len(events))) + " 条 · " + more + " · 下一游标 "
                 + str(page.get("next_after", page.get("after", 0))) + " · 哈希链校验：" + integrity)
    script = """(() => {
  'use strict';
  const cards = Array.from(document.querySelectorAll('.timeline-event'));
  const search = document.getElementById('timeline-search');
  const types = document.getElementById('timeline-type');
  const count = document.getElementById('filter-count');
  const empty = document.getElementById('filter-empty');
  const searchable = new Map(cards.map(card => [card, card.textContent.toLocaleLowerCase()]));
  function filter() {
    const term = search.value.trim().toLocaleLowerCase();
    const type = types.value;
    let visible = 0;
    for (const card of cards) {
      const match = (!type || card.dataset.eventType === type) && (!term || searchable.get(card).includes(term));
      card.hidden = !match;
      if (match) visible += 1;
    }
    count.textContent = `显示 ${visible} / ${cards.length} 条当前页事件`;
    empty.hidden = visible !== 0;
  }
  search.addEventListener('input', filter);
  types.addEventListener('change', filter);
  document.getElementById('expand-all').addEventListener('click', () => { for (const card of cards) card.open = true; });
  document.getElementById('collapse-all').addEventListener('click', () => { for (const card of cards) card.open = false; });
  document.getElementById('clear-filters').addEventListener('click', () => { search.value = ''; types.value = ''; filter(); });
  filter();
})();"""
    script_hash = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-"
            + script_hash + "'\"><title>项目工具执行轨迹</title><style>"
            "*{box-sizing:border-box}body{font:15px/1.55 system-ui,sans-serif;background:#f4f6fa;color:#172238;max-width:1180px;margin:28px auto;padding:0 20px}"
            "h1{font-size:28px;margin:0 0 8px}p{margin:8px 0;color:#4c5970}.page-summary{font-size:14px;padding:14px 16px;background:#e7edf7;border-radius:8px}"
            "details{background:white;border:1px solid #cad2df;border-radius:9px;margin:12px 0;padding:14px 16px}summary{cursor:pointer}summary:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #5984de;outline-offset:3px}"
            ".page-info{font-size:13px;background:transparent;margin:8px 0 18px;padding:8px 12px}.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:end;padding:14px;background:#fff;border:1px solid #cad2df;border-radius:9px;margin:16px 0 8px}"
            "label{display:flex;flex-direction:column;gap:5px;font-size:13px;font-weight:600}.search-control{flex:2 1 300px}.type-control{flex:1 1 230px}input,select,button{font:inherit;border:1px solid #aab7cb;border-radius:6px;padding:8px 10px;background:#fff;color:#172238}"
            "button{cursor:pointer}button:hover{background:#eef3fc}.buttons{display:flex;gap:8px;flex-wrap:wrap}.filter-feedback{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:13px;color:#55627a;margin:10px 2px 16px}"
            ".timeline-event summary{list-style-position:outside;margin-left:16px}.event-heading{display:inline-flex;flex-wrap:wrap;gap:10px;align-items:center;font-weight:650}.sequence{font:12px ui-monospace,monospace;color:#65738a}.event-type{font-size:16px;overflow-wrap:anywhere}"
            ".badge{font-size:11px;font-weight:600;border-radius:12px;padding:2px 8px;background:#edf0f5;color:#55627a}.badge.pass{background:#e0f3e8;color:#17663c}.badge.fail{background:#ffe5e5;color:#a42020}.badge.unknown{background:#fff0d2;color:#865900}"
            ".event-meta{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:12px;color:#65738a;margin:6px 0}.subject{overflow-wrap:anywhere}.event-description{display:block;font-size:13px;color:#34445e;overflow-wrap:anywhere}.raw-label{font-size:12px;color:#65738a;margin:16px 0 4px}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,monospace;padding:14px;background:#eef2f7;border-radius:6px;max-height:34rem;overflow:auto}"
            "[hidden]{display:none!important}@media(max-width:600px){body{padding:0 12px;margin:20px auto}h1{font-size:24px}.toolbar{padding:12px}details{padding:12px}.event-type{font-size:14px}}"
            "</style></head><body><header><h1>项目工具执行轨迹</h1><p>先浏览摘要，按需展开完整记录。记录可见操作的输入、结果、操作者和版本；不记录模型隐藏推理。</p>"
            '<p class="page-summary">' + html.escape(page_text) + '</p><details class="page-info"><summary>查看分页与校验原始信息</summary><pre>'
            + html.escape(json.dumps(pagination, ensure_ascii=False, indent=2)) + '</pre></details></header>'
            '<section class="toolbar" aria-label="当前页事件筛选"><label class="search-control" for="timeline-search">搜索完整事件内容<input id="timeline-search" type="search" placeholder="输入、结果、文件、哈希或任意关键词"></label>'
            '<label class="type-control" for="timeline-type">事件类型<select id="timeline-type">' + options + '</select></label>'
            '<div class="buttons"><button id="expand-all" type="button">展开全部事件</button><button id="collapse-all" type="button">收起全部事件</button><button id="clear-filters" type="button">清除筛选</button></div></section>'
            '<div class="filter-feedback"><output id="filter-count" aria-live="polite">显示 ' + str(len(events)) + ' / ' + str(len(events))
            + ' 条当前页事件</output><span>筛选与展开仅作用当前页，不加载其他分页。</span></div>'
            '<noscript><p>筛选需要启用 JavaScript；每条完整原始记录仍可直接点击展开。</p></noscript>'
            '<p id="filter-empty" hidden>当前页没有匹配事件。可清除筛选，或使用下一游标导出后续事件。</p>'
            '<main aria-label="事件列表">' + "".join(sections) + '</main><script id="timeline-controls">' + script + '</script></body></html>')


def timeline(project: Path, after: int = 0, limit: int = 100, subject: str | None = None,
             format: str = "json", output: str | None = None) -> dict:
    if format not in ("json", "html"):
        raise ToolchainError("timeline format must be json or html")
    store = Store(project)
    page = store.events(after=after, limit=limit, subject=subject)
    if format == "json":
        return page
    events = page.get("items", page.get("events", []))
    pagination = {key: value for key, value in page.items() if key not in ("events", "items")}
    document = _timeline_html(page)
    result = {"pagination": pagination, "event_count": len(events), "html": document}
    if output is not None:
        target = safe_path(project, _text(output, "output"))
        if target.suffix.lower() != ".html" or target.name == "architecture.json":
            raise ToolchainError("timeline output must be an HTML file")
        normalized = target.relative_to(project.resolve()).as_posix().casefold()
        if normalized == "architecture/toolchain" or normalized.startswith("architecture/toolchain/"):
            raise ToolchainError("timeline output cannot overwrite toolchain metadata")
        if target.exists():
            _fail("timeline output exists; choose a new output path")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
        result["output"] = target.relative_to(project.resolve()).as_posix()
    return result


def runtime_dispatch(project: Path, architecture: str, action: str, payload: dict) -> dict:
    """Stable plain-dictionary dispatch contract used by taskarch CLI."""
    project = Path(project).resolve()
    if not isinstance(payload, dict):
        raise ToolchainError("runtime payload must be an object")
    actor, identifier = payload.get("actor"), payload.get("id")
    if action == "lease.claim":
        return claim_lease(project, architecture, actor, payload.get("modules"), payload.get("ttl_seconds", 300))
    if action in ("lease.renew", "lease.release"):
        return _lease_mutate(project, action.split(".")[1], identifier, actor, payload.get("token"),
                             payload.get("ttl_seconds", 300))
    if action == "lease.list":
        leases = Store(project).list("lease")
        return {"items": [{**item, "active": _active_lease(item)} for item in leases], "total": len(leases),
                "limitations": ["registration is not operating-system write isolation"]}
    if action == "handoff.export":
        return handoff_export(project, architecture, actor, payload.get("modules"), payload.get("next_step"),
                              payload.get("unresolved"), payload.get("constraints"), payload.get("to_actor"))
    if action == "handoff.resume":
        return handoff_resume(project, identifier, actor)
    if action in ("handoff.list", "checkpoint.list", "checkpoint.restore-list", "run.list"):
        kind = {"checkpoint.restore-list": "checkpoint-restore"}.get(action, action.split(".")[0])
        items = Store(project).list(kind)
        return {"items": items, "total": len(items)}
    if action == "run.begin":
        return run_begin(project, actor, payload.get("goal"), payload.get("breakpoints"))
    if action == "run.status":
        document = Store(project).get("run", _text(identifier, "run ID"))
        if document is None:
            raise ToolchainError("run does not exist")
        return document
    if action in ("run.step", "run.pause", "run.resume", "run.end"):
        return run_control(project, identifier, actor, action.split(".")[1], payload.get("result"),
                           payload.get("breakpoints"))
    if action == "run.guard":
        return run_guard(project, identifier, actor, payload.get("operation"), payload.get("inputs"))
    if action == "run.record":
        return run_record(project, identifier, actor, payload.get("operation_id"), payload.get("result"),
                          payload.get("status", "pass"))
    if action == "checkpoint.capture":
        return checkpoint_capture(project, architecture, actor, payload.get("label"), payload.get("files"))
    if action == "checkpoint.preview":
        return checkpoint_preview(project, _text(identifier, "checkpoint ID"))
    if action == "checkpoint.restore":
        return checkpoint_restore(project, identifier, actor, payload.get("expected_current"))
    if action == "checkpoint.recover":
        return checkpoint_recover(project, identifier, actor)
    if action == "timeline":
        return timeline(project, payload.get("after", 0), payload.get("limit", 100), payload.get("subject"),
                        payload.get("format", "json"), payload.get("output"))
    raise ToolchainError("unknown runtime operation: " + str(action))
