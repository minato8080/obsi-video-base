#!/usr/bin/env python3
"""Generate Obsidian MD notes and thumbnails from MP4 files."""

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

THUMB_POINTS = {"fp10": 10, "fp50": 50, "fp80": 80}
THUMB_FALLBACK_SECS = {"fp10": 0.5, "fp50": 2.5, "fp80": 5.0}


def check_deps():
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run([tool, "-version"], capture_output=True, check=True)
        except FileNotFoundError:
            sys.exit(f"Error: '{tool}' not found. Install ffmpeg from https://ffmpeg.org/")


def get_duration(mp4: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(mp4),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_thumb(mp4: Path, out: Path, pos_sec: float) -> bool:
    r = subprocess.run(
        [
            "ffmpeg", "-ss", f"{pos_sec:.3f}", "-i", str(mp4),
            "-vframes", "1", "-vf", "scale=640:-2", "-q:v", "3", "-y", str(out),
        ],
        capture_output=True,
    )
    return r.returncode == 0 and out.exists()


HASH_CHUNK = 128 * 1024  # 128KB

def make_id(mp4: Path) -> str:
    h = hashlib.sha256()
    with mp4.open("rb") as f:
        h.update(f.read(HASH_CHUNK))
        f.seek(-min(HASH_CHUNK, mp4.stat().st_size), 2)
        h.update(f.read(HASH_CHUNK))
    return h.hexdigest()[:12]


def update_md_if_changed(md_path: Path, title: str, src: str, folder: str, mp4_name: str) -> bool:
    content = md_path.read_text(encoding="utf-8")
    updated = content
    updated = re.sub(r'^(title: ).*$',  rf'\g<1>{title}',  updated, flags=re.MULTILINE)
    updated = re.sub(r'^(source: ).*$', rf'\g<1>{src}',    updated, flags=re.MULTILINE)
    updated = re.sub(r'^(folder: ).*$', rf'\g<1>{folder}', updated, flags=re.MULTILINE)
    updated = re.sub(r'(?<!!)\[\[[^\]]+\.mp4\]\]', f'[[{mp4_name}]]', updated)
    updated = re.sub(r'!\[\[[^\]]+\.mp4\]\]',      f'![[{mp4_name}]]', updated)
    if updated == content:
        return False
    md_path.write_text(updated, encoding="utf-8")
    return True


def process(mp4: Path, video_root: Path, obsidian_dir: Path, force: bool, vid_id: str) -> str:
    rel = mp4.relative_to(video_root)

    title = mp4.stem
    folder = rel.parent.as_posix()
    if folder == ".":
        folder = ""

    # paths relative from obsidian/metadata/{id}.md  (../../ = video root)
    if folder:
        src = f"../../{folder}/{mp4.name}"
    else:
        src = f"../../{mp4.name}"

    md_path = obsidian_dir / "metadata" / f"{vid_id}.md"
    thumb_dir = obsidian_dir / "thumb"
    thumb_dir.mkdir(exist_ok=True)

    # サムネイルの欠損チェック（MDの有無に関係なく実行）
    missing = [(l, p) for l, p in THUMB_POINTS.items()
               if not (thumb_dir / f"{vid_id}-{l}.jpg").exists() or force]

    duration = get_duration(mp4) if (missing or not md_path.exists() or force) else 0.0

    for label, pct in missing:
        out = thumb_dir / f"{vid_id}-{label}.jpg"
        pos = (duration * pct / 100) if duration > 0 else THUMB_FALLBACK_SECS[label]
        ok = extract_thumb(mp4, out, pos)
        if not ok:
            print(f"\n    warn: thumbnail@{label} failed for {mp4.name}", end="")

    if md_path.exists() and not force:
        if update_md_if_changed(md_path, title, src, folder, mp4.name):
            return "updated"
        return "skip"

    thumbs = {label: f"../thumb/{vid_id}-{label}.jpg" for label in THUMB_POINTS}
    today = date.today().isoformat()

    md = (
        f"---\n"
        f"id: {vid_id}\n"
        f"type: video\n"
        f"title: {title}\n"
        f"source: {src}\n"
        f"thumb: fp10\n"
        f"folder: {folder}\n"
        f"duration: {int(duration)}\n"
        f"created: {today}\n"
        f"tags: []\n"
        f"---\n"
        f"\n"
        f"# {title}\n"
        f"\n"
        f"## Preview\n"
        f"\n"
        f"![[{thumbs['fp10']}]]\n"
        f"![[{thumbs['fp50']}]]\n"
        f"![[{thumbs['fp80']}]]\n"
        f"\n"
        f"## Video\n"
        f"\n"
        f"[[{mp4.name}]]\n"
        f"![[{mp4.name}]]\n"
        f"\n"
    )

    md_path.parent.mkdir(exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    return "created"


def main():
    ap = argparse.ArgumentParser(description="Generate Obsidian MD notes from MP4 files")
    ap.add_argument("--force", action="store_true", help="Overwrite existing MD files and thumbnails")
    ap.add_argument("--dry-run", action="store_true", help="List targets without generating")
    ap.add_argument("--video-root", default="..", help="Path to video root (default: ..)")
    args = ap.parse_args()

    obsidian_dir = Path(__file__).parent.parent.resolve()
    video_root = (obsidian_dir / args.video_root).resolve()

    if not video_root.exists():
        sys.exit(f"Error: video root not found: {video_root}")

    if not args.dry_run:
        check_deps()

    mp4s = sorted(p for p in video_root.rglob("*.mp4") if obsidian_dir not in p.parents)
    if not mp4s:
        print("No MP4 files found.")
        return

    print(f"Found {len(mp4s)} MP4 file(s)\n")
    counts = {"created": 0, "updated": 0, "skip": 0, "error": 0}
    valid_ids: set[str] = set()

    # Phase 1: MP4 処理
    for mp4 in mp4s:
        rel_label = mp4.relative_to(video_root).as_posix()
        print(f"  {rel_label} ... ", end="", flush=True)
        try:
            vid_id = make_id(mp4)
            valid_ids.add(vid_id)
            if args.dry_run:
                exists = (obsidian_dir / "metadata" / f"{vid_id}.md").exists()
                print("skip (dry-run)" if exists else "would create (dry-run)")
                continue
            result = process(mp4, video_root, obsidian_dir, args.force, vid_id)
            print(result)
            counts[result] = counts.get(result, 0) + 1
        except Exception as e:
            print(f"ERROR: {e}")
            counts["error"] += 1

    # Phase 2: 孤立ファイルの削除
    metadata_dir = obsidian_dir / "metadata"
    thumb_dir = obsidian_dir / "thumb"
    orphans = [p for p in metadata_dir.glob("*.md") if p.stem not in valid_ids] if metadata_dir.exists() else []

    if orphans:
        print(f"\nOrphaned files ({len(orphans)}):")
        for md_file in orphans:
            thumbs = [thumb_dir / f"{md_file.stem}-{label}.jpg" for label in THUMB_POINTS]
            if args.dry_run:
                print(f"  [dry-run] would delete: {md_file.name}")
                for t in thumbs:
                    if t.exists():
                        print(f"  [dry-run] would delete: {t.name}")
            else:
                md_file.unlink()
                print(f"  deleted: {md_file.name}")
                for t in thumbs:
                    if t.exists():
                        t.unlink()
                        print(f"  deleted: {t.name}")

    if not args.dry_run:
        total = sum(counts.values())
        print(f"\n{total} file(s) — created: {counts['created']}, updated: {counts['updated']}, skipped: {counts['skip']}, errors: {counts['error']}, orphans deleted: {len(orphans)}")


if __name__ == "__main__":
    main()
