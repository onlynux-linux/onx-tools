"""Linux Docker builds and native ONX packaging through tatami mkpkg."""
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from .recipe import read

def depname(dependency):
    return re.split(r'[<>=]', dependency)[0]

def plan(root, targets):
    root = Path(root)
    recipes = {}
    for p in root.glob("main/*/ONXBUILD"):
        m = read(p)
        if m["name"] in recipes:
            raise ValueError("duplicate package " + m["name"])
        recipes[m["name"]] = (p, m)
    bootstrap = json.loads((root / "bootstrap.json").read_text()) if (root / "bootstrap.json").exists() else {}
    active, done, ordered = [], set(), []
    def visit(name, root_target=False):
        if name in done or (name in bootstrap and not root_target):
            return
        if name in active:
            raise ValueError("dependency cycle: " + " -> ".join(active + [name]))
        if name not in recipes:
            raise ValueError("missing dependency recipe: " + name)
        active.append(name)
        _, m = recipes[name]
        if m["status"] != "reviewed":
            raise ValueError("draft recipe requires review: " + name)
        for key in ("builddeps", "targetdeps", "checkdeps", "rundeps"):
            for dep in m[key]:
                visit(depname(dep))
        active.pop()
        done.add(name)
        ordered.append(name)
    for name in targets:
        # A bootstrap provider may itself be rebuilt as a root target. During its
        # build, the disposable image still supplies the previous-stage version.
        visit(name, root_target=True)
    return ordered, recipes, bootstrap

def fetch(source, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (source["sha512"] + "-" + source["filename"])
    def verify(p):
        with p.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha512").hexdigest()
        if digest != source["sha512"]:
            raise ValueError("source checksum mismatch: " + source["filename"])
    if path.exists():
        verify(path)
        return path
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temporary:
        temp = Path(temporary.name)
        try:
            request = urllib.request.Request(source["url"], headers={"User-Agent": "onx-tools/0.1"})
            with urllib.request.urlopen(request, timeout=120) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("insecure download redirect")
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
            temporary.flush()
            verify(temp)
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
    return path

def extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        # Python data filter rejects traversal, external links and device nodes.
        tar.extractall(destination, filter="data")

def build(root, targets, work, image, allow_unsigned=False):
    if platform.system() != "Linux":
        raise ValueError("build is Linux-only; use GitHub Actions")
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/@+-]*', image):
        raise ValueError("invalid build image")
    root, work = Path(root).resolve(), Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    order, recipes, bootstrap = plan(root, targets)
    built = []
    for name in order:
        recipe, meta = recipes[name]
        source = fetch(meta["source"], work / "sources")
        dependencies = sorted({depname(d) for k in ("builddeps", "targetdeps", "checkdeps", "rundeps") for d in meta[k]})
        # Tatami resolves each direct dependency transitively, so provide every package
        # already built in the topological closure, not only direct edges.
        required_packages = [str(p.relative_to(work)) for _, p in built]
        if required_packages and not allow_unsigned:
            raise ValueError("development dependency packages are unsigned; pass --allow-unsigned explicitly")
        args = ["docker", "run", "--rm", "--network=none", "--cap-drop=ALL",
                "--cap-add=CHOWN", "--cap-add=SETUID", "--cap-add=SETGID", "--cap-add=DAC_OVERRIDE",
                "--security-opt=no-new-privileges",
                "--mount", "type=bind,src=" + str(root) + ",dst=/recipes,readonly",
                "--mount", "type=bind,src=" + str(work) + ",dst=/work",
                image, "python3", "-m", "onx.cli", "_build",
                "--recipe", "/recipes/" + str(recipe.relative_to(root)),
                "--source", "/work/" + str(source.relative_to(work)),
                "--out", "/work/packages", "--bootstrap", "/recipes/bootstrap.json"]
        for item in required_packages:
            args += ["--dependency", "/work/" + item]
        if allow_unsigned:
            args += ["--allow-unsigned"]
        subprocess.run(args, check=True)
        package = work / "packages" / meta["arch"] / f'{name}-{meta["version"]}-r{meta["release"]}.onx'
        if not package.exists():
            raise ValueError("builder did not produce expected package")
        built.append((name, package))
    return [str(path) for _, path in built]

