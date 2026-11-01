"""Project, workspace, submission, and hierarchy rules. No interactive input here."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile

from .db import KitsumaError, ROOT, connect


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise KitsumaError("Use a nonempty relative path with / separators.")
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]}
    if any(p in ("", ".", "..") or p.endswith((" ", ".")) or
           any(ord(c)<32 or c in '<>:"|?*' for c in p) or
           p.casefold() in (".kitsuma", ".git") or p.split(".")[0].upper() in reserved
           for p in value.split("/")):
        raise KitsumaError(f"Invalid workspace path: {value}")
    return value


def account(name, project):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise KitsumaError("Account names use letters, numbers, _ and - (without @project).")
    return f"{name}@{project}"


def validate_spec(spec):
    if not isinstance(spec, dict) or not re.fullmatch(r"[A-Za-z0-9_-]+", spec.get("name", "")):
        raise KitsumaError("Project name uses letters, numbers, _ and -.")
    names = [spec.get("admin", ""), *spec.get("employees", [])]
    logins = [account(n, spec["name"]) for n in names]
    if len(set(n.casefold() for n in logins)) != len(logins):
        raise KitsumaError("Admin and employee names must be distinct.")
    paths = []
    for folder in spec.get("folders", []):
        path = safe_path(folder["path"])
        if "/" in path:
            raise KitsumaError("Assign hierarchy to top-level folders; files inside may be nested.")
        hierarchy = folder["hierarchy"]
        if not hierarchy or len(set(hierarchy)) != len(hierarchy) or any(n not in names[1:] for n in hierarchy):
            raise KitsumaError(f"{path}: hierarchy must contain distinct employee names.")
        if hierarchy[-1] != folder["head"]:
            raise KitsumaError(f"{path}: the folder head must be last in the hierarchy.")
        paths.append(path)
    files = spec.get("files", {})
    if not isinstance(files, dict) or not files:
        raise KitsumaError("Provide at least one text file in files.")
    all_paths = paths + list(files)
    if len(set(p.casefold() for p in all_paths)) != len(all_paths):
        raise KitsumaError("Duplicate file/folder paths (including case differences).")
    for path, content in files.items():
        safe_path(path)
        if not isinstance(content, str) or "\0" in content:
            raise KitsumaError("Only UTF-8 text files without NUL bytes are supported.")
        if "/" in path and path.split("/")[0] not in paths:
            raise KitsumaError(f"Assign a hierarchy to the top-level folder for {path}.")
        if any(other.casefold().startswith(path.casefold()+"/") for other in all_paths):
            raise KitsumaError(f"A file cannot also be a directory: {path}")
    return logins


def create_project(spec, passwords):
    logins = validate_spec(spec)
    names = [spec["admin"], *spec.get("employees", [])]
    if set(passwords) != set(names) or any(not isinstance(p,str) or not p for p in passwords.values()):
        raise KitsumaError("Supply a nonempty password for every account.")
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            for name, login in zip(names, logins):
                cur.execute("INSERT INTO users VALUES (%s,crypt(%s,gen_salt('bf')))", (login,passwords[name]))
            cur.execute("INSERT INTO container(container_name,login) VALUES (%s,%s) RETURNING container_no", (spec["name"],logins[0]))
            cid = cur.fetchone()["container_no"]
            for folder in spec.get("folders", []):
                cur.execute("INSERT INTO folders VALUES (%s,%s)", (cid,folder["path"]))
                for rank, name in enumerate(folder["hierarchy"],1):
                    cur.execute("INSERT INTO folder_hierarchy VALUES (%s,%s,%s,%s)", (cid,folder["path"],account(name,spec["name"]),rank))
                cur.execute("INSERT INTO folder_heads VALUES (%s,%s,%s)", (cid,folder["path"],account(folder["head"],spec["name"])))
            for path, content in spec["files"].items():
                folder = path.split("/")[0] if "/" in path else None
                cur.execute("INSERT INTO file(container_no,filename,folder_path,file_content) VALUES (%s,%s,%s,%s) RETURNING fileno", (cid,path,folder,content))
                cur.execute("INSERT INTO revisions VALUES (%s,0,%s,NULL,%s,now())", (cur.fetchone()["fileno"],content,logins[0]))
        return cid
    finally:
        conn.close()


def authenticate(login, password):
    token = secrets.token_urlsafe(32)
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT login FROM users WHERE login=%s AND password=crypt(%s,password)", (login,password))
            if not cur.fetchone():
                raise KitsumaError("Invalid login or password.")
            cur.execute("INSERT INTO sessions(token_hash,user_login) VALUES (%s,%s)", (hashlib.sha256(token.encode()).hexdigest(),login))
        return token
    finally:
        conn.close()


def identity(cur, token):
    cur.execute("SELECT user_login FROM sessions WHERE token_hash=%s AND expires_at>now()", (hashlib.sha256(token.encode()).hexdigest(),))
    row = cur.fetchone()
    if not row:
        raise KitsumaError("Please log in again (session missing or expired).")
    return row["user_login"]


def project_for(cur, name, login):
    cur.execute("SELECT * FROM container WHERE container_name=%s", (name,))
    project = cur.fetchone()
    if not project:
        raise KitsumaError("Project not found.")
    if project["login"] != login:
        cur.execute("SELECT 1 FROM folder_hierarchy WHERE container_no=%s AND user_login=%s LIMIT 1", (project["container_no"],login))
        if not cur.fetchone():
            raise KitsumaError("You are not assigned to this project.")
    return project


def visible(cur, project, login):
    cur.execute("""SELECT f.* FROM file f WHERE f.container_no=%s AND
        (%s=%s OR EXISTS (SELECT 1 FROM folder_hierarchy h WHERE
        h.container_no=f.container_no AND h.folder_path=f.folder_path AND h.user_login=%s)) ORDER BY filename""",
        (project["container_no"],login,project["login"],login))
    return cur.fetchall()


def snapshot(token, name):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            login = identity(cur,token)
            project = project_for(cur,name,login)
            files = visible(cur,project,login)
            cur.execute("""SELECT folder_path FROM folders d WHERE container_no=%s AND
                (%s=%s OR EXISTS (SELECT 1 FROM folder_hierarchy h WHERE h.container_no=d.container_no
                AND h.folder_path=d.folder_path AND h.user_login=%s)) ORDER BY folder_path""",
                (project["container_no"],login,project["login"],login))
            return login,files,[r["folder_path"] for r in cur.fetchall()]
    finally:
        conn.close()


def local_file(root, path):
    root = Path(root).resolve()
    candidate = root / safe_path(path)
    if not candidate.resolve().is_relative_to(root):
        raise KitsumaError(f"Path leaves the workspace: {path}")
    if any(p.is_symlink() for p in [candidate,*candidate.parents] if p != root and p.is_relative_to(root)):
        raise KitsumaError(f"Symlinks are not supported: {path}")
    return candidate


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value,indent=2),encoding="utf-8")
    os.replace(temp,path)


def checkout(token, name, root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise KitsumaError("Clone into an empty directory; use pull in an existing workspace.")
    login,files,folders = snapshot(token,name)
    root.mkdir(parents=True,exist_ok=True)
    for folder in folders:
        local_file(root,folder).mkdir(parents=True,exist_ok=True)
    for row in files:
        path = local_file(root,row["filename"])
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(row["file_content"].encode("utf-8"))
    state = {"project":name,"login":login,"files":{r["filename"]:{"id":r["fileno"],"revision":r["revision"],"content":r["file_content"]} for r in files}}
    write_json(root/".kitsuma/workspace.json",state)
    return len(files)


def read_state(root):
    path = Path(root)/".kitsuma/workspace.json"
    if not path.exists():
        raise KitsumaError("Not a KITSUMA workspace. Clone a project first.")
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path):
    text = path.read_bytes().decode("utf-8")
    if "\0" in text:
        raise KitsumaError("Binary files are not supported.")
    return text


def changes(root):
    state = read_state(root)
    result = []
    for name,base in state["files"].items():
        path = local_file(root,name)
        status = "missing" if not path.exists() else "modified" if read_text(path) != base["content"] else "clean"
        result.append((name,status))
    return result


def pull(token, root, discard_local=False):
    state = read_state(root)
    login,files,_ = snapshot(token,state["project"])
    if login != state["login"]:
        raise KitsumaError("This workspace belongs to a different account; use its login or clone separately.")
    if set(state["files"]) != {r["filename"] for r in files}:
        raise KitsumaError("File list differs; clone into a new directory.")
    updates = []
    for row in files:
        name = row["filename"]
        path = local_file(root,name)
        if not path.is_file():
            raise KitsumaError(f"Missing local file: {name}. Restore it or clone into a new directory.")
        if not discard_local and read_text(path) not in (state["files"][name]["content"],row["file_content"]):
            raise KitsumaError(f"Unmerged local edits in {name}; pull will not overwrite them.")
        updates.append((path,row))
    for path,row in updates:
        path.write_bytes(row["file_content"].encode("utf-8"))
        state["files"][row["filename"]] = {"id":row["fileno"],"revision":row["revision"],"content":row["file_content"]}
    write_json(Path(root)/".kitsuma/workspace.json",state)
    return len(updates)


def next_reviewer(cur, project, row, author):
    if author == project["login"]:
        return author
    cur.execute("""SELECT user_login FROM folder_hierarchy WHERE container_no=%s AND folder_path=%s AND
        rank > (SELECT rank FROM folder_hierarchy WHERE container_no=%s AND folder_path=%s AND user_login=%s)
        ORDER BY rank LIMIT 1""", (project["container_no"],row["folder_path"],project["container_no"],row["folder_path"],author))
    higher = cur.fetchone()
    return higher["user_login"] if higher else project["login"]


def submit(token, root, names, message):
    if not message.strip():
        raise KitsumaError("A commit message is required.")
    state = read_state(root)
    selected = list(state["files"]) if names == ["."] else list(dict.fromkeys(names))
    if not selected or any(n not in state["files"] for n in selected):
        raise KitsumaError("Select tracked relative file paths, or . for all.")
    conn = connect()
    result = []
    try:
        with conn,conn.cursor() as cur:
            login = identity(cur,token)
            if login != state["login"]:
                raise KitsumaError("Log in as the workspace owner.")
            project = project_for(cur,state["project"],login)
            allowed = {r["filename"]:r for r in visible(cur,project,login)}
            for name in selected:
                if name not in allowed:
                    raise KitsumaError(f"Not assigned to {name}.")
                row,base = allowed[name],state["files"][name]
                cur.execute("SELECT file_content FROM revisions WHERE fileno=%s AND revision=%s", (row["fileno"],base["revision"]))
                original = cur.fetchone()
                if not original or original["file_content"] != base["content"] or row["fileno"] != base["id"]:
                    raise KitsumaError(f"Invalid workspace base for {name}; clone again.")
                content = read_text(local_file(root,name))
                if content == base["content"]:
                    continue
                cur.execute("SELECT 1 FROM pushes WHERE fileno=%s AND user_login=%s AND merged=false", (row["fileno"],login))
                if cur.fetchone():
                    raise KitsumaError(f"{name} already has your pending submission. Merge it before submitting again.")
                reviewer = next_reviewer(cur,project,row,login)
                cur.execute("""INSERT INTO pushes(fileno,base_revision,base_content,file_content,message,user_login,reviewer)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING push_id""",
                    (row["fileno"],base["revision"],base["content"],content,message,login,reviewer))
                result.append((cur.fetchone()["push_id"],name,reviewer))
        return result
    finally:
        conn.close()


def pending(token, name):
    conn = connect()
    try:
        with conn,conn.cursor() as cur:
            login = identity(cur,token)
            project = project_for(cur,name,login)
            cur.execute("""SELECT p.*,f.filename FROM pushes p JOIN file f USING(fileno)
                WHERE f.container_no=%s AND p.merged=false AND (%s=%s OR p.user_login=%s OR p.reviewer=%s)
                ORDER BY push_id""", (project["container_no"],login,project["login"],login,login))
            return cur.fetchall()
    finally:
        conn.close()


def show(token, push_id):
    conn = connect()
    try:
        with conn,conn.cursor() as cur:
            login = identity(cur,token)
            cur.execute("""SELECT p.*,f.filename,f.file_content AS current_content,c.login AS admin
                FROM pushes p JOIN file f USING(fileno) JOIN container c USING(container_no)
                WHERE push_id=%s""", (push_id,))
            row = cur.fetchone()
            if not row or login not in (row["user_login"],row["reviewer"],row["admin"]):
                raise KitsumaError("Submission not found or not assigned to you.")
            return row
    finally:
        conn.close()


def load_push(cur, token, push_id, lock=False):
    login = identity(cur,token)
    cur.execute("""SELECT p.*,f.container_no,f.folder_path,f.filename,f.revision,
        f.file_content AS current_content,c.login AS admin FROM pushes p JOIN file f USING(fileno)
        JOIN container c USING(container_no) WHERE p.push_id=%s"""+(" FOR UPDATE OF p,f" if lock else ""), (push_id,))
    row = cur.fetchone()
    if not row or login not in (row["reviewer"],row["admin"]):
        raise KitsumaError("Submission not found or you are not its current reviewer.")
    if row["merged"]:
        raise KitsumaError("Submission is already merged.")
    cur.execute("SELECT user_login FROM folder_heads WHERE container_no=%s AND folder_path=%s", (row["container_no"],row["folder_path"]))
    head = cur.fetchone()
    final = login == row["admin"] or (head and login == head["user_login"])
    return login,row,bool(final)


def review(token, push_id):
    conn = connect()
    try:
        with conn,conn.cursor() as cur:
            login,row,final = load_push(cur,token,push_id,True)
            if final:
                raise KitsumaError("You are the final reviewer. Use merge to save this submission.")
            reviewer = next_reviewer(cur,{"container_no":row["container_no"],"login":row["admin"]},row,login)
            cur.execute("INSERT INTO push_reviews(push_id,user_login) VALUES (%s,%s)", (push_id,login))
            cur.execute("UPDATE pushes SET reviewer=%s WHERE push_id=%s", (reviewer,push_id))
            return reviewer
    finally:
        conn.close()


def merge_text(base, submitted, current):
    if submitted == current or current == base:
        return submitted
    if submitted == base:
        return current
    executable = ROOT/"build"/("update.exe" if os.name == "nt" else "update")
    if not executable.exists():
        raise KitsumaError("Build the merge tool first: python build.py")
    with tempfile.TemporaryDirectory(prefix="kitsuma-merge-") as directory:
        paths = [Path(directory)/n for n in ("base.txt","submitted.txt","current.txt","merged.txt")]
        for path,text in zip(paths,(base,submitted,current)):
            path.write_bytes(text.encode("utf-8"))
        print("Merge: A = submitted changes; B = current shared version.",flush=True)
        subprocess.run([str(executable),*map(str,paths)],check=True)
        return read_text(paths[3])


def merge(token, push_id):
    conn = connect()
    try:
        with conn,conn.cursor() as cur:
            _,row,final = load_push(cur,token,push_id)
            if not final:
                raise KitsumaError("Approve with review first; only the folder head/admin saves the shared version.")
        result = merge_text(row["base_content"],row["file_content"],row["current_content"])
        with conn,conn.cursor() as cur:
            login,latest,final = load_push(cur,token,push_id,True)
            if not final or latest["revision"] != row["revision"]:
                raise KitsumaError("Shared version changed during review. Run merge again.")
            version = row["revision"]+1
            cur.execute("UPDATE file SET file_content=%s,revision=%s WHERE fileno=%s", (result,version,row["fileno"]))
            cur.execute("INSERT INTO revisions(fileno,revision,file_content,push_id,merged_by) VALUES (%s,%s,%s,%s,%s)", (row["fileno"],version,result,push_id,login))
            cur.execute("UPDATE pushes SET merged=true,merged_by=%s,merged_at=now() WHERE push_id=%s", (login,push_id))
        return version
    finally:
        conn.close()


def history(token, name):
    conn = connect()
    try:
        with conn,conn.cursor() as cur:
            login = identity(cur,token)
            project = project_for(cur,name,login)
            ids = [r["fileno"] for r in visible(cur,project,login)]
            cur.execute("""SELECT r.revision,f.filename,r.merged_by,r.created_at,p.message FROM revisions r
                JOIN file f USING(fileno) LEFT JOIN pushes p USING(push_id)
                WHERE r.fileno=ANY(%s) ORDER BY r.created_at,r.fileno,r.revision""", (ids,))
            return cur.fetchall()
    finally:
        conn.close()
