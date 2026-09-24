"""CAD 버전 변환기 창 프로그램 (tkinter)."""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import core

APP_TITLE = "CAD 버전 변환기"
ODA_DOWNLOAD_URL = "https://www.opendesign.com/guestfiles/oda_file_converter"


def _settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return os.path.join(base, "cad-version-converter", "settings.json")


def load_settings() -> dict:
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    path = _settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x600")
        self.minsize(680, 460)

        s = load_settings()
        self.files: list[str] = []
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker: threading.Thread | None = None

        labels = [name for _, _, name in core.VERSIONS]
        saved_version = s.get("version", "ACAD2010")
        self.var_version = tk.StringVar(value=next(
            (name for code, _, name in core.VERSIONS if code == saved_version), labels[2]))
        self.var_type = tk.StringVar(value=s.get("file_type", "DWG"))
        self.var_same_folder = tk.BooleanVar(value=s.get("same_folder", True))
        self.var_out_dir = tk.StringVar(value=s.get("out_dir", ""))
        self.var_suffix = tk.BooleanVar(value=s.get("add_suffix", True))
        self.var_audit = tk.BooleanVar(value=s.get("audit", True))
        self.var_oda = tk.StringVar(value=s.get("oda_path") or core.find_oda_converter() or "")
        self.var_status = tk.StringVar(value="변환할 파일을 추가하세요.")

        self._build(labels)
        self._toggle_out_dir()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        if not self.var_oda.get():
            self.after(300, self._warn_no_oda)

    # ---------- 화면 구성 ----------
    def _build(self, labels: list[str]) -> None:
        pad = {"padx": 8, "pady": 4}

        # 파일 목록
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="파일 추가", command=self._add_files).pack(side="left")
        ttk.Button(top, text="폴더 추가", command=self._add_folder).pack(side="left", padx=4)
        ttk.Button(top, text="선택 제거", command=self._remove_selected).pack(side="left")
        ttk.Button(top, text="모두 비우기", command=self._clear).pack(side="left", padx=4)

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=8)
        cols = ("name", "version", "status")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("name", text="파일")
        self.tree.heading("version", text="현재 버전")
        self.tree.heading("status", text="상태")
        self.tree.column("name", width=380)
        self.tree.column("version", width=200)
        self.tree.column("status", width=220)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Delete>", lambda e: self._remove_selected())

        # 변환 설정
        opt = ttk.LabelFrame(self, text="변환 설정")
        opt.pack(fill="x", **pad)
        opt.columnconfigure(1, weight=1)

        ttk.Label(opt, text="바꿀 버전").grid(row=0, column=0, sticky="w", **pad)
        ttk.Combobox(opt, textvariable=self.var_version, values=labels,
                     state="readonly", width=32).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(opt, text="저장 형식").grid(row=1, column=0, sticky="w", **pad)
        fmt = ttk.Frame(opt)
        fmt.grid(row=1, column=1, sticky="w", **pad)
        ttk.Radiobutton(fmt, text="DWG", value="DWG", variable=self.var_type).pack(side="left")
        ttk.Radiobutton(fmt, text="DXF", value="DXF", variable=self.var_type).pack(side="left", padx=8)

        ttk.Label(opt, text="저장 위치").grid(row=2, column=0, sticky="w", **pad)
        out = ttk.Frame(opt)
        out.grid(row=2, column=1, sticky="ew", **pad)
        out.columnconfigure(1, weight=1)
        ttk.Checkbutton(out, text="원본과 같은 폴더", variable=self.var_same_folder,
                        command=self._toggle_out_dir).grid(row=0, column=0, sticky="w")
        self.ent_out = ttk.Entry(out, textvariable=self.var_out_dir)
        self.ent_out.grid(row=0, column=1, sticky="ew", padx=6)
        self.btn_out = ttk.Button(out, text="찾아보기", command=self._pick_out_dir)
        self.btn_out.grid(row=0, column=2)

        chk = ttk.Frame(opt)
        chk.grid(row=3, column=1, sticky="w", **pad)
        ttk.Checkbutton(chk, text="파일 이름 뒤에 버전 붙이기 (예: 도면_2010.dwg)",
                        variable=self.var_suffix).pack(side="left")
        ttk.Checkbutton(chk, text="오류 검사·복구(Audit)",
                        variable=self.var_audit).pack(side="left", padx=12)

        ttk.Label(opt, text="ODA 변환기").grid(row=4, column=0, sticky="w", **pad)
        oda = ttk.Frame(opt)
        oda.grid(row=4, column=1, sticky="ew", **pad)
        oda.columnconfigure(0, weight=1)
        ttk.Entry(oda, textvariable=self.var_oda).grid(row=0, column=0, sticky="ew")
        ttk.Button(oda, text="찾아보기", command=self._pick_oda).grid(row=0, column=1, padx=4)
        ttk.Button(oda, text="내려받기", command=lambda: webbrowser.open(ODA_DOWNLOAD_URL)
                   ).grid(row=0, column=2)

        # 진행 상황
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x", side="top")
        ttk.Label(bottom, textvariable=self.var_status).pack(side="left", pady=4)
        self.btn_convert = ttk.Button(bottom, text="변환 시작", command=self._start)
        self.btn_convert.pack(side="right", pady=4)
        self.btn_stop = ttk.Button(bottom, text="중지", command=self.stop_flag.set,
                                   state="disabled")
        self.btn_stop.pack(side="right", padx=4, pady=4)

    # ---------- 파일 목록 ----------
    def _add_paths(self, paths: list[str]) -> None:
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if p in self.files or not p.lower().endswith(core.CAD_EXTENSIONS):
                continue
            self.files.append(p)
            self.tree.insert("", "end", iid=p,
                             values=(p, core.detect_version(p), "대기"))
            added += 1
        self.var_status.set(f"{added}개 추가됨 · 총 {len(self.files)}개")

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="CAD 파일 선택",
            filetypes=[("CAD 파일", "*.dwg *.dxf"), ("DWG", "*.dwg"), ("DXF", "*.dxf")])
        self._add_paths(list(paths))

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="CAD 파일이 들어 있는 폴더")
        if not folder:
            return
        sub = messagebox.askyesno(APP_TITLE, "하위 폴더의 파일도 함께 추가할까요?")
        self._add_paths(core.collect_cad_files(folder, recursive=sub))

    def _remove_selected(self) -> None:
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.files.remove(iid)
        self.var_status.set(f"총 {len(self.files)}개")

    def _clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self.var_status.set("변환할 파일을 추가하세요.")

    # ---------- 설정 ----------
    def _toggle_out_dir(self) -> None:
        state = "disabled" if self.var_same_folder.get() else "normal"
        self.ent_out.configure(state=state)
        self.btn_out.configure(state=state)

    def _pick_out_dir(self) -> None:
        folder = filedialog.askdirectory(title="저장할 폴더")
        if folder:
            self.var_out_dir.set(folder)

    def _pick_oda(self) -> None:
        types = [("ODAFileConverter", "ODAFileConverter.exe"), ("모든 파일", "*.*")] \
            if sys.platform == "win32" else [("모든 파일", "*")]
        path = filedialog.askopenfilename(title="ODAFileConverter 실행 파일", filetypes=types)
        if path:
            self.var_oda.set(path)

    def _warn_no_oda(self) -> None:
        if messagebox.askyesno(
                APP_TITLE,
                "ODA File Converter를 찾지 못했습니다.\n"
                "DWG 변환에는 무료 프로그램인 ODA File Converter가 필요합니다.\n\n"
                "내려받기 페이지를 열까요?\n"
                "(설치 후 이 프로그램을 다시 켜면 자동으로 찾습니다)"):
            webbrowser.open(ODA_DOWNLOAD_URL)

    def _version_code(self) -> str:
        label = self.var_version.get()
        return next(code for code, _, name in core.VERSIONS if name == label)

    def _collect_settings(self) -> dict:
        return {
            "version": self._version_code(),
            "file_type": self.var_type.get(),
            "same_folder": self.var_same_folder.get(),
            "out_dir": self.var_out_dir.get(),
            "add_suffix": self.var_suffix.get(),
            "audit": self.var_audit.get(),
            "oda_path": self.var_oda.get(),
        }

    # ---------- 변환 ----------
    def _start(self) -> None:
        if not self.files:
            messagebox.showinfo(APP_TITLE, "먼저 변환할 파일을 추가하세요.")
            return
        exe = self.var_oda.get().strip()
        if not exe or not os.path.isfile(exe):
            self._warn_no_oda()
            return
        out_dir = None
        if not self.var_same_folder.get():
            out_dir = self.var_out_dir.get().strip()
            if not out_dir:
                messagebox.showinfo(APP_TITLE, "저장할 폴더를 고르세요.")
                return

        settings = self._collect_settings()
        save_settings(settings)
        files = list(self.files)
        for f in files:
            self.tree.set(f, "status", "대기")
        self.progress.configure(maximum=len(files), value=0)
        self.stop_flag.clear()
        self.btn_convert.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.var_status.set("변환 중…")

        def progress(i: int, r: core.Result) -> None:
            self.events.put(("done", i, r))
            if i + 1 < len(files) and not self.stop_flag.is_set():
                self.events.put(("running", files[i + 1]))

        def work() -> None:
            results = core.convert_many(
                exe, files, out_dir, settings["version"], settings["file_type"],
                settings["audit"], settings["add_suffix"],
                on_progress=progress, should_stop=self.stop_flag.is_set)
            self.events.put(("finished", results, len(files)))

        self.tree.set(files[0], "status", "변환 중…")
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "running":
                    if self.tree.exists(ev[1]):
                        self.tree.set(ev[1], "status", "변환 중…")
                elif ev[0] == "done":
                    _, i, r = ev
                    self.progress.configure(value=i + 1)
                    if self.tree.exists(r.source):
                        text = "✔ " + os.path.basename(r.output) if r.ok else "✖ " + r.message
                        self.tree.set(r.source, "status", text)
                elif ev[0] == "finished":
                    self._finish(ev[1], ev[2])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, results: list, total: int) -> None:
        ok = sum(1 for r in results if r.ok)
        fail = len(results) - ok
        skipped = total - len(results)
        msg = f"완료: 성공 {ok}개"
        if fail:
            msg += f", 실패 {fail}개"
        if skipped:
            msg += f", 중지로 건너뜀 {skipped}개"
        self.var_status.set(msg)
        self.btn_convert.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        messagebox.showinfo(APP_TITLE, msg)

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_TITLE, "변환 중입니다. 그래도 닫을까요?"):
                return
            self.stop_flag.set()
        save_settings(self._collect_settings())
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
