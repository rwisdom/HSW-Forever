import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import release as r  # noqa: E402


class Versions(unittest.TestCase):
    def test_bumps_keep_the_suffix(self):
        self.assertEqual(r.bump("1.0.0-forever", "patch"), "1.0.1-forever")
        self.assertEqual(r.bump("1.0.9-forever", "minor"), "1.1.0-forever")
        self.assertEqual(r.bump("1.4.2-forever", "major"), "2.0.0-forever")
        self.assertEqual(r.bump("1.4.2", "patch"), "1.4.3")

    def test_explicit_version(self):
        self.assertEqual(r.bump("1.0.0-forever", "2.1.0"), "2.1.0-forever")     # suffix kept unless given
        self.assertEqual(r.bump("1.0.0-forever", "2.1.0-beta.1"), "2.1.0-beta.1")
        with self.assertRaises(SystemExit):
            r.bump("1.0.0", "v2")

    def test_toc_carries_a_version(self):
        self.assertRegex(r.current_version(), r"^\d+\.\d+\.\d+(-[\w.]+)?$")


class Build(unittest.TestCase):
    def test_zip_holds_only_the_addon_under_one_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, n = r.build("9.9.9-test", dist=pathlib.Path(tmp))
            self.assertEqual(out.name, "HealerStatWeights-9.9.9-test.zip")
            names = zipfile.ZipFile(out).namelist()
        self.assertEqual(len(names), n)
        self.assertTrue(all(x.startswith("HealerStatWeights/") for x in names))
        for required in ("HealerStatWeights/HealerStatWeights.toc", "HealerStatWeights/embeds.xml", "HealerStatWeights/icon.png", "HealerStatWeights/Core.lua",
                         "HealerStatWeights/Classes/HealMatcher.lua", "HealerStatWeights/Parsers/Spells_Generated.lua",
                         "HealerStatWeights/Libs/LibStub/LibStub.lua", "HealerStatWeights/LICENSE", "HealerStatWeights/README.md"):
            self.assertIn(required, names)
        for top in ("tests", "tools", "docs", "images", ".claude", "download", "dist", ".git", ".gitignore"):
            self.assertFalse(any(x.split("/")[1] == top for x in names), top)
        self.assertFalse(any("__pycache__" in x for x in names))

    def test_toc_files_are_all_shipped(self):
        r.check_toc_covered(r.shipped_files())      # raises when the .toc loads something outside SHIP_FILES/SHIP_DIRS


class Git(unittest.TestCase):
    def repo(self, tmp):
        root = pathlib.Path(tmp)
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=root, check=True)
        toc = root / "HealerStatWeights.toc"
        toc.write_text("## Version: 1.0.0-forever\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
        return root, toc

    def test_commit_and_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, toc = self.repo(tmp)
            r.require_clean_tree(root=root)
            toc.write_text("## Version: 1.0.1-forever\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                r.require_clean_tree(root=root)
            self.assertEqual(r.commit_and_tag("1.0.1-forever", root=root, toc=toc), "v1.0.1-forever")
            self.assertEqual(r.git("tag", "--list", root=root).split(), ["v1.0.1-forever"])
            self.assertEqual(r.git("log", "-1", "--format=%s", root=root).strip(), "release: 1.0.1-forever")
            r.require_clean_tree(root=root)                                       # the bump is committed
            with self.assertRaises(SystemExit):
                r.commit_and_tag("1.0.1-forever", root=root, toc=toc)             # tag taken

    def test_release_notes_list_commits_since_the_previous_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, toc = self.repo(tmp)
            first = r.write_notes("1.0.0-forever", dist=root / "dist", root=root)
            self.assertIn("first release\n\n## Other\n\n- init", first.read_text(encoding="utf-8"))
            subprocess.run(["git", "tag", "v1.0.0-forever"], cwd=root, check=True)
            for subject in ("fix: a thing", "test: noise", "feat: another", "data: Int per crit", "chore: bump libs",
                            "fix(matcher): second thing", "docs: how it works"):
                (root / "f").write_text(subject, encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=root, check=True)
                subprocess.run(["git", "commit", "-q", "-m", subject], cwd=root, check=True)
            toc.write_text("## Version: 1.0.1-forever\n", encoding="utf-8")
            r.commit_and_tag("1.0.1-forever", root=root, toc=toc)
            notes = r.write_notes("1.0.1-forever", dist=root / "dist", root=root)
            text = notes.read_text(encoding="utf-8")
        self.assertEqual(notes.name, "HealerStatWeights-1.0.1-forever-notes.md")
        self.assertTrue(text.startswith("# HealerStatWeights 1.0.1-forever\n"))
        self.assertIn(", since v1.0.0-forever\n", text)
        body = text.split("\n\n", 2)[2]
        self.assertEqual(body, "## Features\n\n- another\n\n## Fixes\n\n- a thing\n- second thing\n\n"
                               "## Data\n\n- Int per crit\n\n## Other\n\n- docs: how it works\n")
        for noise in ("test:", "chore:", "release:"):
            self.assertNotIn(noise, text)

    def test_group_subjects(self):
        self.assertEqual(r.group_subjects(["feat!: breaking", "chore: x", "plain subject"]),
                         {"Features": ["breaking"], "Other": ["plain subject"]})
        self.assertEqual(r.group_subjects(["test: only"]), {})
