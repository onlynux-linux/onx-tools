import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from onx.deps import reduce, translate, Unsupported
from onx.recipe import render, read, write
from onx.build import plan, extract, fetch
from onx.importer import import_packages

def recipe(name="sample", deps=None):
    return dict(format=1, name=name, version="1.0", release=0, arch="x86_64",
                description="fixture", homepage="https://example.org", license="MIT",
                source=dict(url="https://example.org/sample.tar.gz", filename="sample.tar.gz", sha512="a"*128),
                source_dir="sample-1.0", build_system="autotools", configure_args=[],
                builddeps=deps or [], targetdeps=[], checkdeps=[], rundeps=[], status="reviewed")

class Dependencies(unittest.TestCase):
    def test_nested_conditions(self):
        self.assertEqual(reduce("a? ( cat/a !b? ( cat/b ) )", {"a":True,"b":False}, {}), ["cat/a","cat/b"])
    def test_disabled(self):
        self.assertEqual(reduce("x? ( cat/a ) cat/b", {"x":False}, {}), ["cat/b"])
    def test_unknown_flag(self):
        with self.assertRaises(Unsupported): reduce("x? ( cat/a )", {}, {})
    def test_incomplete_group(self):
        with self.assertRaises(Unsupported): reduce("x? ( cat/a", {"x":True}, {})
    def test_complex_fail_closed(self):
        for expression in ("|| ( a/b a/c )", "^^ ( a/b a/c )"):
            with self.assertRaises(Unsupported): reduce(expression, {}, {})
    def test_versions_preserved(self):
        self.assertEqual(translate(">=sys-libs/zlib-1.3.2", {"sys-libs/zlib":"zlib"}), "zlib>=1.3.2")
    def test_complex_atoms_not_erased(self):
        for atom in ("!sys-libs/zlib", "sys-libs/zlib:0", "sys-libs/zlib[static-libs]", "~sys-libs/zlib-1.3"):
            with self.assertRaises(Unsupported): translate(atom, {"sys-libs/zlib":"zlib"})
    def test_missing_provider(self):
        with self.assertRaises(Unsupported): translate("sys-libs/zlib", {})

class Recipes(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ONXBUILD"; p.write_text(render(recipe()))
            self.assertEqual(read(p),recipe())
    def test_phase_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ONXBUILD"; p.write_text(render(recipe()) + "\necho unexpected\n")
            with self.assertRaises(ValueError): read(p)
    def test_shell_metadata_quoted(self):
        m=recipe(); m["description"]="$(touch /tmp/not-allowed)"
        self.assertIn("pkgdesc='$(touch /tmp/not-allowed)'",render(m))
    def test_path_rejected(self):
        m=recipe(); m["name"]="../bad"
        with self.assertRaises(ValueError): render(m)
    def test_diamond_dependency_order(self):
        with tempfile.TemporaryDirectory() as d:
            for name,deps in [("app",["left","right"]),("left",["lib"]),("right",["lib"]),("lib",[])]:
                write(Path(d)/"main"/name,recipe(name,deps),{})
            self.assertEqual(plan(d,["app"])[0],["lib","left","right","app"])
    def test_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            for name,deps in [("a",["b"]),("b",["a"])]:
                write(Path(d)/"main"/name,recipe(name,deps),{})
            with self.assertRaisesRegex(ValueError,"cycle"): plan(d,["a"])
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            write(Path(d)/"main/a",recipe("a",["missing"]),{})
            with self.assertRaisesRegex(ValueError,"missing"): plan(d,["a"])
    def test_cached_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            m=recipe(); source=m["source"]
            (Path(d)/(source["sha512"]+"-"+source["filename"])).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError,"checksum"): fetch(source,d)
    def test_archive_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bad.tar"
            with tarfile.open(p,"w") as t:
                entry=tarfile.TarInfo("../escape"); entry.size=1
                t.addfile(entry,io.BytesIO(b"x"))
            with self.assertRaises(tarfile.FilterError): extract(p,Path(d)/"out")
            self.assertFalse((Path(d)/"escape").exists())
    def test_upstream_recursive_import(self):
        with tempfile.TemporaryDirectory() as d:
            m=recipe()
            adapters={}
            for name,deps in [("app",["lib"]),("lib",[])]:
                adapters[name]=dict(provider="upstream",version="1.0",license="MIT",homepage="https://example.org",
                    references=["https://example.org/INSTALL"],source=m["source"],build_system="autotools",
                    review_reason="Test fixture",reviewed_dependencies={"builddeps":deps})
            p=Path(d)/"policy.json"
            p.write_text(json.dumps({"arch":"x86_64","packages":adapters}))
            self.assertEqual(import_packages(p,["app"],Path(d)/"out"),["lib","app"])
            with self.assertRaises(ValueError): import_packages(p,["app"],Path(d)/"out")
if __name__ == "__main__":
    unittest.main()
