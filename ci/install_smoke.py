"""Validate native ONX installation in both bootstrap and isolated roots."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

state = Path(tempfile.mkdtemp(prefix="onx-smoke-"))
root = state / "root"
root.mkdir()
receipts = []
for name, version in json.loads(Path("/etc/onx-bootstrap.json").read_text()).items():
    receipt = str(state / (name + ".onx"))
    subprocess.run([
        "tatami", "mkpkg", "--output", receipt, "--info", "name:" + name,
        "--info", "version:" + version, "--info", "arch:x86_64",
    ], check=True)
    receipts.append(receipt)
subprocess.run(["tatami", "--allow-untrusted", "--initdb", "install", *receipts], check=True)
subprocess.run([
    "tatami", "--root", str(root), "--force-no-chroot", "--allow-untrusted",
    "--initdb", "install", *receipts,
], check=True)

packages = sorted(Path("/packages/x86_64").glob("*.onx"))
assert packages
owners = {}
for package in packages:
    report = json.loads(package.with_suffix(".build.json").read_text())
    with package.open("rb") as stream:
        actual_sha512 = hashlib.file_digest(stream, "sha512").hexdigest()
    if actual_sha512 != report["artifact_sha512"]:
        raise RuntimeError(f"artifact checksum changed in transit: {package.name}")
    manifest = subprocess.check_output(
        ["tatami", "--allow-untrusted", "manifest", str(package)], text=True
    )
    for line in manifest.splitlines():
        checksum, path = line.split(" ", 1)
        if path in owners and owners[path][0] != checksum:
            raise RuntimeError(f"payload conflict: {path}: {owners[path][1]} vs {package.name}")
        owners[path] = (checksum, package.name)

preferred = {"sed": 0, "gzip": 1, "ncurses": 2, "less": 3, "nano": 3}
by_name = {}
runtime_dependencies = {}
for package in packages:
    metadata = json.loads(package.with_suffix(".build.json").read_text())["package"]
    name = metadata["name"]
    by_name[name] = package
    runtime_dependencies[name] = {
        re.split(r"[<>=]", dependency, 1)[0] for dependency in metadata["rundeps"]
    }
ordered = []
visiting = []
visited = set()

def visit(name):
    if name in visited:
        return
    if name in visiting:
        raise RuntimeError("runtime dependency cycle: " + " -> ".join([*visiting, name]))
    visiting.append(name)
    for dependency in sorted(runtime_dependencies[name]):
        if dependency in by_name:
            visit(dependency)
    visiting.pop()
    visited.add(name)
    ordered.append(by_name[name])

for name in sorted(by_name, key=lambda item: (preferred.get(item, 4), item)):
    visit(name)

for package in ordered:
    name = json.loads(package.with_suffix(".build.json").read_text())["package"]["name"]
    subprocess.run([
        "tatami", "-vv", "--root", str(root), "--force-no-chroot",
        "--allow-untrusted", "--force-overwrite", "install", str(package),
    ], check=True)
    if name != "onlynux-filesystem":
        subprocess.run([
            "tatami", "-vv", "--allow-untrusted", "--force-overwrite",
            "install", str(package),
        ], check=True)

assert (root / "usr/lib/os-release").read_text().splitlines()[0] == "NAME=Onlynux"
for path, target in (("bin", "usr/bin"), ("sbin", "usr/sbin"),
                     ("lib", "usr/lib"), ("lib64", "usr/lib")):
    candidate = root / path
    assert candidate.is_symlink(), f"{path} is not a symlink"
    assert os.readlink(candidate) == target, f"{path} points to {os.readlink(candidate)}"
assert (root / "etc/shadow").stat().st_mode & 0o077 == 0

payload = b"Onlynux GNU/Linux ONX smoke test\n" * 100
compressed = subprocess.check_output(["/usr/bin/gzip", "-c"], input=payload)
assert subprocess.check_output(["/usr/bin/gzip", "-dc"], input=compressed) == payload
assert subprocess.check_output(["/usr/bin/sed", "s/old/new/"], input=b"old\n") == b"new\n"
print("Isolated Onlynux root, native ONX installation, gzip and sed checks passed.")
