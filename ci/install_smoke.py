"""Validate native ONX installation in a disposable bootstrap image."""
import json
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as d:
    files=[]
    for name,version in json.loads(Path("/etc/onx-bootstrap.json").read_text()).items():
        p=str(Path(d)/(name+".onx"))
        subprocess.run(["tatami","mkpkg","--output",p,"--info","name:"+name,
                        "--info","version:"+version,"--info","arch:x86_64"],check=True)
        files.append(p)
    subprocess.run(["tatami","--allow-untrusted","--initdb","install",*files],check=True)
packages=sorted(Path("/packages/x86_64").glob("*.onx"))
assert packages
# Detect payload collisions before installation and verify every artifact against
# the digest recorded by its isolated GitHub Actions build.
owners={}
for package in packages:
    report=json.loads(package.with_suffix(".build.json").read_text())
    with package.open("rb") as stream:
        actual_sha512=hashlib.file_digest(stream,"sha512").hexdigest()
    if actual_sha512 == report["artifact_sha512"]:
        pass
    else:
        raise RuntimeError(f"artifact checksum changed in transit: {package.name}")
    manifest=subprocess.check_output(
        ["tatami","--allow-untrusted","manifest",str(package)],text=True)
    for line in manifest.splitlines():
        checksum,path=line.split(" ",1)
        if path in owners and owners[path][0] != checksum:
            raise RuntimeError(f"payload conflict: {path}: {owners[path][1]} vs {package.name}")
        owners[path]=(checksum,package.name)
# Install individual ONX artifacts in runtime-dependency order. Keeping separate
# transactions exercises Tatami's installed-package resolver for every package.
preferred={"sed":0,"gzip":1,"ncurses":2,"less":3,"nano":3}
by_name={}
runtime_dependencies={}
for package in packages:
    metadata=json.loads(package.with_suffix(".build.json").read_text())["package"]
    name=metadata["name"]
    by_name[name]=package
    runtime_dependencies[name]={re.split(r"[<>=]",dep,1)[0] for dep in metadata["rundeps"]}
ordered=[]
visiting=[]
visited=set()
def visit(name):
    if name in visited:
        return
    if name in visiting:
        raise RuntimeError("runtime dependency cycle: "+" -> ".join([*visiting,name]))
    visiting.append(name)
    for dependency in sorted(runtime_dependencies[name]):
        if dependency in by_name:
            visit(dependency)
    visiting.pop()
    visited.add(name)
    ordered.append(by_name[name])
for name in sorted(by_name,key=lambda n:(preferred.get(n,4),n)):
    visit(name)
for package in ordered:
    subprocess.run(["tatami","-vv","--allow-untrusted","--force-overwrite","install",str(package)],check=True)
payload=b"Onlynux GNU/Linux ONX smoke test\n"*100
compressed=subprocess.check_output(["/usr/bin/gzip","-c"],input=payload)
assert subprocess.check_output(["/usr/bin/gzip","-dc"],input=compressed)==payload
assert subprocess.check_output(["/usr/bin/sed","s/old/new/"],input=b"old\n")==b"new\n"
print("Native ONX installation, gzip roundtrip and sed transformation passed.")
