"""Console UI shared by the C++ launchers and python load.py."""
import argparse
import getpass
import json
import os
import difflib
from pathlib import Path
import subprocess
import sys

import psycopg2

from . import core
from .db import KitsumaError, ROOT, initialize


def session_path():
    return Path(os.environ.get("KITSUMA_SESSION_DIR", ROOT / ".kitsuma")) / "session.json"


def token():
    if not session_path().exists():
        raise KitsumaError("Log in first: kitsuma login <user@project>")
    return json.loads(session_path().read_text(encoding="utf-8"))["token"]


def login_user(login):
    value = core.authenticate(login, getpass.getpass("Password: "))
    core.write_json(session_path(), {"login": login, "token": value})
    print(f"Logged in as {login}.")


def interactive_spec():
    print("Create a project. Rank employees from first contributor to folder head.")
    name = input("Project name: ").strip()
    admin = input("Admin name (without @project): ").strip()
    employees = input("Employee names, separated by spaces: ").split()
    folders = []
    while True:
        folder = input("Top-level folder (blank to finish): ").strip()
        if not folder:
            break
        hierarchy = input(f"Employees for {folder}, in rank order (head last): ").split()
        if not hierarchy:
            raise KitsumaError("Every folder needs at least one employee.")
        folders.append({"path": folder, "hierarchy": hierarchy, "head": hierarchy[-1]})
    files = {}
    print("Files start empty. Use full relative paths, e.g. src/player.cpp.")
    while True:
        path = input("File path (blank to finish): ").strip()
        if not path:
            break
        if path in files:
            raise KitsumaError("Duplicate file path.")
        files[path] = ""
    return {"name": name, "admin": admin, "employees": employees, "folders": folders, "files": files}


def create(spec_path=None):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8")) if spec_path else interactive_spec()
    core.validate_spec(spec)
    passwords = {name: getpass.getpass(f"Password for {core.account(name, spec['name'])}: ")
                 for name in [spec["admin"], *spec.get("employees", [])]}
    core.create_project(spec, passwords)
    value = core.authenticate(core.account(spec["admin"], spec["name"]), passwords[spec["admin"]])
    core.write_json(session_path(), {"login": core.account(spec["admin"], spec["name"]), "token": value})
    print(f"Created {spec['name']}; admin is logged in. Clone it to start working.")


def parser():
    result = argparse.ArgumentParser(description="KITSUMA - hierarchy based mini-git for text files")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("db-init", help="Initialize a fresh PostgreSQL database")
    init = commands.add_parser("init", help="Create accounts, files and folder hierarchy")
    init.add_argument("--spec", help="Project JSON; passwords are prompted, never stored in it")
    login = commands.add_parser("login")
    login.add_argument("login", help="employee@project")
    commands.add_parser("logout")
    commands.add_parser("menu", help="Interactive signup/login entry point")
    clone = commands.add_parser("clone", help="Download assigned files into an empty directory")
    clone.add_argument("project")
    clone.add_argument("directory")
    for name in ("status", "pull"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--workspace", default=".")
        if name == "pull":
            cmd.add_argument("--discard-local", action="store_true", help="Explicitly replace local edits with the shared version after a conflict resolution")
    add = commands.add_parser("add", help="Submit changed tracked files for hierarchical review")
    add.add_argument("files", nargs="+", help="Relative paths, or . for all")
    add.add_argument("-m", "--message", required=True)
    add.add_argument("--workspace", default=".")
    for name in ("pending", "log"):
        cmd = commands.add_parser(name)
        cmd.add_argument("project")
    for name in ("review", "merge", "show"):
        cmd = commands.add_parser(name)
        cmd.add_argument("push_id", type=int)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "db-init":
            initialize()
            print("Database ready (schema version 1).")
        elif args.command == "init":
            create(args.spec)
        elif args.command == "login":
            login_user(args.login)
        elif args.command == "logout":
            if session_path().exists():
                from .db import connect
                conn = connect()
                try:
                    with conn, conn.cursor() as cur:
                        cur.execute("DELETE FROM sessions WHERE token_hash=%s", (core.hashlib.sha256(token().encode()).hexdigest(),))
                finally:
                    conn.close()
                session_path().unlink()
            print("Logged out.")
        elif args.command == "menu":
            choice = input("KITSUMA: [S]ignup/create project or [L]ogin: ").strip().lower()
            if choice == "s":
                create()
            elif choice == "l":
                login_user(input("Login (user@project): ").strip())
            else:
                raise KitsumaError("Choose S or L.")
        elif args.command == "clone":
            print(f"Cloned {core.checkout(token(), args.project, args.directory)} assigned files into {Path(args.directory).resolve()}.")
        elif args.command == "status":
            state = core.read_state(args.workspace)
            print(f"{state['project']} / {state['login']}")
            for name, status in core.changes(args.workspace):
                print(f"{status:9} {name}")
        elif args.command == "pull":
            print(f"Updated {core.pull(token(), args.workspace, args.discard_local)} files. Local base revisions refreshed.")
        elif args.command == "add":
            rows = core.submit(token(), args.workspace, args.files, args.message)
            for push_id, name, reviewer in rows:
                print(f"Submitted #{push_id}: {name} -> {reviewer}")
            if not rows:
                print("No changed tracked files to submit.")
        elif args.command == "pending":
            rows = core.pending(token(), args.project)
            for row in rows:
                print(f"#{row['push_id']} {row['filename']} | {row['user_login']} -> {row['reviewer']} | {row['message']}")
            if not rows:
                print("No pending submissions visible to your account.")
        elif args.command == "review":
            print(f"Approved #{args.push_id}; forwarded to {core.review(token(), args.push_id)}.")
        elif args.command == "show":
            row = core.show(token(), args.push_id)
            print(f"#{row['push_id']} {row['filename']} | {row['message']} | reviewer: {row['reviewer']}")
            print("".join(difflib.unified_diff(row['base_content'].splitlines(True), row['file_content'].splitlines(True), fromfile="base", tofile="submitted")))
            if row['current_content'] != row['base_content']:
                print("Shared version has changed since this submission's base:")
                print(row['current_content'])
        elif args.command == "merge":
            print(f"Merged #{args.push_id} as revision {core.merge(token(), args.push_id)}. Run pull to refresh your workspace.")
        elif args.command == "log":
            for row in core.history(token(), args.project):
                print(f"r{row['revision']} {row['filename']} | {row['merged_by']} | {row['message'] or 'Initial version'}")
        return 0
    except psycopg2.IntegrityError:
        print("Error: duplicate project/account/submission or invalid relationship. No changes from this operation were saved.", file=sys.stderr)
    except psycopg2.Error as error:
        # Do not print connection strings/passwords from configuration.
        print(f"Database error ({type(error).__name__}). Check DATABASE_URL, connectivity, and db-init.", file=sys.stderr)
    except (KitsumaError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No unresolved merge was saved.", file=sys.stderr)
    return 1
