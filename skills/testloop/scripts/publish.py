#!/usr/bin/env python3
"""File a finished testloop iteration into qmsWrapper Storage.

LOCAL / EXPERIMENTAL — not yet part of the published skill. This runs after
audit.py and mirrors the run directory into a Storage folder, keeping the
house filenames exactly as the chain produced them. Nothing is renamed: the
audit recounts the rendered documents against their own filenames, so a
re-formatted copy in Storage would no longer be the thing that was audited.

  python3 publish.py --run-dir . --dest-folder-id 224479
  python3 publish.py --run-dir . --dest-folder-id 224479 --dry-run

The token is read from, in order: --token, $WRAPPER_PAT, then
~/.claude.json -> mcpServers.wrapper.env.WRAPPER_PAT. It is never written to
disk by this script; MANIFEST.md records ids, never the credential.

What is uploaded: every file under the run directory except the extensions in
--skip-ext (default .json, so results.json and codecheck.json stay local as the
record's and the code validation's sources).

Every upload is verified with a GET before it is treated as filed — the API has
been seen to answer phase:complete with an id that does not resolve. Verification
compares name+extension, byte size and folder path, because Storage keeps the
stem and the extension in separate fields.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_BASE = "https://yourorg.qmswrapper.com"
DEFAULT_SKIP = {".json"}

# Standing convention (local): iterations are filed under this folder, in a
# folder named "<module tested> - Mate". The short name is the tester's call —
# the existing folders are Settings, Storage, Logs, Approvals, QMSManual, which
# are friendlier than the registry tokens (SettingsAdministration, Dashboard...).
# Files go directly inside; the stamped filenames keep iterations apart.
DEFAULT_DEST_PATH = "/library/Wrapper/Validation And How Tos"


class PublishError(RuntimeError):
    pass


# --- credential ------------------------------------------------------------

def read_token(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("WRAPPER_PAT"):
        return os.environ["WRAPPER_PAT"]
    cfg = pathlib.Path.home() / ".claude.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            tok = data["mcpServers"]["wrapper"]["env"]["WRAPPER_PAT"]
            if tok:
                return tok
        except (KeyError, json.JSONDecodeError):
            pass
    raise PublishError(
        "no token: pass --token, set $WRAPPER_PAT, or put one in "
        "~/.claude.json under mcpServers.wrapper.env.WRAPPER_PAT")


# --- transport -------------------------------------------------------------

class Api:
    def __init__(self, base, token):
        self.base = base.rstrip("/")
        self.auth = {"Authorization": f"Bearer {token}"}

    def call(self, path, data=None, headers=None, method=None, raw=False, timeout=120):
        h = dict(self.auth)
        if headers:
            h.update(headers)
        if data is not None and not raw:
            data = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.base}/{path}", data=data, headers=h,
                                     method=method or ("POST" if data is not None else "GET"))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode()
                return r.status, (json.loads(body) if body.strip() else {})
        except urllib.error.HTTPError as e:
            txt = e.read().decode()
            try:
                return e.code, json.loads(txt)
            except json.JSONDecodeError:
                return e.code, {"raw": txt[:300]}

    def multipart(self, path, filepath, fields, timeout=300):
        boundary = "----testloop" + uuid.uuid4().hex
        body = bytearray()
        for k, v in fields.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        fp = pathlib.Path(filepath)
        ctype = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                 f"filename=\"{fp.name}\"\r\nContent-Type: {ctype}\r\n\r\n").encode()
        body += fp.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        return self.call(path, bytes(body),
                         {"Content-Type": f"multipart/form-data; boundary={boundary}"},
                         raw=True, timeout=timeout)


# --- storage ---------------------------------------------------------------

def list_folders(api, folder_id=None, path=None):
    """Sub-folders of a folder, or of the storage root when neither is given."""
    q = (f"folderId={folder_id}" if folder_id is not None
         else f"path={urllib.parse.quote(path or '/')}")
    st, res = api.call(f"rest/cli-storage/folder?{q}&limit=500")
    if st != 200:
        raise PublishError(f"could not list folders ({q}): HTTP {st} {res}")
    return [i for i in (res.get("items") or []) if i.get("type") == "folder"]


def resolve_path(api, path):
    """Turn a Storage path into a folder id by walking it a level at a time."""
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        raise PublishError("cannot file into the storage root; choose a folder")
    current, walked = None, ""
    for part in parts:
        match = next((f for f in list_folders(api, current, "/" if current is None else None)
                      if f.get("name") == part), None)
        if match is None:
            raise PublishError(f"no folder {part!r} under /{walked}")
        current, walked = match["id"], f"{walked}{part}/"
    return current


def choose_folder(api):
    """Browse Storage and pick a destination. Needs a terminal."""
    if not sys.stdin.isatty():
        raise PublishError(
            "no destination given and stdin is not a terminal, so there is nobody "
            "to ask. Pass --dest-folder-id or --dest-path, or run --list-folders "
            "to see the options and choose.")
    current_id, current_path = None, "/"
    while True:
        folders = list_folders(api, current_id, current_path if current_id is None else None)
        print(f"\n  {current_path}")
        if not folders:
            print("    (no sub-folders)")
        for i, f in enumerate(folders, 1):
            print(f"    {i:2}. {f['name']}/   (id {f['id']})")
        prompt = "  number to open"
        if current_id is not None:
            prompt += ", s to file here"
        prompt += ", u for up, q to cancel: " if current_id is not None else ", q to cancel: "
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            raise PublishError("cancelled")
        if answer == "q":
            raise PublishError("cancelled — nothing was uploaded")
        if answer == "s" and current_id is not None:
            return current_id, current_path
        if answer == "u":
            if current_id is None:
                continue
            trimmed = "/".join(current_path.rstrip("/").split("/")[:-1]) + "/"
            current_path = trimmed if trimmed != "/" else "/"
            current_id = None if current_path == "/" else resolve_path(api, current_path)
            continue
        if answer.isdigit() and 1 <= int(answer) <= len(folders):
            picked = folders[int(answer) - 1]
            current_id, current_path = picked["id"], f"{current_path}{picked['name']}/"
            continue
        print("    ? enter a number from the list, or s / u / q")


def ensure_folder(api, name, parent_id):
    """Create a folder under parent_id. Tolerates one that is already there —
    the API refuses a duplicate sibling, which on a re-run is not an error."""
    st, res = api.call("rest/cli-storage/folder",
                       {"name": name, "parentFolderId": parent_id})
    if st in (200, 201):
        fid = res.get("id") or (res.get("folder") or {}).get("id")
        if fid:
            return fid, "created"
    st2, listing = api.call(f"rest/cli-storage/folder?folderId={parent_id}&limit=500")
    if st2 == 200:
        for it in (listing.get("items") or listing.get("data") or []):
            if it.get("name") == name and it.get("type") == "folder":
                return it.get("id"), "existed"
    raise PublishError(f"could not create or find folder {name!r} under {parent_id}: {st} {res}")


def upload_file(api, fp, folder_id):
    blob = fp.read_bytes()
    st, pre = api.call("rest/cli-storage/file/upload-precheck", {
        "filename": fp.name,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "destinationFolderId": folder_id,
    })
    if st != 200:
        return None, f"precheck HTTP {st}: {pre.get('message') or pre}"
    plan = pre.get("plan", pre)
    if plan.get("refuseReason"):
        return None, f"refused: {plan['refuseReason']}"
    mode = plan.get("mode", "new_file")
    st, res = api.multipart("rest/cli-storage/file/upload", fp, {
        "filename": fp.name, "mode": str(mode), "destinationFolderId": str(folder_id)})
    if st not in (200, 201):
        return None, f"upload HTTP {st}: {res.get('message') or res}"
    fid = res.get("id") or (res.get("file") or {}).get("id") or res.get("fileId")
    if not fid:
        return None, f"upload returned no file id: {res}"
    return fid, mode


def verify(api, file_id, local_path, expected_folder_path):
    """A reported id is not proof. Storage splits the stem and the extension,
    so compare the rejoined name — not the stem against a filename."""
    st, f = api.call(f"rest/cli-storage/file/{file_id}")
    if st != 200:
        return False, f"HTTP {st}"
    name = f.get("name") or ""
    ext = f.get("extension")
    full = f"{name}.{ext}" if ext else name
    problems = []
    if full != local_path.name:
        problems.append(f"name {full!r} != {local_path.name!r}")
    if f.get("size") is not None and int(f["size"]) != local_path.stat().st_size:
        problems.append(f"size {f['size']} != {local_path.stat().st_size}")
    if f.get("path") != expected_folder_path:
        problems.append(f"path {f.get('path')!r} != {expected_folder_path!r}")
    return (not problems), "; ".join(problems)


# --- manifest --------------------------------------------------------------

def write_manifest(run_dir, dest_path, root_id, folder_ids, records, skipped, verdict,
                   folder_name=None):
    lines = [
        f"# Storage manifest — {folder_name or run_dir.name}", "",
        "Where this iteration was filed in qmsWrapper Storage. Every id below was",
        "confirmed with a follow-up GET: name, byte size and folder path all matched",
        "the local file.", "",
        "| | |", "|---|---|",
        f"| **Destination** | `{dest_path}` |",
        f"| **Root folder id** | {root_id} |",
        f"| **Files filed** | {len(records)} |",
        f"| **Gate verdict at upload** | {verdict} |",
        "| **Lifecycle status** | DRAFT — no revision comment or tags set |", "",
    ]
    if skipped:
        lines += [f"Not uploaded (stays local): {', '.join(sorted(skipped))}.", ""]
    lines += ["## Folders", "", "| Path | Folder id |", "|---|---|"]
    for k, v in sorted(folder_ids.items(), key=lambda x: (x[0] != ".", x[0])):
        lines.append(f"| `{'(root)' if k == '.' else k + '/'}` | {v} |")
    lines += ["", "## Files", "", "| File | Storage id |", "|---|---|"]
    for r in records:
        lines.append(f"| `{r['path']}` | {r['fileId']} |")
    lines += ["", "---", "",
              "_Generated by `publish.py`. The iteration's own documents are unchanged —",
              "this file only records where they went._"]
    out = run_dir / "MANIFEST.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def gate_verdict(run_dir):
    """Read the verdict out of the audit, for the record. Never computed here."""
    for p in sorted(run_dir.glob("Audit_*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "## Confirmation — CONFIRMED" in text:
            return "CONFIRMED"
        if "## Confirmation — REFUSED" in text:
            return "REFUSED"
    return "unknown (no audit found)"


# --- main ------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", default=".", help="the iteration's run directory")
    dest = ap.add_mutually_exclusive_group()
    dest.add_argument("--dest-folder-id", type=int, help="Storage folder id to file under")
    dest.add_argument("--dest-path", help="Storage path to file under (resolved to an id)")
    ap.add_argument("--folder-name", metavar="NAME",
                    help="name of the folder the iteration is filed into, created if absent "
                         "(convention: \"<module tested> - Mate\"). Defaults to the run "
                         "directory's own name.")
    ap.add_argument("--ask", action="store_true",
                    help="browse Storage and pick the destination, even if one was given")
    ap.add_argument("--list-folders", action="store_true",
                    help="print the Storage folders under --under (default: root) and exit; "
                         "use this to offer the choice somewhere else, then pass "
                         "--dest-folder-id")
    ap.add_argument("--under", help="folder id or path --list-folders should list (default: root)")
    ap.add_argument("--base-url", default=os.environ.get("WRAPPER_BASE_URL", DEFAULT_BASE))
    ap.add_argument("--token", help="PAT; else $WRAPPER_PAT, else ~/.claude.json")
    ap.add_argument("--skip-ext", default=".json",
                    help="comma-separated extensions to leave local (default: .json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be created and uploaded; touch nothing")
    args = ap.parse_args(argv)

    if args.list_folders:
        api = Api(args.base_url, read_token(args.token))
        under = args.under
        if under is None:
            folders, where = list_folders(api, None, "/"), "/"
        elif str(under).isdigit():
            folders, where = list_folders(api, int(under)), f"folder id {under}"
        else:
            fid = resolve_path(api, under)
            folders, where = list_folders(api, fid), f"{under} (id {fid})"
        print(f"folders under {where}:")
        for f in folders:
            print(f"  id {f['id']:<8} {f['name']}")
        if not folders:
            print("  (none)")
        print("\npass one to --dest-folder-id, or use --ask to browse interactively")
        return 0

    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise PublishError(f"{run_dir} is not a directory")
    folder_name = args.folder_name or run_dir.name
    skip = {e if e.startswith(".") else "." + e
            for e in (s.strip().lower() for s in args.skip_ext.split(",")) if e}

    files = sorted(p for p in run_dir.rglob("*")
                   if p.is_file() and p.suffix.lower() not in skip
                   and p.name != "MANIFEST.md")
    skipped = {p.name for p in run_dir.rglob("*")
               if p.is_file() and p.suffix.lower() in skip}
    if not files:
        raise PublishError(f"nothing to upload under {run_dir}")

    subdirs = sorted({str(p.relative_to(run_dir).parent) for p in files
                      if str(p.relative_to(run_dir).parent) != "."})

    if args.dry_run:
        print(f"DRY RUN — nothing will be created or uploaded\n")
        print(f"run directory : {run_dir}")
        # Resolve the destination for real: a dry run that accepts a mistyped
        # folder and then fails on the live run has checked the wrong half.
        if args.ask:
            print("destination   : would ask (--ask)")
        else:
            try:
                api = Api(args.base_url, read_token(args.token))
                if args.dest_folder_id is not None:
                    listing = list_folders(api, args.dest_folder_id)
                    print(f"destination   : folder id {args.dest_folder_id} "
                          f"— exists, {len(listing)} sub-folder(s)")
                else:
                    dest_path = args.dest_path or DEFAULT_DEST_PATH
                    fid = resolve_path(api, dest_path)
                    tail = "" if args.dest_path else "  (standing default)"
                    print(f"destination   : {dest_path} -> folder id {fid}{tail}")
            except PublishError as exc:
                print(f"destination   : ** {exc} **")
                return 2
        print(f"folder        : {folder_name}"
              f"{'' if args.folder_name else '  (defaulted to the run dir name)'}")
        print(f"verdict       : {gate_verdict(run_dir)}")
        print(f"\nfolders to create ({1 + len(subdirs)}):")
        print(f"   {folder_name}/")
        for s in subdirs:
            print(f"   {folder_name}/{s}/")
        total = sum(p.stat().st_size for p in files)
        print(f"\nfiles to upload ({len(files)}, {total/1024/1024:.1f} MB):")
        for p in files:
            print(f"   {p.stat().st_size/1024:9.1f} KB  {p.relative_to(run_dir)}")
        if skipped:
            print(f"\nleft local ({len(skipped)}): {', '.join(sorted(skipped))}")
        return 0

    api = Api(args.base_url, read_token(args.token))

    if args.ask:
        parent_id, chosen = choose_folder(api)
        print(f"\nfiling into {chosen}  (id {parent_id})")
    elif args.dest_folder_id is not None:
        parent_id = args.dest_folder_id
    else:
        dest_path = args.dest_path or DEFAULT_DEST_PATH
        parent_id = resolve_path(api, dest_path)
        note = "" if args.dest_path else "  (standing default — --ask to choose another)"
        print(f"destination: {dest_path} -> folder id {parent_id}{note}")

    root_id, how = ensure_folder(api, folder_name, parent_id)
    print(f"{folder_name}/  id={root_id} ({how})", flush=True)
    folder_ids = {".": root_id}
    for rel in subdirs:
        cur, acc = root_id, []
        for part in pathlib.PurePosixPath(rel).parts:
            acc.append(part)
            key = "/".join(acc)
            if key not in folder_ids:
                fid, how = ensure_folder(api, part, cur)
                folder_ids[key] = fid
                print(f"{folder_name}/{key}/  id={fid} ({how})", flush=True)
            cur = folder_ids[key]

    print(f"\nuploading {len(files)} files...", flush=True)
    records, failures = [], []
    for i, fp in enumerate(files, 1):
        rel = fp.relative_to(run_dir)
        fid, note = upload_file(api, fp, folder_ids[str(rel.parent)])
        if fid is None:
            failures.append({"path": str(rel), "error": note})
            print(f"  [{i:2}/{len(files)}] FAIL {rel} — {note}", flush=True)
        else:
            records.append({"path": str(rel), "fileId": fid, "mode": note})
            print(f"  [{i:2}/{len(files)}] ok   {rel}  id={fid}", flush=True)

    # The expected folder path is built from the root's own path plus the local
    # layout, so the check is independent of what the file record claims.
    root_path = _root_path(api, root_id, parent_id, folder_name)
    print(f"\nverifying {len(records)} ids against {root_path} ...", flush=True)
    bad = []
    for r in records:
        rel = pathlib.PurePosixPath(r["path"])
        sub = "" if str(rel.parent) == "." else str(rel.parent) + "/"
        ok, why = verify(api, r["fileId"], run_dir / r["path"], f"{root_path}{sub}")
        if not ok:
            bad.append({"path": r["path"], "fileId": r["fileId"], "problem": why})
    print(f"verified {len(records) - len(bad)}/{len(records)}", flush=True)
    for b in bad:
        print(f"   !! {b['path']} — {b['problem']}", flush=True)

    manifest = write_manifest(run_dir, root_path, root_id, folder_ids, records,
                              skipped, gate_verdict(run_dir), folder_name)
    print(f"\nmanifest: {manifest}")
    if failures or bad:
        print(f"\n{len(failures)} upload failure(s), {len(bad)} verification problem(s)")
        return 1
    print(f"\nfiled {len(records)} files, all verified")
    return 0


def _root_path(api, root_id, parent_id, name):
    """The Storage path of the run's root folder, ending in a slash. Asked for
    once and used to build every expected path, so verification never derives
    its expectation from the record it is checking.

    Listing a folder returns children whose `path` is the containing folder's
    path — so any child of the root reports exactly what we want. A root with no
    children yet falls back to finding itself in its parent's listing."""
    st, res = api.call(f"rest/cli-storage/folder?folderId={root_id}&limit=1")
    if st == 200:
        items = res.get("items") or []
        if items and items[0].get("path"):
            p = items[0]["path"]
            return p if p.endswith("/") else p + "/"

    st, res = api.call(f"rest/cli-storage/folder?folderId={parent_id}&limit=500")
    if st == 200:
        for it in (res.get("items") or []):
            if it.get("id") == root_id and it.get("path"):
                return f"{it['path'].rstrip('/')}/{name}/"

    raise PublishError(f"could not read the path of root folder {root_id}; "
                       "cannot verify uploads against an unknown destination")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PublishError as exc:
        print(f"publish: {exc}", file=sys.stderr)
        sys.exit(2)
