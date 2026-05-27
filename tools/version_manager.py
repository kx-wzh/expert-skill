#!/usr/bin/env python3
"""
Expert skill version manager.

Archives and restores generated expert skill artifacts.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from skill_schema import now_iso

MAX_VERSIONS = 10


def list_versions(skill_dir: Path) -> list[dict]:
    """List all archived versions for a skill directory."""
    versions_dir = skill_dir / "versions"
    if not versions_dir.is_dir():
        return []
    result = []
    for v_dir in sorted(versions_dir.iterdir()):
        if not v_dir.is_dir():
            continue
        info = {"version": v_dir.name, "path": str(v_dir)}
        info_path = v_dir / "_info.json"
        if info_path.exists():
            try:
                info.update(json.loads(info_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError):
                pass
        result.append(info)
    return result


def backup(skill_dir: Path) -> str | None:
    """Archive current version. Returns version name or None if nothing to backup."""
    if not skill_dir.is_dir():
        print(f"Skill directory not found: {skill_dir}", file=sys.stderr)
        return None

    versions_dir = skill_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    existing = list_versions(skill_dir)
    if existing:
        last_num = max(
            int(v["version"][1:]) if v["version"].startswith("v") else 0
            for v in existing
        )
    else:
        last_num = 0
    version_name = f"v{last_num + 1}"
    backup_dir = versions_dir / version_name
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Copy all artifacts except versions dir itself
    for item in skill_dir.iterdir():
        if item.name == "versions":
            continue
        dest = backup_dir / item.name
        if item.is_dir():
            if not dest.exists():
                shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    info = {
        "version": version_name,
        "backed_up_at": now_iso(),
        "artifacts_copied": [str(p.name) for p in backup_dir.iterdir()],
    }
    (backup_dir / "_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    # Prune old versions
    pruned = sorted(versions_dir.iterdir(), key=lambda p: p.name)
    while len([p for p in pruned if p.is_dir()]) > MAX_VERSIONS:
        oldest = pruned.pop(0)
        if oldest.is_dir() and oldest.name != version_name:
            shutil.rmtree(oldest)

    return version_name


def rollback(skill_dir: Path, version: str) -> bool:
    """Restore a specific version. Returns True on success."""
    backup_dir = skill_dir / "versions" / version
    if not backup_dir.is_dir():
        print(f"Version {version} not found in {skill_dir}", file=sys.stderr)
        return False

    # Backup current state first
    backup(skill_dir)

    # Remove current artifacts (except versions)
    for item in list(skill_dir.iterdir()):
        if item.name == "versions":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Restore from backup
    for item in backup_dir.iterdir():
        if item.name.startswith("_"):
            continue
        dest = skill_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    return True


def main():
    parser = argparse.ArgumentParser(description="Expert Skill Version Manager")
    parser.add_argument("--action", choices=["backup", "rollback", "list"], required=True)
    parser.add_argument("--slug", required=True, help="Skill slug")
    parser.add_argument("--base-dir", default="./skills/expert", help="Base directory")
    parser.add_argument("--version", help="Version to rollback to")
    args = parser.parse_args()

    skill_dir = Path(args.base_dir) / args.slug

    if args.action == "list":
        versions = list_versions(skill_dir)
        if versions:
            for v in versions:
                when = v.get("backed_up_at", "?")
                print(f"  {v['version']} — {when}")
        else:
            print(f"  (no versions for {args.slug})")
        return

    if args.action == "backup":
        version = backup(skill_dir)
        if version:
            print(f"Backed up {args.slug} as version {version}")
        else:
            print("Backup failed.", file=sys.stderr)
            sys.exit(1)

    elif args.action == "rollback":
        if not args.version:
            parser.error("--version is required for rollback")
        success = rollback(skill_dir, args.version)
        if success:
            print(f"Rolled back {args.slug} to version {args.version}")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
