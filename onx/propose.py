"""Generate review-only ONXBUILD drafts from arbitrary pinned Gentoo CPVs."""
from pathlib import Path
from urllib.parse import urlparse
from .deps import reduce, translate, Unsupported
from .gentoo import evaluate, manifest_hash
from .recipe import write

def propose(repo, cpv, output, policy, enabled=()):
    evidence = evaluate(repo, cpv, policy.get("profile", "default/linux/amd64/23.0"))
    m = evidence["metadata"]
    if m["EAPI"] not in ("7", "8"):
        raise ValueError("unsupported EAPI")
    flags = {x.lstrip("+-"): x.startswith("+") for x in m["IUSE"].split()}
    for option in enabled:
        flag = option.lstrip("+-")
        if flag not in flags:
            raise ValueError("unknown USE flag: " + flag)
        flags[flag] = not option.startswith("-")
    # Signature blobs are not a replacement for verifying the tarball Manifest hash.
    tokens = reduce(m["SRC_URI"], flags, {})
    sources = []
    i = 0
    while i < len(tokens):
        url = tokens[i]
        i += 1
        filename = Path(urlparse(url).path).name
        if i < len(tokens) and tokens[i] == "->":
            i += 1
            if i == len(tokens):
                raise ValueError("missing SRC_URI rename target")
            filename = tokens[i]
            i += 1
        if url.startswith("mirror://gnu/"):
            url = "https://ftp.gnu.org/gnu/" + url[len("mirror://gnu/"):]
        if url.startswith("https://") and filename.endswith((".tar.gz", ".tar.xz", ".tar.bz2", ".tgz")):
            sources.append((filename, url))
    if len({name for name, _ in sources}) != 1:
        raise ValueError("ambiguous/unsupported source set; add an explicit upstream policy adapter")
    filename, url = sources[0]
    inherited = set(m["INHERITED"].split())
    system = "meson" if "meson" in inherited else "cmake" if "cmake" in inherited else "autotools"
    issues = ["Draft only: upstream configure arguments, test dependencies and phases need review.",
              "Build-system selection is a hint from inherited eclasses, not a phase translation.",
              "No patches or Gentoo phase code were copied."]
    deps = {"checkdeps":[]}
    for target, field in (("builddeps","BDEPEND"),("targetdeps","DEPEND"),("rundeps","RDEPEND")):
        deps[target] = []
        try:
            for atom in reduce(m[field],flags,{}):
                try:
                    deps[target].append(translate(atom,policy.get("providers",{})))
                except Unsupported as e:
                    issues.append(field+": "+str(e))
        except Unsupported as e:
            issues.append(field+": "+str(e))
    for field in ("REQUIRED_USE","PDEPEND","IDEPEND","RESTRICT"):
        if m[field]:
            issues.append("Review "+field+": "+m[field])
    license_map={"GPL-3+":"GPL-3.0-or-later","GPL-2+":"GPL-2.0-or-later",
                 "GPL-2":"GPL-2.0-only","GPL-3":"GPL-3.0-only","ZLIB":"Zlib","MIT":"MIT"}
    license_value=license_map.get(m["LICENSE"],m["LICENSE"])
    if m["LICENSE"] not in license_map:
        issues.append("Confirm SPDX license expression: "+m["LICENSE"])
    meta=dict(format=1,name=evidence["name"],version=evidence["version"],release=0,
              arch=policy.get("arch","x86_64"),description=m["DESCRIPTION"],
              homepage=m["HOMEPAGE"].split()[0] if m["HOMEPAGE"] else "",
              license=license_value,source={"url":url,"filename":filename,
              "sha512":manifest_hash(repo,cpv,filename)},
              source_dir=evidence["name"]+"-"+evidence["version"],
              build_system=system,configure_args=[],status="draft",**deps)
    write(Path(output)/"drafts"/meta["name"],meta,
          {"evidence":evidence,"features":flags,"review_required":issues,
           "untranslated_dependencies_preserved_in":"evidence.metadata"})
    return meta["name"]
