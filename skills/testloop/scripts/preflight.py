#!/usr/bin/env python3
"""Check the skills testloop drives, before a cycle starts.

install.sh checks this too, but only at install time and only advisorily — it
prints a TODO and exits 0. That is the wrong place for it to bind. Someone who
installs testloop alone gets a working `/testloop`, and the gap does not surface
until step 1 asks for `/validation` and it is not there.

What happens then is the failure this script exists to prevent. Nothing in the
workflow says what to do about an absent `/validation`, so the matrix gets
written freehand instead — and a matrix written by the same model that then
executes it is the self-certifying loop the skill was built to rule out. C, D
and E do not notice: they read `results.json` and a matrix that parses, and they
will render five correctly-named documents and a confident verdict on top of a
plan nobody validated.

So the check runs at the start of the cycle, and a missing `/validation` exits
non-zero.

  python3 preflight.py            # check, print what to install
  python3 preflight.py --json     # same, machine-readable
"""

import argparse
import json
import sys
from pathlib import Path

MARKETPLACE = {
    "validation": ("MattTheCoder556/validation-skill", "validation@validation-skill"),
    "howto": ("MattTheCoder556/howto-skill", "howto@howto-skill"),
}


def find_skill(name):
    """Resolve a skill to the copy that will ACTUALLY load, or None.

    Same resolution order as install.sh, and for the same reason: the plugin
    cache keeps every version ever installed, so scanning it picks an arbitrary
    one. Ask installed_plugins.json which version is active, and fall back to
    the newest cached copy only when the plugin is not registered at all.
    """
    home = Path.home()

    candidate = home / ".claude" / "skills" / name / "SKILL.md"
    if candidate.is_file():
        return candidate

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
                        return root / rel

    cache = home / ".claude" / "plugins" / "cache"
    if not cache.is_dir():
        return None

    def version_key(path):
        try:
            return tuple(int(p) for p in path.parent.name.split("."))
        except ValueError:
            return (0,)

    hits = sorted(cache.glob(f"*/{name}/*/skills/{name}/SKILL.md"),
                  key=version_key, reverse=True)
    return hits[0] if hits else None


def install_lines(name):
    repo, plugin = MARKETPLACE[name]
    return [f"/plugin marketplace add {repo}", f"/plugin install {plugin}"]


def check():
    validation = find_skill("validation")
    registry = None
    if validation:
        candidate = validation.parent / "reference" / "modules.md"
        registry = candidate if candidate.is_file() else None
    howto = find_skill("howto")
    return {
        "validation": str(validation) if validation else None,
        "registry": str(registry) if registry else None,
        "howto": str(howto) if howto else None,
        "ok": validation is not None,
    }


def report(state):
    print("testloop preflight\n")

    if state["validation"]:
        print(f"  [ok  ] /validation — {state['validation']}")
        if state["registry"]:
            print("  [ok  ] module registry present")
        else:
            print("  [warn] no reference/modules.md beside it — module names "
                  "cannot be checked against the registry")
    else:
        print("  [STOP] /validation NOT installed.\n")
        print("         testloop drives /validation to produce document A; it does")
        print("         not contain a matrix generator of its own. Writing the")
        print("         matrix freehand instead is not a fallback — the results")
        print("         would be executed against a plan the same model invented,")
        print("         which is the self-certifying loop this skill exists to")
        print("         prevent. Install it, then start the cycle again:\n")
        for line in install_lines("validation"):
            print(f"           {line}")
        print()

    if state["howto"]:
        print(f"  [ok  ] /howto — {state['howto']}")
    else:
        print("  [warn] /howto not installed. C, D and E still run, but document B")
        print("         is not produced and nothing in the iteration tests whether")
        print("         a person can follow the module unaided. Install it with:\n")
        for line in install_lines("howto"):
            print(f"           {line}")
        print()

    print()
    if state["ok"]:
        print("Ready." if state["registry"] and state["howto"]
              else "Ready, with the warnings above — say them to the user before starting.")
    else:
        print("Not ready. Stop here and give the user the commands above.")


def main():
    parser = argparse.ArgumentParser(
        description="Check that the skills testloop drives are installed.")
    parser.add_argument("--json", action="store_true",
                        help="emit the result as JSON instead of prose")
    args = parser.parse_args()

    state = check()
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        report(state)
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
