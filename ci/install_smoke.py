"""Validate native ONX installation in a disposable bootstrap image."""
import json
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
# Detect payload collisions explicitly; a sequence of independent transactions
# also avoids conflating a Tatami multi-package transaction error with archive
# corruption.
owners={}
for package in packages:
    manifest=subprocess.check_output(
        ["tatami","--allow-untrusted","manifest",str(package)],text=True)
    for line in manifest.splitlines():
        checksum,path=line.split(" ",1)
        if path in owners and owners[path][0] != checksum:
            raise RuntimeError(f"payload conflict: {path}: {owners[path][1]} vs {package.name}")
        owners[path]=(checksum,package.name)
preferred={"sed":0,"gzip":1}
packages.sort(key=lambda p:(preferred.get(p.name.split("-",1)[0],2),p.name))
for package in packages:
    subprocess.run(["tatami","-vv","--allow-untrusted","--force-overwrite","install",str(package)],check=True)
payload=b"Onlynux GNU/Linux ONX smoke test\n"*100
compressed=subprocess.check_output(["/usr/bin/gzip","-c"],input=payload)
assert subprocess.check_output(["/usr/bin/gzip","-dc"],input=compressed)==payload
assert subprocess.check_output(["/usr/bin/sed","s/old/new/"],input=b"old\n")==b"new\n"
print("Native ONX installation, gzip roundtrip and sed transformation passed.")
