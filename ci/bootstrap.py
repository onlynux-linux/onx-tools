"""Record actual image versions. Not distribution packages."""
import json
import subprocess
import re
from pathlib import Path
commands={"gcc":["gcc","-dumpfullversion"],"g++":["g++","-dumpfullversion"],"make":["make","--version"],
          "binutils":["ld","--version"],"glibc":["getconf","GNU_LIBC_VERSION"],
          "glibc-locales":["locale","--version"],
          "bash":["bash","--version"],"grep":["grep","--version"],"perl":["perl","-e","printf \"%vd\\n\", $^V"],
          "meson":["meson","--version"],"ninja":["ninja","--version"],"pkg-config":["pkg-config","--version"],
          "bison":["bison","--version"],"flex":["flex","--version"],
          "autoconf":["autoconf","--version"],"automake":["automake","--version"],"libtool":["libtoolize","--version"]}
versions={}
for name,command in commands.items():
    line=subprocess.check_output(command,text=True).splitlines()[0]
    found=re.search(r"\d+(?:\.\d+)+",line)
    if not found: raise RuntimeError("cannot determine "+name+" version")
    versions[name]=found.group(0)
Path("/etc/onx-bootstrap.json").write_text(json.dumps(versions,indent=2)+"\n")
