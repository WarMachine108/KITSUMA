"""A small executable college demo. Creates only a new uniquely named project."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from kitsuma import core  # noqa: E402
from kitsuma.db import initialize  # noqa: E402


def main():
    initialize()
    spec=json.loads((ROOT/"examples/project.json").read_text())
    spec["name"]="Demo_"+uuid.uuid4().hex[:8]
    print("KITSUMA: two employees, ranked review, and a real conflict",flush=True)
    core.create_project(spec,{name:"demo-only-password" for name in ("admin","alice","bob","head")})
    tokens={name:core.authenticate(name+"@"+spec["name"],"demo-only-password") for name in ("admin","alice","bob","head")}
    with tempfile.TemporaryDirectory(prefix="kitsuma-demo-") as directory:
        roots={name:Path(directory)/name for name in ("alice","bob")}
        for name in roots:
            core.checkout(tokens[name],spec["name"],roots[name])
        print("1. Created project, accounts, and src hierarchy: alice -> bob -> head.",flush=True)
        print("2. Both employees cloned volume = 10; admin-only README is hidden.",flush=True)
        assert not (roots["alice"]/"README.txt").exists()
        ids={}
        for name,volume in (("alice",20),("bob",30)):
            (roots[name]/"src/player.txt").write_text(f"volume = {volume}\nplaying = false\n",encoding="utf-8",newline="")
            rows=core.submit(tokens[name],roots[name],["."] if name=="bob" else ["src/player.txt"],f"{name} changes volume")
            ids[name]=rows[0][0]
        print("3. Alice submitted one file; Bob submitted all changed files. Shared volume is still 10.",flush=True)
        assert next(r for r in core.snapshot(tokens["admin"],spec["name"])[1] if r["filename"]=="src/player.txt")["revision"]==0
        core.review(tokens["bob"],ids["alice"])
        print("4. Bob approved Alice's submission and forwarded it to Head.",flush=True)
        assert core.merge(tokens["head"],ids["alice"])==1
        print("5. Head merged Alice: shared volume = 20, revision 1.",flush=True)
        session=Path(directory)/"session"
        core.write_json(session/"session.json",{"token":tokens["head"]})
        env=dict(os.environ,KITSUMA_SESSION_DIR=str(session))
        executable=ROOT/"build"/("kitsuma.exe" if os.name=="nt" else "kitsuma")
        print("6. Head merges Bob through C++ launcher -> Python -> C++ merge UI. Choose A (Bob).",flush=True)
        result=subprocess.run([str(executable),"merge",str(ids["bob"])],input="a\ny\ny\ny\n",text=True,capture_output=True,env=env,check=True)
        # Strip ANSI color for a readable captured transcript.
        import re
        output=re.sub(r"\x1b\[[0-9;]*m","",result.stdout)
        # Temporary paths are intentionally omitted from the lasting transcript.
        for line in output.splitlines():
            if "base: " not in line and "Merge complete ->" not in line:
                print(line)
        assert "CONFLICT" in output
        for name in roots:
            core.pull(tokens[name],roots[name],discard_local=name=="alice")
            assert (roots[name]/"src/player.txt").read_text()=="volume = 30\nplaying = false\n"
            assert all(status=="clean" for _,status in core.changes(roots[name]))
        assert not core.pending(tokens["admin"],spec["name"])
        print("7. Both employees pulled volume = 30, revision 2; working copies are clean.")
        print("8. Pending queue empty. Revision history retains original, Alice's merge, and Bob's merge.")
        print("DEMO PASSED")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
