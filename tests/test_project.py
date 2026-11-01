"""Real PostgreSQL integration tests, isolated in a new schema per test."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg2
from psycopg2.extensions import make_dsn

from kitsuma import core
from kitsuma.db import KitsumaError, ROOT, initialize


class ValidationTests(unittest.TestCase):
    def test_unsafe_paths(self):
        for path in ("../oops", "/absolute", "C:/oops", "src/../oops", "src//a", "src\\a", ".kitsuma/token", "NUL.txt"):
            with self.subTest(path=path), self.assertRaises(KitsumaError):
                core.safe_path(path)

    def test_head_must_finish_hierarchy(self):
        spec = json.loads((ROOT/"examples/project.json").read_text())
        spec["folders"][0]["head"] = "alice"
        with self.assertRaises(KitsumaError):
            core.validate_spec(spec)


class MergeExecutableTests(unittest.TestCase):
    def run_merge(self, base, a, b, answers="", missing=False):
        executable=ROOT/"build"/("update.exe" if os.name=="nt" else "update")
        if not executable.exists():
            self.skipTest("Run python build.py first")
        with tempfile.TemporaryDirectory(prefix="kitsuma-merge-test-") as directory:
            paths=[Path(directory)/name for name in ("base","a","b","output")]
            for path,content in zip(paths,(base,a,b)):
                path.write_bytes(content)
            if missing:
                paths[1].unlink()
            result=subprocess.run([str(executable),*map(str,paths)],input=answers,text=True,capture_output=True)
            output=paths[3].read_bytes() if paths[3].exists() else None
            return result,output

    def test_empty_files(self):
        result,output=self.run_merge(b"",b"",b"")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(output,b"")

    def test_missing_input_fails_without_output(self):
        result,output=self.run_merge(b"x",b"x",b"x",missing=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIsNone(output)

    def test_eof_cancels_conflict_without_output(self):
        result,output=self.run_merge(b"x\n",b"a\n",b"b\n")
        self.assertNotEqual(result.returncode,0)
        self.assertIsNone(output)

    def test_line_endings_and_final_newline_preserved(self):
        result,output=self.run_merge(b"x\r\nlast",b"new\r\nlast",b"x\r\nlast","typo\ny\n")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("Use y or n",result.stdout)
        self.assertEqual(output,b"new\r\nlast")


@unittest.skipUnless(os.environ.get("KITSUMA_TEST_DATABASE_URL"), "Use python scripts/test_local.py for isolated real-PostgreSQL tests")
class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.base_url = os.environ["KITSUMA_TEST_DATABASE_URL"]
        self.schema = "kitsuma_test_"+uuid.uuid4().hex
        conn = psycopg2.connect(self.base_url)
        try:
            with conn,conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
                cur.execute(f'CREATE SCHEMA "{self.schema}"')
        finally:
            conn.close()
        self.environment = patch.dict(os.environ, {"DATABASE_URL":make_dsn(self.base_url,options=f"-c search_path={self.schema},public")})
        self.environment.start()
        self.addCleanup(self.cleanup_schema)
        initialize()
        self.spec = json.loads((ROOT/"examples/project.json").read_text())
        self.spec["folders"].append({"path":"private","hierarchy":["head"],"head":"head"})
        self.spec["files"]["private/player.txt"] = "private\n"
        core.create_project(self.spec, {n:"test-password" for n in ("admin","alice","bob","head")})
        self.tokens = {n:core.authenticate(n+"@MusicPlayer","test-password") for n in ("admin","alice","bob","head")}
        self.temp = tempfile.TemporaryDirectory(prefix="kitsuma-test-")
        self.addCleanup(self.temp.cleanup)

    def cleanup_schema(self):
        self.environment.stop()
        conn = psycopg2.connect(self.base_url)
        try:
            with conn,conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        finally:
            conn.close()

    def clone(self, user):
        path = Path(self.temp.name)/user
        core.checkout(self.tokens[user],"MusicPlayer",path)
        return path

    def edit_submit(self, user, text, all_files=False):
        root = self.clone(user)
        (root/"src/player.txt").write_text(text,encoding="utf-8",newline="")
        return root,core.submit(self.tokens[user],root,["."] if all_files else ["src/player.txt"],"Test change")

    def test_schema_reapply_and_atomic_duplicate_project(self):
        initialize()
        with self.assertRaises(psycopg2.IntegrityError):
            core.create_project(self.spec,{n:"pw" for n in ("admin","alice","bob","head")})
        self.assertEqual(len(core.snapshot(self.tokens["admin"],"MusicPlayer")[1]),4)

    def test_login_and_folder_visibility(self):
        with self.assertRaises(KitsumaError):
            core.authenticate("alice@MusicPlayer","wrong")
        with self.assertRaises(KitsumaError):
            core.snapshot("forged-token","MusicPlayer")
        root = self.clone("alice")
        self.assertFalse((root/"README.txt").exists())
        self.assertFalse((root/"private/player.txt").exists())
        self.assertTrue((root/"src/player.txt").exists())
        self.assertEqual(core.changes(root),[("src/notes.txt","clean"),("src/player.txt","clean")])

    def test_hierarchy_review_merge_pull(self):
        root,rows = self.edit_submit("alice","volume = 20\nplaying = false\n")
        pid = rows[0][0]
        self.assertEqual(rows[0][2],"bob@MusicPlayer")
        self.assertFalse(core.pending(self.tokens["alice"],"MusicPlayer")[0]["merged"])
        with self.assertRaises(KitsumaError):
            core.merge(self.tokens["alice"],pid)
        with self.assertRaises(KitsumaError):
            core.merge(self.tokens["head"],pid)
        self.assertEqual(core.review(self.tokens["bob"],pid),"head@MusicPlayer")
        self.assertEqual(core.merge(self.tokens["head"],pid),1)
        core.pull(self.tokens["alice"],root)
        self.assertEqual(core.changes(root)[1][1],"clean")
        self.assertFalse(core.pending(self.tokens["admin"],"MusicPlayer"))
        with self.assertRaises(KitsumaError):
            core.merge(self.tokens["head"],pid)

    def test_all_files_submission_and_duplicates(self):
        root = self.clone("alice")
        (root/"src/player.txt").write_text("changed\n")
        (root/"src/notes.txt").write_text("more notes\n")
        rows=core.submit(self.tokens["alice"],root,["."],"Both files")
        self.assertEqual(len(rows),2)
        with self.assertRaises(KitsumaError):
            core.submit(self.tokens["alice"],root,["."],"Duplicate")
        self.assertEqual(len(core.pending(self.tokens["admin"],"MusicPlayer")),2)

    def test_missing_file_rolls_back_whole_submission(self):
        root = self.clone("alice")
        (root/"src/notes.txt").write_text("changed\n")
        (root/"src/player.txt").unlink()
        with self.assertRaises(OSError):
            core.submit(self.tokens["alice"],root,["."],"Must roll back")
        self.assertFalse(core.pending(self.tokens["admin"],"MusicPlayer"))

    def test_pull_preserves_edits_and_rejects_wrong_account(self):
        root,_=self.edit_submit("alice","my unsaved change\n")
        with self.assertRaises(KitsumaError):
            core.pull(self.tokens["alice"],root)
        self.assertEqual((root/"src/player.txt").read_text(),"my unsaved change\n")
        with self.assertRaises(KitsumaError):
            core.pull(self.tokens["bob"],root)
        core.pull(self.tokens["alice"],root,discard_local=True)
        self.assertEqual((root/"src/player.txt").read_text(),self.spec["files"]["src/player.txt"])

    def test_same_filename_isolated_by_project_and_folder(self):
        spec=copy.deepcopy(self.spec)
        spec["name"]="Other"
        spec["files"]["src/player.txt"]="Other project\n"
        core.create_project(spec,{n:"pw" for n in ("admin","alice","bob","head")})
        other=core.authenticate("alice@Other","pw")
        self.assertEqual(core.snapshot(other,"Other")[1][1]["file_content"],"Other project\n")
        with self.assertRaises(KitsumaError):
            core.snapshot(other,"MusicPlayer")
        root=self.clone("head")
        self.assertEqual((root/"private/player.txt").read_text(),"private\n")
        self.assertNotEqual((root/"private/player.txt").read_text(),(root/"src/player.txt").read_text())

    def test_concurrent_submissions_keep_base_and_use_cpp_merge(self):
        a,arows=self.edit_submit("alice","volume = 20\nplaying = false\n")
        b,brows=self.edit_submit("bob","volume = 30\nplaying = false\n",True)
        core.review(self.tokens["bob"],arows[0][0])
        core.merge(self.tokens["head"],arows[0][0])
        # Exercise the real C++ conflict UI via the Python CLI, choosing A (Bob).
        session=Path(self.temp.name)/"session"
        core.write_json(session/"session.json",{"token":self.tokens["head"]})
        env=dict(os.environ,KITSUMA_SESSION_DIR=str(session))
        result=subprocess.run([sys.executable,str(ROOT/"load.py"),"merge",str(brows[0][0])],input="a\ny\ny\ny\n",text=True,capture_output=True,env=env)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("CONFLICT",result.stdout)
        core.pull(self.tokens["alice"],a,discard_local=True)
        core.pull(self.tokens["bob"],b)
        self.assertEqual((a/"src/player.txt").read_text(),"volume = 30\nplaying = false\n")
        self.assertEqual(core.read_state(b)["files"]["src/player.txt"]["revision"],2)
        history=[r for r in core.history(self.tokens["admin"],"MusicPlayer") if r["filename"]=="src/player.txt"]
        self.assertEqual([r["revision"] for r in history],[0,1,2])

    def test_merge_rechecks_revision_before_saving(self):
        _,rows=self.edit_submit("bob","new\n")
        def someone_else_merges(*args):
            from kitsuma.db import connect
            conn=connect()
            try:
                with conn,conn.cursor() as cur:
                    cur.execute("UPDATE file SET revision=revision+1 WHERE filename='src/player.txt'")
            finally:
                conn.close()
            return "my result\n"
        with patch("kitsuma.core.merge_text",side_effect=someone_else_merges):
            with self.assertRaises(KitsumaError):
                core.merge(self.tokens["head"],rows[0][0])
        self.assertEqual(len(core.pending(self.tokens["head"],"MusicPlayer")),1)

    def test_cpp_commands_work_outside_repository(self):
        executable=ROOT/"build"/("kitsuma.exe" if os.name=="nt" else "kitsuma")
        if not executable.exists():
            self.skipTest("Run python build.py first")
        session=Path(self.temp.name)/"session"
        core.write_json(session/"session.json",{"token":self.tokens["alice"]})
        env=dict(os.environ,KITSUMA_SESSION_DIR=str(session))
        def command(*args):
            result=subprocess.run([str(executable),*args],cwd=self.temp.name,env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return result.stdout
        self.assertIn("Cloned 2",command("clone","MusicPlayer","Alice workspace"))
        path=Path(self.temp.name)/"Alice workspace"
        (path/"src/player.txt").write_text("edited via CLI\n")
        self.assertIn("modified",command("status","--workspace",str(path)))
        self.assertIn("Submitted #",command("add","src/player.txt","-m","A message with spaces","--workspace",str(path)))
        self.assertIn("A message with spaces",command("pending","MusicPlayer"))
        self.assertIn("submitted",command("show","1"))


if __name__ == "__main__":
    unittest.main()