def inner_build(recipe, source, out, bootstrap, dependency, allow_unsigned):
    if os.environ.get("ONX_BUILD_CONTAINER") != "1":
        raise ValueError("_build is only supported inside the build image")
    meta = read(recipe)
    native = {"x86_64": "x86_64", "aarch64": "aarch64"}.get(platform.machine())
    if meta["arch"] not in (native, "noarch"):
        raise ValueError("cross compilation is not supported")
    boundaries = json.loads(Path(bootstrap).read_text())
    # Image must carry explicit versions, not infer packages from executable names.
    installed = json.loads(Path("/etc/onx-bootstrap.json").read_text())
    for name in boundaries:
        if name not in installed:
            raise ValueError("bootstrap image lacks declared provider " + name)
    # Register bootstrap-image providers in the disposable container database only.
    # These empty receipts are never copied into the output repository.
    with tempfile.TemporaryDirectory(prefix="onx-bootstrap-") as temporary:
        receipts = []
        for name, version in installed.items():
            receipt = str(Path(temporary) / (name + ".onx"))
            subprocess.run(["tatami", "mkpkg", "--output", receipt,
                            "--info", "name:" + name, "--info", "version:" + version,
                            "--info", "arch:" + native], check=True)
            receipts.append(receipt)
        subprocess.run(["tatami", "--allow-untrusted", "--initdb", "install", *receipts], check=True)
    if dependency:
        if not allow_unsigned:
            raise ValueError("unsigned dependency installation disabled")
        subprocess.run(["tatami", "--allow-untrusted", "--initdb", "install", *dependency], check=True)
    for key in ("builddeps", "targetdeps", "checkdeps", "rundeps"):
        for atom in meta[key]:
            name = depname(atom)
            if name in boundaries:
                version = installed[name]
            else:
                result = subprocess.run(["tatami", "info", "--exists", atom], capture_output=True)
                if result.returncode:
                    raise ValueError("unsatisfied dependency: " + atom)
                continue
            parts = re.split(r'(>=|<=|=|>|<)', atom, maxsplit=1)
            if len(parts) == 3:
                comparison = subprocess.check_output(["tatami", "version", "-t", version, parts[2]], text=True).strip()
                if comparison not in {">=": (">", "="), "<=": ("<", "="), "=": ("=",), ">": (">",), "<": ("<",)}[parts[1]]:
                    raise ValueError("bootstrap version does not satisfy " + atom)
    package_dir = Path(out) / meta["arch"]
    package_dir.mkdir(parents=True, exist_ok=True)
    artifact = package_dir / f'{meta["name"]}-{meta["version"]}-r{meta["release"]}.onx'
    if artifact.exists():
        raise ValueError("refusing to overwrite built package")
    with tempfile.TemporaryDirectory(prefix="onx-build-") as temporary:
        base = Path(temporary)
        extract(source, base / "src")
        src = base / "src" / meta["source_dir"]
        if not src.is_dir():
            raise ValueError("source directory missing")
        dest = base / "pkg"
        dest.mkdir()
        # Upstream code runs as nobody, with no network and no capabilities.
        for p in [base, *base.rglob("*")]:
            if not p.is_symlink():
                os.chown(p, 65534, 65534)
        environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(base),
                       "LC_ALL": "C.UTF-8", "TZ": "UTC", "SOURCE_DATE_EPOCH": "0",
                       "pkgdir": str(dest), "jobs": str(os.cpu_count() or 2)}
        script = 'set -eu\n. "$1"\nconfigure\nbuild\ncheck\npackage\n'
        subprocess.run(["bash", "-c", script, "onx", str(Path(recipe).resolve())],
                       cwd=src, env=environment, user=65534, group=65534, extra_groups=[], check=True)
        # install-info owns this generated cross-package index. Shipping one copy
        # per GNU package creates file conflicts and stale global state.
        info_index = dest / "usr/share/info/dir"
        if info_index.is_file() or info_index.is_symlink():
            info_index.unlink()
        if not any(dest.rglob("*")):
            raise ValueError("empty package")
        elf = []
        for path in dest.rglob("*"):
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as stream:
                    if stream.read(4) != b"\x7fELF":
                        continue
                dynamic = subprocess.check_output(["readelf", "-d", str(path)], text=True)
                elf.append({"file": str(path.relative_to(dest)),
                            "needed": re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic)})
        # Keep payload owned by root regardless of the unprivileged build user.
        for p in [dest, *dest.rglob("*")]:
            os.chown(p, 0, 0, follow_symlinks=False)
        args = ["tatami", "mkpkg", "--files", str(dest), "--output", str(artifact)]
        info = {"name": meta["name"], "version": f'{meta["version"]}-r{meta["release"]}',
                "arch": meta["arch"], "description": meta["description"], "license": meta["license"],
                "url": meta["homepage"], "depends": " ".join(meta["rundeps"])}
        for key, value in info.items():
            if value:
                args += ["--info", key + ":" + value]
        subprocess.run(args, check=True)
        subprocess.run(["tatami", "--allow-untrusted", "verify", str(artifact)], check=True)
        with artifact.open("rb") as stream:
            artifact_sha512 = hashlib.file_digest(stream, "sha512").hexdigest()
        with tempfile.TemporaryDirectory(prefix="onx-extract-check-") as extract_dir:
            subprocess.run(["tatami", "--allow-untrusted", "extract", "--destination", extract_dir, str(artifact)], check=True)
        artifact.with_suffix(".build.json").write_text(json.dumps(
            {"package": meta, "tests": "passed", "artifact_sha512": artifact_sha512, "elf": elf, "bootstrap_versions": installed,
             "scope": "bootstrap-image build; not a self-hosted Onlynux build",
             "signing": "unsigned development artifact",
             "runtime_dependencies": "reviewed explicit metadata; ELF scan is an audit report"},
            indent=2) + "\n")