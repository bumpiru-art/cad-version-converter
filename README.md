# CAD 버전 변환기

AutoCAD DWG / DXF 파일의 버전을 한꺼번에 바꾸는 Windows 창 프로그램입니다.
예를 들어 AutoCAD 2018로 저장된 도면을 2010이나 2007 버전으로 낮춰, 예전 CAD에서도 열 수 있게 합니다.

실제 변환은 무료 프로그램인 **ODA File Converter**가 하고, 이 프로그램은 파일 선택·버전 확인·일괄 처리·결과 정리를 맡습니다.
DWG는 공개되지 않은 형식이라, 직접 구현하기보다 검증된 ODA 엔진을 쓰는 편이 도면이 깨질 위험이 훨씬 적습니다.

## 준비

1. **ODA File Converter 설치** (무료): <https://www.opendesign.com/guestfiles/oda_file_converter>
   기본 위치(`C:\Program Files\ODA\...`)에 설치하면 프로그램이 알아서 찾습니다.
2. 둘 중 하나로 실행합니다.
   - **exe 파일**: GitHub의 *Actions* 탭 → 최근 *Build Windows exe* 실행 → `CADVersionConverter` 내려받기
     (또는 `build.bat`을 더블클릭해 직접 만들면 `dist\CADVersionConverter.exe`가 생깁니다)
   - **Python으로 바로 실행**: Python 3.9 이상에서 `python main.py` (추가 설치 없음)

## 사용법

1. `파일 추가` / `폴더 추가`로 도면을 넣습니다. 목록에 **현재 버전**이 표시됩니다.
2. **바꿀 버전**과 **저장 형식**(DWG 또는 DXF)을 고릅니다.
3. 저장 위치를 정하고 `변환 시작`을 누릅니다.

| 옵션 | 설명 |
|---|---|
| 원본과 같은 폴더 | 끄면 원하는 폴더에 모아서 저장 |
| 파일 이름 뒤에 버전 붙이기 | `도면.dwg` → `도면_2010.dwg` |
| 오류 검사·복구(Audit) | 변환하면서 도면 오류를 고침 (권장) |

- **원본 파일은 절대 바뀌거나 덮어써지지 않습니다.** 같은 이름이 있으면 `도면 (1).dwg`처럼 번호를 붙입니다.
- 한 파일이 실패해도 나머지는 계속 변환하며, 실패 원인은 목록의 *상태* 칸에 나옵니다.
- 설정은 `%APPDATA%\cad-version-converter\settings.json`에 기억됩니다.

## 지원 버전

같은 파일 형식을 쓰는 AutoCAD 버전끼리 묶여 있습니다. 예를 들어 "2010 형식"으로 저장하면 AutoCAD 2010·2011·2012에서 열립니다.

| 선택 항목 | 열 수 있는 AutoCAD |
|---|---|
| AutoCAD 2018 | 2018 이후 전부 |
| AutoCAD 2013 | 2013 ~ 2017 |
| AutoCAD 2010 | 2010 ~ 2012 |
| AutoCAD 2007 | 2007 ~ 2009 |
| AutoCAD 2004 | 2004 ~ 2006 |
| AutoCAD 2000 | 2000 ~ 2002 |
| R14 / R13 / R12 | 해당 릴리스 |

낮은 버전으로 바꾸면 그 버전에 없는 기능(새 객체 종류 등)은 단순화되거나 빠질 수 있습니다.

## 개발

```
python -m unittest discover -s tests -v
```

테스트는 실제 ODA 대신 `tests/fake_oda.py`(같은 명령줄 인자를 받는 가짜 변환기)를 씁니다.

| 파일 | 내용 |
|---|---|
| `cadconv/core.py` | 버전 판별, ODA 호출, 일괄 변환 (화면과 무관) |
| `cadconv/app.py` | tkinter 창 |
| `main.py` | 실행 진입점 |
