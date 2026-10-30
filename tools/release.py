#!/usr/bin/env python3
"""Cut a release of the addon.

    python tools/release.py            zip the version the .toc carries now (no git)
    python tools/release.py patch      bump 1.0.0-forever -> 1.0.1-forever, commit, tag, zip
    python tools/release.py minor      -> 1.1.0-forever
    python tools/release.py major      -> 2.0.0-forever
    python tools/release.py 1.2.3      set that version (an optional -suffix is kept)

The version is the "## Version:" line of HealerStatWeights.toc: MAJOR.MINOR.PATCH with an
optional -suffix that bumps keep. A bump needs a clean working tree; it commits the .toc as
"release: <version>" and tags it v<version>. The zip lands in dist/HealerStatWeights-<version>.zip
and unpacks to a single HealerStatWeights/ folder holding only what the client loads. Next to it,
dist/HealerStatWeights-<version>-notes.md lists the commits since the previous v* tag.
"""
import datetime
import pathlib
import re
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDON = "HealerStatWeights"
TOC = ROOT / f"{ADDON}.toc"
DIST = ROOT / "dist"

# What the client needs: the .toc, what it and embeds.xml load, the AddOns-list icon, licence and readme.
SHIP_FILES = [f"{ADDON}.toc", "embeds.xml", "icon.png", "Core.lua", "DisplayPanel.lua", "Events.lua", "LICENSE", "README.md"]
SHIP_DIRS = ["Classes", "Parsers", "Libs"]
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}

VERSION_RE = re.compile(r"^(## Version:\s*)(\d+)\.(\d+)\.(\d+)(-[\w.]+)?\s*$", re.M)


def version_match(text):
    m = VERSION_RE.search(text)
    if not m:
        raise SystemExit(f"{TOC.name}: no '## Version: X.Y.Z' line")
    return m


def current_version():
    text = TOC.read_text(encoding="utf-8")
    m = version_match(text)
    return text[m.start(2):m.end()].rstrip()


def bump(version, part):
    """New version string: `part` is major|minor|patch or an explicit X.Y.Z[-suffix]."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(-[\w.]+)?", version)
    major, minor, patch, suffix = int(m[1]), int(m[2]), int(m[3]), m[4] or ""
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    elif part == "patch":
        patch += 1
    else:
        e = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(-[\w.]+)?", part)
        if not e:
            raise SystemExit(f"not a version or bump: {part!r} (want major, minor, patch or X.Y.Z[-suffix])")
        major, minor, patch = int(e[1]), int(e[2]), int(e[3])
        suffix = e[4] or suffix
    return f"{major}.{minor}.{patch}{suffix}"


def set_version(part):
    text = TOC.read_text(encoding="utf-8")
    m = version_match(text)
    old = text[m.start(2):m.end()].rstrip()
    new = bump(old, part)
    TOC.write_text(text[:m.start(2)] + new + text[m.end():], encoding="utf-8")
    return old, new


def git(*args, root=None):
    return subprocess.run(["git", *args], cwd=root or ROOT, check=True, capture_output=True, text=True).stdout


def require_clean_tree(root=None):
    if git("status", "--porcelain", root=root).strip():
        raise SystemExit("working tree not clean: commit or stash first")


def commit_and_tag(version, root=None, toc=None):
    tag = f"v{version}"
    if git("tag", "--list", tag, root=root).strip():
        raise SystemExit(f"tag {tag} already exists")
    git("add", (toc or TOC).name, root=root)
    git("commit", "-m", f"release: {version}", root=root)
    git("tag", tag, root=root)
    return tag


def previous_tag(version, root=None):
    """Newest v* tag other than this version's own, or None for a first release."""
    for tag in git("tag", "--list", "v*", "--sort=-v:refname", root=root).split():
        if tag != f"v{version}":
            return tag
    return None


NOTE_GROUPS = [("feat", "Features"), ("fix", "Fixes"), ("data", "Data"), (None, "Other")]
NOTE_SKIP = {"test", "chore", "release"}   # not news to a player
SUBJECT_RE = re.compile(r"^(\w+)(?:\([^)]*\))?!?:\s*(.*)$")   # conventional "type(scope): text"


def group_subjects(subjects):
    """{heading: [text, ...]} in NOTE_GROUPS order; test/chore/release commits dropped, prefixes stripped."""
    groups = {heading: [] for _, heading in NOTE_GROUPS}
    headings = {kind: heading for kind, heading in NOTE_GROUPS}
    for s in subjects:
        m = SUBJECT_RE.match(s)
        kind, text = (m[1], m[2]) if m else (None, s)
        if kind in NOTE_SKIP:
            continue
        groups[headings.get(kind, "Other")].append(text if kind in headings else s)
    return {h: items for h, items in groups.items() if items}


def write_notes(version, dist=DIST, root=None):
    """dist/HealerStatWeights-<version>-notes.md: commits since the previous release, grouped by type."""
    prev = previous_tag(version, root=root)
    head = f"v{version}" if git("tag", "--list", f"v{version}", root=root).strip() else "HEAD"
    rng = f"{prev}..{head}" if prev else head
    groups = group_subjects(git("log", "--no-merges", "--reverse", "--format=%s", rng, root=root).splitlines())
    since = f"since {prev}" if prev else "first release"
    lines = [f"# {ADDON} {version}", "", f"{datetime.date.today().isoformat()}, {since}"]
    for heading, items in groups.items():
        lines += ["", f"## {heading}", ""] + [f"- {t}" for t in items]
    if not groups:
        lines += ["", "- no changes"]
    dist.mkdir(exist_ok=True)
    out = dist / f"{ADDON}-{version}-notes.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def shipped_files():
    """(archive path, source path) for every file in the release, archive paths under ADDON/."""
    out = []
    for name in SHIP_FILES:
        out.append((f"{ADDON}/{name}", ROOT / name))
    for d in SHIP_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and not (SKIP_NAMES & set(p.relative_to(ROOT).parts)):
                out.append((f"{ADDON}/{p.relative_to(ROOT).as_posix()}", p))
    return out


def check_toc_covered(files):
    """Every file the .toc loads must be in the release (a new top-level Lua file needs SHIP_FILES)."""
    shipped = {a for a, _ in files}
    for line in TOC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if f"{ADDON}/{line.replace(chr(92), '/')}" not in shipped:
            raise SystemExit(f"{TOC.name} loads {line} but the release does not ship it: add it to SHIP_FILES/SHIP_DIRS")


def build(version, dist=DIST):
    files = shipped_files()
    for _, src in files:
        if not src.is_file():
            raise SystemExit(f"missing: {src.relative_to(ROOT)}")
    check_toc_covered(files)
    dist.mkdir(exist_ok=True)
    out = dist / f"{ADDON}-{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in files:
            z.write(src, arc)
    return out, len(files)


def main(argv):
    if len(argv) > 1:
        return print(__doc__) or 2
    if argv:
        require_clean_tree()
        old, new = set_version(argv[0])
        tag = commit_and_tag(new)
        print(f"{TOC.name}: {old} -> {new}, committed and tagged {tag}")
    version = current_version()
    out, n = build(version)
    print(f"wrote {out.relative_to(ROOT)}: {n} files")
    notes = write_notes(version)
    print(f"wrote {notes.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
