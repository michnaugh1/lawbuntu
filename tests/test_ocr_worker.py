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


class TestCheckOcrmypdfInstalled(unittest.TestCase):

    def test_returns_true_when_installed(self):
        from tools.ocr_pdfs_gui import check_ocrmypdf_installed
        self.assertTrue(check_ocrmypdf_installed())

    def test_returns_false_when_not_on_path(self):
        from unittest.mock import patch
        from tools.ocr_pdfs_gui import check_ocrmypdf_installed
        with patch('shutil.which', return_value=None):
            self.assertFalse(check_ocrmypdf_installed())


class TestProcessPdf(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_pdf(self, name='test.pdf'):
        p = self.tmp / name
        p.write_bytes(b'%PDF-1.4 fake content')
        return p

    def test_returns_skipped_on_exit_code_6(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=6, stderr='')):
            result = process_pdf(pdf)
        self.assertEqual(result['status'], 'skipped')
        self.assertTrue(pdf.exists())

    def test_returns_ok_and_moves_temp_file_on_success(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b'%PDF-1.4 ocr processed')
            return Mock(returncode=0, stderr='')

        with patch('subprocess.run', side_effect=fake_run):
            result = process_pdf(pdf)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(pdf.exists())

    def test_returns_error_on_nonzero_exit(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='unknown error')):
            result = process_pdf(pdf)
        self.assertEqual(result['status'], 'error')
        self.assertIn('message', result)
        self.assertTrue(pdf.exists())

    def test_error_message_mentions_password_when_encrypted(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='encrypted password required')):
            result = process_pdf(pdf)
        self.assertIn('password', result['message'].lower())

    def test_error_message_mentions_damaged_when_invalid(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='not a pdf invalid format')):
            result = process_pdf(pdf)
        self.assertIn('damaged', result['message'].lower())


if __name__ == '__main__':
    unittest.main()
