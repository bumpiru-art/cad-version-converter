"""테스트용 가짜 ODAFileConverter.

실제 변환기와 같은 인자를 받아, 필터에 맞는 파일의 머리글만 목표 버전으로 바꿔 출력한다.
파일 이름에 'broken'이 들어 있으면 .err 파일만 남기고 실패한다.
"""
import fnmatch
import os
import sys

CODES = {"ACAD2018": b"AC1032", "ACAD2013": b"AC1027", "ACAD2010": b"AC1024",
         "ACAD2007": b"AC1021", "ACAD2004": b"AC1018", "ACAD2000": b"AC1015"}

in_dir, out_dir, version, ftype, _recurse, _audit, pattern = sys.argv[1:8]
for name in os.listdir(in_dir):
    if not fnmatch.fnmatch(name, pattern):
        continue
    stem = os.path.splitext(name)[0]
    if "broken" in name:
        with open(os.path.join(out_dir, name + ".err"), "w") as f:
            f.write("Error: File is corrupted\n")
        continue
    with open(os.path.join(in_dir, name), "rb") as f:
        data = f.read()
    with open(os.path.join(out_dir, stem + "." + ftype.lower()), "wb") as f:
        f.write(CODES[version] + data[6:])
