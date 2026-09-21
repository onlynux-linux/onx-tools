"""Record actual image versions. Not distribution packages."""
import json
import subprocess
import re
from pathlib import Path
commands={"gcc":["gcc","-dumpfullversion"],"make":["make","--version"],
          "binutils":["ld","--version"],"glibc":["getconf","GNU_LIBC_VERSION"],
          "bash":["bash","--version"],"grep":["grep","--version"]}
versions={}
for name,command in commands.items():
    line=subprocess.check_output(command,text=True).splitlines()[0]
    found=re.search(r"\d+(?:\.\d+)+",line)
    if not found: raise RuntimeError("cannot determine "+name+" version")
    versions[name]=found.group(0)
Path("/etc/onx-bootstrap.json").write_text(json.dumps(versions,indent=2)+"\n")
