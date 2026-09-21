import argparse
import json
import subprocess
from pathlib import Path
from .importer import import_packages
from .recipe import read
from .build import plan, fetch, build, inner_build

def main():
    p = argparse.ArgumentParser(description="Onlynux ONXBUILD importer and Tatami builder")
    sub = p.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="Generate an entire reviewed dependency closure")
    imp.add_argument("packages", nargs="+")
    imp.add_argument("--policy", required=True)
    imp.add_argument("--gentoo")
    imp.add_argument("--output", required=True)
    lint = sub.add_parser("lint")
    lint.add_argument("root")
    planner = sub.add_parser("plan")
    planner.add_argument("packages", nargs="+")
    planner.add_argument("--recipes", required=True)
    fetcher = sub.add_parser("fetch")
    fetcher.add_argument("--recipes", required=True)
    fetcher.add_argument("--cache", required=True)
    builder = sub.add_parser("build", help="Build dependencies first in networkless Linux containers")
    builder.add_argument("packages", nargs="+")
    builder.add_argument("--recipes", required=True)
    builder.add_argument("--work", required=True)
    builder.add_argument("--image", required=True)
    builder.add_argument("--allow-unsigned", action="store_true")
    internal = sub.add_parser("_build", help=argparse.SUPPRESS)
    for field in ("recipe", "source", "out", "bootstrap"):
        internal.add_argument("--" + field, required=True)
    internal.add_argument("--dependency", action="append", default=[])
    internal.add_argument("--allow-unsigned", action="store_true")
    a = p.parse_args()
    try:
        if a.command == "import":
            print(json.dumps(import_packages(a.policy, a.packages, a.output, a.gentoo)))
        elif a.command == "lint":
            paths = list(Path(a.root).glob("main/*/ONXBUILD"))
            if not paths:
                raise ValueError("no recipes found")
            for path in paths:
                read(path)
                subprocess.run(["bash", "-n", str(path)], check=True)
            print(f"{len(paths)} ONXBUILD files valid")
        elif a.command == "plan":
            order, _, bootstrap = plan(a.recipes, a.packages)
            print(json.dumps({"build_order": order, "bootstrap_boundary": bootstrap}, indent=2))
        elif a.command == "fetch":
            for path in Path(a.recipes).glob("main/*/ONXBUILD"):
                print(fetch(read(path)["source"], a.cache))
        elif a.command == "build":
            print(json.dumps(build(a.recipes, a.packages, a.work, a.image, a.allow_unsigned)))
        elif a.command == "_build":
            inner_build(a.recipe, a.source, a.out, a.bootstrap, a.dependency, a.allow_unsigned)
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        p.exit(1, f"onx: {e}\n")

if __name__ == "__main__":
    main()
