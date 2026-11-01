"""Run real integration tests in a disposable local PostgreSQL cluster.

Never reads DATABASE_URL and never contacts Render/Supabase. Requires local
PostgreSQL binaries (set PG_BIN if they aren't on PATH or in Program Files).
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    subprocess.run([sys.executable,str(ROOT/"build.py")],check=True)
    merge_test=ROOT/"build"/("merge_tests.exe" if os.name=="nt" else "merge_tests")
    subprocess.run([os.environ.get("CXX","g++"),"-std=c++17","-Wall","-Wextra","-Werror","-O2",str(ROOT/"tests/merge_tests.cpp"),"-o",str(merge_test)],check=True)
    subprocess.run([str(merge_test)],check=True)
    found=shutil.which("initdb")
    candidates=sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin/initdb.exe")) if os.name=="nt" else []
    pg_bin=Path(os.environ["PG_BIN"]) if "PG_BIN" in os.environ else Path(found or (candidates[-1] if candidates else "initdb")).parent
    suffix=".exe" if os.name=="nt" else ""
    flags={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
    def run(name,*args,**kwargs):
        return subprocess.run([str(pg_bin/(name+suffix)),*map(str,args)],check=True,**flags,**kwargs)
    with tempfile.TemporaryDirectory(prefix="kitsuma-postgres-") as directory:
        data=Path(directory)/"data"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            port=sock.getsockname()[1]
        run("initdb","-D",data,"-U","postgres","--auth=trust","--no-locale","-E","UTF8",stdout=subprocess.DEVNULL)
        started=False
        try:
            run("pg_ctl","-D",data,"-l",Path(directory)/"postgres.log","-o",f"-h 127.0.0.1 -p {port}","-w","start",stdout=subprocess.DEVNULL)
            started=True
            env=dict(os.environ,KITSUMA_TEST_DATABASE_URL=f"postgresql://postgres@127.0.0.1:{port}/postgres")
            result=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-v"],cwd=ROOT,env=env)
            if result.returncode==0 and "--demo" in sys.argv:
                env["DATABASE_URL"]=env["KITSUMA_TEST_DATABASE_URL"]
                demo=subprocess.run([sys.executable,str(ROOT/"scripts/demo.py")],cwd=ROOT,env=env,text=True,capture_output=True)
                print(demo.stdout,end="")
                if demo.stderr:
                    print(demo.stderr,file=sys.stderr)
                return demo.returncode
            return result.returncode
        finally:
            if started:
                run("pg_ctl","-D",data,"-m","fast","-w","stop",stdout=subprocess.DEVNULL)


if __name__=="__main__":
    raise SystemExit(main())
