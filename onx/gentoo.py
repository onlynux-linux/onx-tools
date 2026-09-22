"""Read evaluated Portage metadata in an ephemeral Linux build environment."""
import hashlib
import subprocess
import tempfile
from pathlib import Path

KEYS = ("EAPI", "DESCRIPTION", "HOMEPAGE", "SRC_URI", "LICENSE", "SLOT",
        "BDEPEND", "DEPEND", "RDEPEND", "KEYWORDS", "PDEPEND", "IDEPEND", "IUSE",
        "REQUIRED_USE", "INHERITED", "DEFINED_PHASES", "RESTRICT")

def evaluate(repo, cpv, profile="default/linux/amd64/23.0"):
    try:
        import portage
    except ImportError as e:
        raise ValueError("Gentoo import needs Portage on the GitHub runner; see workflow") from e
    repo = Path(repo).resolve()
    parts = portage.versions.catpkgsplit(cpv)
    if not parts:
        raise ValueError("pass a pinned Gentoo CPV, e.g. app-arch/gzip-1.14")
    category, name, version, revision = parts
    pv = version + (("-" + revision) if revision != "r0" else "")
    ebuild = repo / category / name / (name + "-" + pv + ".ebuild")
    if not ebuild.is_file():
        raise ValueError("missing ebuild: " + str(ebuild))
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip():
        raise ValueError("Gentoo checkout must be clean")
    selected_profile = (repo / "profiles" / profile).resolve()
    if not selected_profile.is_relative_to(repo / "profiles") or not selected_profile.is_dir():
        raise ValueError("invalid Gentoo profile")
    with tempfile.TemporaryDirectory(prefix="onx-portage-") as temporary:
        config = Path(temporary)
        etc = config / "etc/portage"
        (etc / "repos.conf").mkdir(parents=True)
        (etc / "repos.conf/gentoo.conf").write_text(
            "[DEFAULT]\nmain-repo = gentoo\n[gentoo]\nlocation = " + str(repo) + "\nauto-sync = no\n")
        (etc / "make.profile").symlink_to(selected_profile, target_is_directory=True)
        (etc / "make.conf").write_text('ACCEPT_KEYWORDS="amd64"\n')
        trees = portage.create_trees(config_root=str(config), target_root=str(config / "root"))
        tree = next(iter(trees.values()))
        db = tree["porttree"].dbapi
        values = db.aux_get(cpv, list(KEYS))
    return {"cpv": cpv, "name": name, "version": version,
            "gentoo_commit": commit, "ebuild_sha256": hashlib.sha256(ebuild.read_bytes()).hexdigest(),
            "metadata": dict(zip(KEYS, values))}

def manifest_hash(repo, cpv, filename):
    import portage
    category, name, _, _ = portage.versions.catpkgsplit(cpv)
    for line in (Path(repo) / category / name / "Manifest").read_text().splitlines():
        fields = line.split()
        if len(fields) > 4 and fields[:2] == ["DIST", filename]:
            hashes = dict(zip(fields[3::2], fields[4::2]))
            if "SHA512" in hashes:
                return hashes["SHA512"]
    raise ValueError("no SHA512 in Gentoo Manifest for " + filename)


def select_cpv(repo, atom, profile="default/linux/amd64/23.0"):
    """Select the best stable amd64 CPV from the pinned repository/profile."""
    try:
        import portage
    except ImportError as e:
        raise ValueError("Gentoo selection needs Portage on the GitHub runner") from e
    repo = Path(repo).resolve()
    selected_profile = (repo / "profiles" / profile).resolve()
    with tempfile.TemporaryDirectory(prefix="onx-select-") as temporary:
        config = Path(temporary)
        etc = config / "etc/portage"
        (etc / "repos.conf").mkdir(parents=True)
        (etc / "repos.conf/gentoo.conf").write_text(
            "[DEFAULT]\nmain-repo = gentoo\n[gentoo]\nlocation = " + str(repo) + "\nauto-sync = no\n")
        (etc / "make.profile").symlink_to(selected_profile, target_is_directory=True)
        (etc / "make.conf").write_text('ACCEPT_KEYWORDS="amd64"\n')
        trees = portage.create_trees(config_root=str(config), target_root=str(config / "root"))
        tree = next(iter(trees.values()))
        db = tree["porttree"].dbapi
        cpv = db.xmatch("bestmatch-visible", atom)
        if not cpv:
            # Auditing must still inventory packages that Gentoo marks testing or
            # masked. Promotion remains a separate, reviewed Onlynux decision.
            cpv = portage.best(db.xmatch("match-all", atom))
    if not cpv:
        raise ValueError("no Gentoo package found for " + atom)
    return cpv
