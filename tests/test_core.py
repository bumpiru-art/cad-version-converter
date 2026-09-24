import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cadconv import core  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def write(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)
    return path


def make_fake_exe(folder):
    """가짜 변환기를 실행 파일처럼 감싼다."""
    if sys.platform == "win32":
        exe = os.path.join(folder, "fake.bat")
        with open(exe, "w") as f:
            f.write(f'@"{sys.executable}" "{os.path.join(HERE, "fake_oda.py")}" %*\n')
    else:
        exe = os.path.join(folder, "fake.sh")
        with open(exe, "w") as f:
            f.write(f'#!/bin/sh\nexec "{sys.executable}" "{os.path.join(HERE, "fake_oda.py")}" "$@"\n')
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
    return exe


class DetectVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_dwg_header(self):
        p = write(os.path.join(self.tmp, "a.dwg"), b"AC1032" + b"\0" * 100)
        self.assertEqual(core.detect_version(p), "AutoCAD 2018 (2018 이후 전부)")
        p = write(os.path.join(self.tmp, "b.dwg"), b"AC1015" + b"\0" * 100)
        self.assertEqual(core.detect_version(p), "AutoCAD 2000 (2000~2002)")

    def test_unknown_dwg(self):
        p = write(os.path.join(self.tmp, "c.dwg"), b"hello!")
        self.assertEqual(core.detect_version(p), "알 수 없음")

    def test_ascii_dxf(self):
        dxf = b"  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1024\n  0\nENDSEC\n"
        p = write(os.path.join(self.tmp, "d.dxf"), dxf)
        self.assertEqual(core.detect_version(p), "AutoCAD 2010 (2010~2012)")

    def test_old_dxf_without_acadver(self):
        p = write(os.path.join(self.tmp, "e.dxf"), b"  0\nSECTION\n  2\nENTITIES\n")
        self.assertEqual(core.detect_version(p), "AutoCAD R11/R12 이하")

    def test_binary_dxf(self):
        data = b"AutoCAD Binary DXF\r\n\x1a\x00" + b"\x09\x00$ACADVER\x00\x01\x00AC1027\x00"
        p = write(os.path.join(self.tmp, "f.dxf"), data)
        self.assertEqual(core.detect_version(p), "AutoCAD 2013 (2013~2017)")

    def test_missing_file(self):
        self.assertEqual(core.detect_version(os.path.join(self.tmp, "nope.dwg")), "읽을 수 없음")


class OutputPathTest(unittest.TestCase):
    def test_suffix_and_no_overwrite(self):
        tmp = tempfile.mkdtemp()
        src = write(os.path.join(tmp, "도면.dwg"), b"AC1032")
        p1 = core.output_path(src, None, "ACAD2010", "DWG", True)
        self.assertEqual(p1, os.path.join(tmp, "도면_2010.dwg"))
        write(p1, b"x")
        p2 = core.output_path(src, None, "ACAD2010", "DWG", True)
        self.assertEqual(p2, os.path.join(tmp, "도면_2010 (1).dwg"))
        # 접미사 없이 같은 폴더에 저장해도 원본은 덮어쓰지 않는다
        p3 = core.output_path(src, None, "ACAD2010", "DWG", False)
        self.assertEqual(p3, os.path.join(tmp, "도면 (1).dwg"))

    def test_other_folder_and_dxf(self):
        p = core.output_path("/x/a.dwg", "/out", "ACAD14", "DXF", True)
        self.assertEqual(p, os.path.join("/out", "a_R14.dxf"))


class BuildCommandTest(unittest.TestCase):
    def test_arguments(self):
        cmd = core.build_command("oda", "in", "out", "ACAD2007", "dwg", True, "a.dwg")
        self.assertEqual(cmd, ["oda", "in", "out", "ACAD2007", "DWG", "0", "1", "a.dwg"])


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.exe = make_fake_exe(self.tmp)

    def test_convert_to_same_folder(self):
        src = write(os.path.join(self.tmp, "plan.dwg"), b"AC1032" + b"body")
        r = core.convert_file(self.exe, src, None, "ACAD2010")
        self.assertTrue(r.ok, r.message)
        self.assertEqual(r.output, os.path.join(self.tmp, "plan_2010.dwg"))
        self.assertEqual(core.detect_version(r.output), "AutoCAD 2010 (2010~2012)")
        # 원본은 그대로
        with open(src, "rb") as f:
            self.assertEqual(f.read(), b"AC1032body")

    def test_convert_to_other_folder_as_dxf(self):
        src = write(os.path.join(self.tmp, "plan.dwg"), b"AC1032" + b"body")
        out = os.path.join(self.tmp, "result", "sub")
        r = core.convert_file(self.exe, src, out, "ACAD2004", "DXF", add_suffix=False)
        self.assertTrue(r.ok, r.message)
        self.assertEqual(r.output, os.path.join(out, "plan.dxf"))

    def test_failure_reports_err_file(self):
        src = write(os.path.join(self.tmp, "broken.dwg"), b"AC1032")
        r = core.convert_file(self.exe, src, None, "ACAD2010")
        self.assertFalse(r.ok)
        self.assertIn("corrupted", r.message)

    def test_missing_converter(self):
        src = write(os.path.join(self.tmp, "a.dwg"), b"AC1032")
        r = core.convert_file(os.path.join(self.tmp, "no_such_exe"), src, None, "ACAD2010")
        self.assertFalse(r.ok)
        self.assertIn("ODA", r.message)

    def test_convert_many_continues_after_failure_and_stops(self):
        files = [write(os.path.join(self.tmp, n), b"AC1032") for n in
                 ("a.dwg", "broken.dwg", "c.dwg")]
        seen = []
        results = core.convert_many(self.exe, files, None, "ACAD2013",
                                    on_progress=lambda i, r: seen.append(i))
        self.assertEqual([r.ok for r in results], [True, False, True])
        self.assertEqual(seen, [0, 1, 2])
        results = core.convert_many(self.exe, files, None, "ACAD2013",
                                    should_stop=lambda: len(seen) >= 4,
                                    on_progress=lambda i, r: seen.append(i))
        self.assertEqual(len(results), 1)

    def test_collect_cad_files(self):
        os.makedirs(os.path.join(self.tmp, "sub"))
        write(os.path.join(self.tmp, "A.DWG"), b"")
        write(os.path.join(self.tmp, "b.txt"), b"")
        write(os.path.join(self.tmp, "sub", "c.dxf"), b"")
        names = [os.path.basename(p) for p in core.collect_cad_files(self.tmp)]
        self.assertEqual(sorted(names), ["A.DWG", "c.dxf"])
        names = [os.path.basename(p) for p in core.collect_cad_files(self.tmp, recursive=False)]
        self.assertEqual(names, ["A.DWG"])


if __name__ == "__main__":
    unittest.main()
