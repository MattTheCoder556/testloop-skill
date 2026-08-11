#!/usr/bin/env bash
# Install testloop on this machine.
#
# Idempotent: safe to re-run to upgrade. Reports everything outstanding in one
# pass rather than stopping at the first gap.
#
#   ./install.sh              install the skill and check its dependencies
#   ./install.sh --check      check only, change nothing
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skills/testloop"
DEST="$HOME/.claude/skills/testloop"
CHECK_ONLY=0

while [ $# -gt 0 ]; do
	case "$1" in
		--check) CHECK_ONLY=1; shift ;;
		-h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "unknown option: $1" >&2; exit 2 ;;
	esac
done

say()  { printf '  %s\n' "$*"; }
todo() { printf '  TODO  %s\n' "$*"; TODOS=$((TODOS+1)); }
TODOS=0

echo "testloop installer"
echo

# --- 1. python + openpyxl --------------------------------------------------
echo "Python"
if ! command -v python3 >/dev/null; then
	todo "python3 not found — install it, nothing here works without it"
else
	say "$(python3 --version)"
	if ! python3 -c "import openpyxl" 2>/dev/null; then
		if [ "$CHECK_ONLY" -eq 1 ]; then
			todo "openpyxl missing — pip install --user openpyxl"
		elif python3 -m pip install --user --quiet openpyxl 2>/dev/null; then
			say "installed openpyxl"
		else
			todo "openpyxl missing — pip install --user openpyxl"
		fi
	else
		say "openpyxl present"
	fi
fi

# --- 2. skill --------------------------------------------------------------
echo
echo "Skill"
if [ ! -d "$SRC" ]; then
	echo "  ERROR: $SRC not found — run this from the testloop-skill checkout" >&2
	exit 1
fi
if [ "$CHECK_ONLY" -eq 1 ]; then
	[ -f "$DEST/SKILL.md" ] && say "installed at $DEST" || todo "not installed — run without --check"
else
	mkdir -p "$DEST"
	if command -v rsync >/dev/null; then
		rsync -a --delete --exclude __pycache__ "$SRC"/ "$DEST"/
	else
		rm -rf "$DEST" && mkdir -p "$DEST" && cp -r "$SRC"/. "$DEST"/
		rm -rf "$DEST/scripts/__pycache__"
	fi
	say "installed to $DEST"
fi

# --- 3. the skills it drives ------------------------------------------------
# testloop does not replace /validation and /howto, it sequences them. Without
# /validation there is no module registry and no matrix to execute, so the loop
# has nothing to start from — that is a hard dependency, not a nice-to-have.
echo
echo "Skills it drives"
# Resolve a skill to the copy that will ACTUALLY load. The plugin cache keeps
# every version ever installed, so scanning it picks an arbitrary one — here
# that meant reporting a missing module registry that the live 2.2.0 has. Ask
# installed_plugins.json which version is active instead, and only fall back to
# the newest cached copy when the plugin is not registered at all.
find_skill() {  # $1 = skill name -> prints the SKILL.md path, or nothing
	python3 - "$1" <<'PY'
import json, sys
from pathlib import Path

name = sys.argv[1]
home = Path.home()

candidate = home / ".claude" / "skills" / name / "SKILL.md"
if candidate.is_file():
    print(candidate); raise SystemExit

installed = home / ".claude" / "plugins" / "installed_plugins.json"
if installed.is_file():
    try:
        plugins = json.loads(installed.read_text()).get("plugins", {})
    except (json.JSONDecodeError, OSError):
        plugins = {}
    for key, entries in plugins.items():
        if key.split("@")[0] != name:
            continue
        for entry in entries:
            root = Path(entry.get("installPath", ""))
            for rel in (f"skills/{name}/SKILL.md", "SKILL.md"):
                if (root / rel).is_file():
                    print(root / rel); raise SystemExit

cache = home / ".claude" / "plugins" / "cache"
def version_key(path):
    try:
        return tuple(int(p) for p in path.parent.name.split("."))
    except ValueError:
        return (0,)
hits = sorted(cache.glob(f"*/{name}/*/skills/{name}/SKILL.md"),
              key=version_key, reverse=True) if cache.is_dir() else []
if hits:
    print(hits[0])
PY
}

VALIDATION="$(find_skill validation)"
if [ -n "$VALIDATION" ]; then
	say "/validation found — $VALIDATION"
	REG="$(dirname "$VALIDATION")/reference/modules.md"
	[ -f "$REG" ] && say "module registry present" \
		|| todo "no reference/modules.md beside it — module names cannot be checked"
else
	todo "/validation NOT found. testloop cannot produce document A without it."
	todo "  /plugin marketplace add MattTheCoder556/validation-skill"
	todo "  /plugin install validation@validation-skill"
fi

HOWTO="$(find_skill howto)"
if [ -n "$HOWTO" ]; then
	say "/howto found — $HOWTO"
else
	todo "/howto NOT found. Document B (the user guide) cannot be produced;"
	todo "the rest of the loop still runs, but nothing tests whether a person"
	todo "can actually follow the module unaided."
fi

# --- 4. smoke test ----------------------------------------------------------
echo
echo "Scripts"
if [ -f "$DEST/scripts/reconcile.py" ]; then
	ALL_OK=1
	for s in build_results reconcile audit; do
		python3 "$DEST/scripts/$s.py" --help >/dev/null 2>&1 || { todo "$s.py does not run"; ALL_OK=0; }
	done
	[ "$ALL_OK" -eq 1 ] && say "build_results / reconcile / audit all runnable"
else
	todo "scripts not present at $DEST/scripts"
fi

# --- 5. done ----------------------------------------------------------------
echo
if [ "$TODOS" -eq 0 ]; then
	echo "Ready. Start a cycle with /testloop, or read $DEST/SKILL.md"
else
	echo "$TODOS thing(s) left above. Re-run, or check with:  ./install.sh --check"
fi
