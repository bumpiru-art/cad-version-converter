"""CAD 파일 버전 판별과 ODA File Converter 호출을 담당하는 핵심 로직.

GUI와 분리돼 있어 명령줄이나 테스트에서도 그대로 쓸 수 있다.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

# (ODA 버전 코드, 파일 머리글 코드, 표시 이름)
# 같은 머리글 코드를 쓰는 AutoCAD 릴리스를 함께 적어 둔다.
VERSIONS = [
    ("ACAD2018", "AC1032", "AutoCAD 2018 (2018 이후 전부)"),
    ("ACAD2013", "AC1027", "AutoCAD 2013 (2013~2017)"),
    ("ACAD2010", "AC1024", "AutoCAD 2010 (2010~2012)"),
    ("ACAD2007", "AC1021", "AutoCAD 2007 (2007~2009)"),
    ("ACAD2004", "AC1018", "AutoCAD 2004 (2004~2006)"),
    ("ACAD2000", "AC1015", "AutoCAD 2000 (2000~2002)"),
    ("ACAD14", "AC1014", "AutoCAD R14"),
    ("ACAD13", "AC1012", "AutoCAD R13"),
    ("ACAD12", "AC1009", "AutoCAD R11/R12"),
]

# 오래된 파일도 판별만은 할 수 있도록 머리글 코드 표를 넓게 둔다.
HEADER_NAMES = {code: name for _, code, name in VERSIONS}
HEADER_NAMES.update({
    "AC1006": "AutoCAD R10",
    "AC1004": "AutoCAD R9",
    "AC1003": "AutoCAD 2.60",
    "AC1002": "AutoCAD 2.50",
})

# 출력 파일 이름 뒤에 붙일 짧은 버전 표기
SHORT_NAMES = {
    "ACAD2018": "2018", "ACAD2013": "2013", "ACAD2010": "2010",
    "ACAD2007": "2007", "ACAD2004": "2004", "ACAD2000": "2000",
    "ACAD14": "R14", "ACAD13": "R13", "ACAD12": "R12",
}

CAD_EXTENSIONS = (".dwg", ".dxf")


def detect_version(path: str) -> str:
    """파일 머리글을 읽어 AutoCAD 버전 이름을 돌려준다. 모르면 '알 수 없음'."""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as f:
            head = f.read(6)
            if ext == ".dxf":
                rest = f.read(64 * 1024)
                return _dxf_version(head + rest, binary=head == b"AutoCA")
    except OSError:
        return "읽을 수 없음"
    code = head.decode("ascii", errors="replace")
    return HEADER_NAMES.get(code, "알 수 없음")


def _dxf_version(data: bytes, binary: bool) -> str:
    """DXF 머리말의 $ACADVER 값을 찾는다. 없으면 R12 이전 형식이다."""
    idx = data.find(b"$ACADVER")
    if idx < 0:
        return "AutoCAD R11/R12 이하" if not binary else "알 수 없음"
    tail = data[idx + len(b"$ACADVER"):idx + 200]
    pos = tail.find(b"AC10")
    if pos < 0:
        return "알 수 없음"
    code = tail[pos:pos + 6].decode("ascii", errors="replace")
    return HEADER_NAMES.get(code, "알 수 없음")


def find_oda_converter() -> Optional[str]:
    """설치된 ODAFileConverter 실행 파일을 찾는다."""
    found = shutil.which("ODAFileConverter")
    if found:
        return found
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    candidates: List[str] = []
    for root in roots:
        candidates += glob.glob(os.path.join(root, "ODA", "*", "ODAFileConverter.exe"))
    # 리눅스·맥 설치 경로
    candidates += glob.glob("/usr/bin/ODAFileConverter*")
    candidates += glob.glob("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter")
    candidates = [c for c in candidates if os.path.isfile(c)]
    if not candidates:
        return None
    # 폴더 이름에 버전 번호가 들어 있으므로 가장 최신 것을 고른다.
    return sorted(candidates)[-1]


def build_command(exe: str, in_dir: str, out_dir: str, version: str,
                  file_type: str, audit: bool, file_filter: str) -> List[str]:
    """ODA File Converter 명령줄 인자를 만든다.

    형식: ODAFileConverter 입력폴더 출력폴더 버전 형식 하위폴더포함 검사 필터
    """
    return [exe, in_dir, out_dir, version, file_type.upper(), "0",
            "1" if audit else "0", file_filter]


def output_path(src: str, out_dir: Optional[str], version: str, file_type: str,
                add_suffix: bool) -> str:
    """변환 결과를 저장할 경로. 기존 파일은 절대 덮어쓰지 않도록 번호를 붙인다."""
    folder = out_dir or os.path.dirname(os.path.abspath(src))
    stem = os.path.splitext(os.path.basename(src))[0]
    if add_suffix:
        stem = f"{stem}_{SHORT_NAMES.get(version, version)}"
    ext = "." + file_type.lower()
    candidate = os.path.join(folder, stem + ext)
    n = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem} ({n}){ext}")
        n += 1
    return candidate


@dataclass
class Result:
    source: str
    ok: bool
    output: str = ""
    message: str = ""


def _hidden_window_kwargs() -> dict:
    """윈도우에서 변환기 창이 깜빡이지 않도록 숨긴다."""
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return {"startupinfo": si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW


def convert_file(exe: str, src: str, out_dir: Optional[str], version: str,
                 file_type: str = "DWG", audit: bool = True,
                 add_suffix: bool = True, timeout: int = 600) -> Result:
    """파일 하나를 변환한다.

    ODA 변환기는 폴더 단위로 동작하므로, 원본을 임시 폴더에 복사해 변환한 뒤
    결과만 원하는 위치로 옮긴다. 원본 파일은 건드리지 않는다.
    """
    if not os.path.isfile(src):
        return Result(src, False, message="파일이 없습니다")
    work = tempfile.mkdtemp(prefix="cadconv_")
    try:
        in_dir = os.path.join(work, "in")
        res_dir = os.path.join(work, "out")
        os.makedirs(in_dir)
        os.makedirs(res_dir)
        name = os.path.basename(src)
        shutil.copy2(src, os.path.join(in_dir, name))

        cmd = build_command(exe, in_dir, res_dir, version, file_type, audit, name)
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                                  **_hidden_window_kwargs())
        except FileNotFoundError:
            return Result(src, False, message="ODA File Converter를 실행할 수 없습니다")
        except subprocess.TimeoutExpired:
            return Result(src, False, message="시간 초과")

        ext = "." + file_type.lower()
        produced = [p for p in glob.glob(os.path.join(res_dir, "*"))
                    if p.lower().endswith(ext)]
        if not produced:
            return Result(src, False, message=_error_text(res_dir, proc))

        dest = output_path(src, out_dir, version, file_type, add_suffix)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(produced[0], dest)
        return Result(src, True, output=dest, message="완료")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _error_text(res_dir: str, proc: subprocess.CompletedProcess) -> str:
    """변환 실패 원인을 .err 파일이나 프로그램 출력에서 모은다."""
    for err in glob.glob(os.path.join(res_dir, "*.err")):
        try:
            with open(err, encoding="utf-8", errors="replace") as f:
                text = f.read().strip()
            if text:
                return text.splitlines()[-1]
        except OSError:
            pass
    out = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
    if out:
        return out.splitlines()[-1]
    return "변환 결과가 만들어지지 않았습니다 (손상된 파일일 수 있음)"


def convert_many(exe: str, files: Iterable[str], out_dir: Optional[str],
                 version: str, file_type: str = "DWG", audit: bool = True,
                 add_suffix: bool = True,
                 on_progress: Optional[Callable[[int, Result], None]] = None,
                 should_stop: Optional[Callable[[], bool]] = None) -> List[Result]:
    """여러 파일을 차례로 변환한다. 한 파일이 실패해도 나머지는 계속한다."""
    results = []
    for i, src in enumerate(files):
        if should_stop and should_stop():
            break
        r = convert_file(exe, src, out_dir, version, file_type, audit, add_suffix)
        results.append(r)
        if on_progress:
            on_progress(i, r)
    return results


def collect_cad_files(folder: str, recursive: bool = True) -> List[str]:
    """폴더 안의 DWG/DXF 파일을 모은다."""
    found = []
    for root, _dirs, names in os.walk(folder):
        for n in sorted(names):
            if n.lower().endswith(CAD_EXTENSIONS):
                found.append(os.path.join(root, n))
        if not recursive:
            break
    return found
