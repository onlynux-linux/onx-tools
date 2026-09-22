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
packages=sorted(str(p) for p in Path("/packages/x86_64").glob("*.onx"))
assert packages
subprocess.run(["tatami","--allow-untrusted","install",*packages],check=True)
payload=b"Onlynux GNU/Linux ONX smoke test\n"*100
compressed=subprocess.check_output(["/usr/bin/gzip","-c"],input=payload)
assert subprocess.check_output(["/usr/bin/gzip","-dc"],input=compressed)==payload
assert subprocess.check_output(["/usr/bin/sed","s/old/new/"],input=b"old\n")==b"new\n"
print("Native ONX installation, gzip roundtrip and sed transformation passed.")
