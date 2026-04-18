import shutil
import tempfile
import unittest
from pathlib import Path


class TestFindPdfs(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _touch(self, rel):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        return p

    def test_finds_pdfs_in_flat_directory(self):
        self._touch('a.pdf')
        self._touch('b.pdf')
        self._touch('notes.txt')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=False)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(p.suffix == '.pdf' for p in result))

    def test_recursive_finds_nested_pdfs(self):
        self._touch('top.pdf')
        self._touch('sub/nested.pdf')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=True)
        self.assertEqual(len(result), 2)

    def test_non_recursive_skips_nested_pdfs(self):
        self._touch('top.pdf')
        self._touch('sub/nested.pdf')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=False)
        self.assertEqual(len(result), 1)

    def test_returns_sorted_list(self):
        self._touch('z.pdf')
        self._touch('a.pdf')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=False)
        names = [p.name for p in result]
        self.assertEqual(names, sorted(names))

    def test_empty_directory_returns_empty_list(self):
        from tools.ocr_pdfs_gui import find_pdfs
        self.assertEqual(find_pdfs(self.tmp, recursive=False), [])


if __name__ == '__main__':
    unittest.main()
