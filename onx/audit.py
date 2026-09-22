"""Audit the complete requested base list without promoting unverified recipes."""
import json
from pathlib import Path
from .gentoo import select_cpv, evaluate
from .propose import propose

def audit_catalog(repo, catalog_path, policy_path, output):
    catalog=json.loads(Path(catalog_path).read_text())
    policy=json.loads(Path(policy_path).read_text())
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    results=[]
    names=[x["name"] for x in catalog["packages"]]
    if len(names)!=len(set(names)):
        raise ValueError("duplicate package in base catalog")
    for item in catalog["packages"]:
        row={"name":item["name"],"kind":item["kind"],"gentoo_atom":item["gentoo_atom"],
             "membership":"base","status":"pending-review"}
        try:
            if item["kind"]=="internal":
                row["status"]="internal-recipe-required"
                row["reason"]="Onlynux-owned filesystem layout has no upstream/Gentoo source recipe."
            elif item["kind"]=="upstream-source":
                row["status"]="upstream-adapter-required"
                row["upstream"]=item["upstream"]
                row["reason"]="Package is absent from the pinned Gentoo tree; derive the ONX recipe from upstream."
            else:
                cpv=select_cpv(repo,item["gentoo_atom"],policy.get("profile","default/linux/amd64/23.0"))
                row["cpv"]=cpv
                evidence=evaluate(repo,cpv,policy.get("profile","default/linux/amd64/23.0"))
                row["version"]=evidence["version"]
                row["ebuild_sha256"]=evidence["ebuild_sha256"]
                row["metadata"]={k:evidence["metadata"].get(k,"") for k in
                    ("DESCRIPTION","HOMEPAGE","LICENSE","SLOT","KEYWORDS","IUSE","INHERITED",
                     "DEFINED_PHASES","BDEPEND","DEPEND","RDEPEND","PDEPEND","IDEPEND",
                     "REQUIRED_USE","RESTRICT","SRC_URI")}
                if item["kind"]=="split-output":
                    row["status"]="split-output-required"
                    row["reason"]="This requested package is an output of another source recipe."
                else:
                    try:
                        propose(repo,cpv,output/"proposals"/item["name"],policy)
                        row["status"]="draft-generated"
                        row["draft"]=f"proposals/{item['name']}/drafts/{evidence['name']}"
                    except Exception as e:
                        row["status"]="adapter-required"
                        row["reason"]=str(e)
        except Exception as e:
            row["status"]="catalog-error"
            row["reason"]=str(e)
        results.append(row)
        package_dir=output/"inventory"/item["name"]
        package_dir.mkdir(parents=True,exist_ok=True)
        (package_dir/"audit.json").write_text(json.dumps(row,indent=2,sort_keys=True)+"\n")
    summary={"format":1,"gentoo_commit":policy["gentoo_commit"],
             "base_count":len(results),"base_names":names,"packages":results}
    (output/"base-audit.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    counts={}
    for row in results: counts[row["status"]]=counts.get(row["status"],0)+1
    lines=["# Onlynux base audit","",f"Requested base packages: {len(results)}","",
           "| Status | Count |","|---|---:|"]+[f"| {k} | {v} |" for k,v in sorted(counts.items())]
    lines+=["","| Package | Gentoo CPV | Status |","|---|---|---|"]
    lines += [f"| {r['name']} | {r.get('cpv','—')} | {r['status']} |" for r in results]
    (output/"SUMMARY.md").write_text("\n".join(lines)+"\n")
    # An audit is successful only if every catalog item resolved to evidence or an explicit internal/split case.
    errors=[r for r in results if r["status"]=="catalog-error"]
    if errors:
        raise ValueError("catalog errors: "+", ".join(r["name"] for r in errors))
    return summary
