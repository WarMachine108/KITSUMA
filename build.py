"""Build once; running KITSUMA never invokes a compiler."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def main():
    output = ROOT / "build"
    output.mkdir(exist_ok=True)
    for name in ("kitsuma", "update"):
        target = output / (name + (".exe" if os.name == "nt" else ""))
        subprocess.run([os.environ.get("CXX", "g++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2", str(ROOT / f"{name}.cpp"), "-o", str(target)], check=True)
        print(f"Built {target.name}")


if __name__ == "__main__":
    main()
