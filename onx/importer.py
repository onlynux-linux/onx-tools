"""Gentoo metadata is evidence; reviewed Onlynux adapters define vanilla behavior."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from .deps import reduce, translate, Unsupported
from .gentoo import evaluate, manifest_hash
from .recipe import validate, write

def import_packages(policy_path, names, output, gentoo=None):
    policy = json.loads(Path(policy_path).read_text())
    recipes = policy["packages"]
    bootstrap = policy.get("bootstrap", {})
    if gentoo:
        import subprocess
        commit = subprocess.check_output(["git", "-C", str(gentoo), "rev-parse", "HEAD"], text=True).strip()
        if commit != policy["gentoo_commit"]:
            raise ValueError("Gentoo checkout does not match policy pin")
    made, visiting = {}, []
    def visit(name, root_target=False):
        if name in made or (name in bootstrap and not root_target):
            return
        if name in visiting:
            raise ValueError("dependency cycle: " + " -> ".join(visiting + [name]))
        if name not in recipes:
            raise ValueError("dependency has no adapter or declared bootstrap provider: " + name)
        visiting.append(name)
        adapter = recipes[name]
        provider = adapter.get("provider", "gentoo")
        if provider == "gentoo":
            if not gentoo:
                raise ValueError("Gentoo adapter requires --gentoo checkout")
            evidence = evaluate(gentoo, adapter["cpv"], policy.get("profile", "default/linux/amd64/23.0"))
            metadata = evidence["metadata"]
            if metadata["EAPI"] not in ("7", "8"):
                raise ValueError("unsupported EAPI")
            version = evidence["version"]
        elif provider == "upstream":
            evidence = {"provider": "upstream", "references": adapter["references"]}
            metadata = {}
            version = adapter["version"]
        else:
            raise ValueError("unsupported source provider")
        report = {"evidence": evidence, "adapter": adapter,
                  "notes": ["No ebuild phases, eclasses or distribution patches are copied.",
                            "Review status is not a successful build claim."]}
        deps = {}
        if "reviewed_dependencies" in adapter:
            if not adapter.get("review_reason"):
                raise ValueError("dependency override needs a review_reason")
            deps = adapter["reviewed_dependencies"]
            report["dependency_decision"] = adapter["review_reason"]
            status = "reviewed"
        else:
            flags = adapter.get("features", {})
            fields = {"builddeps": "BDEPEND", "targetdeps": "DEPEND", "rundeps": "RDEPEND"}
            if any(metadata.get(k) for k in ("PDEPEND", "IDEPEND", "REQUIRED_USE")):
                raise Unsupported("PDEPEND/IDEPEND/REQUIRED_USE require reviewed policy")
            for output_key, input_key in fields.items():
                deps[output_key] = [
                    translate(atom, policy.get("providers", {}))
                    for atom in reduce(metadata.get(input_key, ""), flags, {})]
            deps["checkdeps"] = []
            # A successful metadata parse cannot prove eclass/phase translation.
            status = "draft"
        source = dict(adapter["source"])
        source["url"] = source["url"].replace("{version}", version)
        source["filename"] = source["filename"].replace("{version}", version)
        if gentoo and provider == "gentoo":
            expected = manifest_hash(gentoo, adapter["cpv"], source["filename"])
            if source.get("sha512") and source["sha512"] != expected:
                raise ValueError("policy checksum disagrees with Gentoo Manifest")
            source["sha512"] = expected
        meta = {"format": 1, "name": name, "version": version,
                "release": adapter.get("release", 0), "arch": policy["arch"],
                "description": adapter.get("description", metadata.get("DESCRIPTION", name)),
                "homepage": adapter.get("homepage", metadata.get("HOMEPAGE", "").split(" ")[0]),
                "license": adapter["license"], "source": source,
                "source_dir": adapter.get("source_dir", name + "-{version}").replace("{version}", version),
                "build_system": adapter["build_system"], "configure_args": adapter.get("configure_args", []),
                "status": status, **{k: deps.get(k, []) for k in ("builddeps", "targetdeps", "checkdeps", "rundeps")}}
        validate(meta)
        for key in ("builddeps", "targetdeps", "checkdeps", "rundeps"):
            for dep in meta[key]:
                depname = re.split(r'[<>=]', dep)[0]
                visit(depname)
        made[name] = (meta, report)
        visiting.pop()
    for name in names:
        visit(name, root_target=True)
    root = Path(output)
    # Validate the whole closure before writing any recipe.
    for name in made:
        if (root / "main" / name).exists():
            raise ValueError("refusing to overwrite " + name)
    root.mkdir(parents=True, exist_ok=True)
    for name, (meta, report) in made.items():
        write(root / "main" / name, meta, report)
    (root / "bootstrap.json").write_text(json.dumps(bootstrap, indent=2) + "\n")
    return list(made)
