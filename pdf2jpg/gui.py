"""PDF → JPG 変換の tkinter GUI."""

from __future__ import annotations

import dataclasses
import queue
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from pdf2jpg.converter import ConversionError, iter_convert_pdf, pymupdf
from pdf2jpg.form import FormError, FormResult, build_options, describe_size

PAD = 8


@dataclass
class _Message:
    """ワーカースレッドから UI へ渡す通知."""

    kind: str  # "log" | "progress" | "done"
    text: str = ""
    current: int = 0
    total: int = 0


def _count_pages(pdf_path: Path, form: FormResult) -> int:
    with pymupdf.open(pdf_path) as document:
        if document.needs_pass:
            raise ConversionError(f"パスワード保護された PDF です: {pdf_path.name}")
        selected = form.pages_for_document(document.page_count)
        return len(selected) if selected is not None else document.page_count


def _convert_all(
    pdf_paths: list[Path],
    output_dir: Path,
    form: FormResult,
    outbox: "queue.Queue[_Message]",
    cancel: threading.Event,
) -> None:
    """ワーカースレッド本体。進捗を outbox 経由で UI に送る."""
    converted = 0
    failed = 0
    try:
        totals: dict[Path, int] = {}
        total = 0
        for pdf_path in pdf_paths:
            try:
                totals[pdf_path] = _count_pages(pdf_path, form)
                total += totals[pdf_path]
            except Exception as exc:
                totals[pdf_path] = 0
                outbox.put(_Message("log", f"✗ {pdf_path.name}: {exc}"))
                failed += 1

        outbox.put(_Message("progress", current=0, total=max(total, 1)))

        for pdf_path in pdf_paths:
            if cancel.is_set():
                break
            if not totals.get(pdf_path):
                continue
            outbox.put(_Message("log", f"▶ {pdf_path.name} を変換中..."))
            try:
                with pymupdf.open(pdf_path) as document:
                    pages = form.pages_for_document(document.page_count)
                options = form.options
                if pages is not None:
                    options = dataclasses.replace(options, pages=pages)
                for destination in iter_convert_pdf(pdf_path, output_dir, options):
                    converted += 1
                    outbox.put(_Message("log", f"  {destination}"))
                    outbox.put(_Message("progress", current=converted, total=total))
                    if cancel.is_set():
                        outbox.put(_Message("log", "中断しました。"))
                        break
            except (ConversionError, ValueError) as exc:
                failed += 1
                outbox.put(_Message("log", f"✗ {pdf_path.name}: {exc}"))
            except Exception:  # pragma: no cover - 想定外のエラーも UI に出す
                failed += 1
                outbox.put(_Message("log", f"✗ {pdf_path.name}:\n{traceback.format_exc()}"))
    finally:
        summary = f"完了: {converted} 枚を出力しました。"
        if failed:
            summary += f" ({failed} ファイルでエラー)"
        if cancel.is_set():
            summary = f"中断: {converted} 枚を出力しました。"
        outbox.put(_Message("done", text=summary))


class App(ttk.Frame):
    """メインウィンドウ."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=PAD)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.pdf_paths: list[Path] = []
        self.outbox: "queue.Queue[_Message]" = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None

        self.output_dir = tk.StringVar(value=str(Path.cwd() / "output"))
        self.size_mode = tk.StringVar(value="pixels")
        self.width = tk.StringVar(value="1920")
        self.height = tk.StringVar(value="1080")
        self.dpi = tk.StringVar(value="150")
        self.scale = tk.StringVar(value="1.0")
        self.fit = tk.StringVar(value="contain")
        self.background = tk.StringVar(value="#ffffff")
        self.quality = tk.IntVar(value=90)
        self.pages = tk.StringVar(value="")
        self.grayscale = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="PDF を追加してください。")

        self._build_widgets()
        self._update_size_mode()
        self.after(100, self._drain_queue)

    # ------------------------------------------------------------------ UI
    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        # --- 入力ファイル
        files = ttk.LabelFrame(self, text="変換する PDF", padding=PAD)
        files.grid(row=0, column=0, sticky="nsew")
        files.columnconfigure(0, weight=1)
        files.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(files, height=5, selectmode=tk.EXTENDED)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(files, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        buttons = ttk.Frame(files)
        buttons.grid(row=0, column=2, sticky="n", padx=(PAD, 0))
        ttk.Button(buttons, text="追加...", command=self.add_files).grid(row=0, column=0, sticky="ew")
        ttk.Button(buttons, text="削除", command=self.remove_selected).grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(buttons, text="すべて消去", command=self.clear_files).grid(row=2, column=0, sticky="ew")

        # --- 出力先
        output = ttk.Frame(self, padding=(0, PAD))
        output.grid(row=1, column=0, sticky="ew")
        output.columnconfigure(1, weight=1)
        ttk.Label(output, text="出力先:").grid(row=0, column=0, padx=(0, PAD))
        ttk.Entry(output, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(output, text="参照...", command=self.choose_output_dir).grid(row=0, column=2, padx=(PAD, 0))

        # --- 変換設定
        settings = ttk.LabelFrame(self, text="出力サイズ", padding=PAD)
        settings.grid(row=2, column=0, sticky="ew")
        settings.columnconfigure(5, weight=1)

        ttk.Radiobutton(
            settings, text="ピクセル指定", value="pixels",
            variable=self.size_mode, command=self._update_size_mode,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(settings, text="幅").grid(row=0, column=1, padx=(PAD, 2))
        self.width_entry = ttk.Entry(settings, textvariable=self.width, width=7)
        self.width_entry.grid(row=0, column=2)
        ttk.Label(settings, text="× 高さ").grid(row=0, column=3, padx=2)
        self.height_entry = ttk.Entry(settings, textvariable=self.height, width=7)
        self.height_entry.grid(row=0, column=4)
        ttk.Label(settings, text="px（片方を空欄にすると比率を維持）").grid(
            row=0, column=5, sticky="w", padx=(4, 0)
        )

        ttk.Radiobutton(
            settings, text="解像度 (dpi)", value="dpi",
            variable=self.size_mode, command=self._update_size_mode,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.dpi_entry = ttk.Entry(settings, textvariable=self.dpi, width=7)
        self.dpi_entry.grid(row=1, column=2, pady=(4, 0))

        ttk.Radiobutton(
            settings, text="倍率", value="scale",
            variable=self.size_mode, command=self._update_size_mode,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.scale_entry = ttk.Entry(settings, textvariable=self.scale, width=7)
        self.scale_entry.grid(row=2, column=2, pady=(4, 0))

        options = ttk.LabelFrame(self, text="オプション", padding=PAD)
        options.grid(row=3, column=0, sticky="ew", pady=(PAD, 0))
        options.columnconfigure(6, weight=1)

        ttk.Label(options, text="合わせ方:").grid(row=0, column=0, sticky="w")
        for index, (value, label) in enumerate(
            (("contain", "収める"), ("cover", "切り抜く"), ("stretch", "引き伸ばす"))
        ):
            ttk.Radiobutton(options, text=label, value=value, variable=self.fit).grid(
                row=0, column=1 + index, sticky="w", padx=(PAD, 0)
            )
        ttk.Label(options, text="余白色:").grid(row=0, column=4, padx=(PAD, 2))
        ttk.Entry(options, textvariable=self.background, width=9).grid(row=0, column=5)
        ttk.Button(options, text="選択...", command=self.choose_color).grid(
            row=0, column=6, sticky="w", padx=(4, 0)
        )

        ttk.Label(options, text="ページ:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(options, textvariable=self.pages, width=18).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Label(options, text="例: 1,3-5,8-（空欄で全ページ）").grid(
            row=1, column=3, columnspan=4, sticky="w", padx=(PAD, 0), pady=(6, 0)
        )

        ttk.Label(options, text="品質:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Scale(
            options, from_=1, to=100, orient="horizontal",
            variable=self.quality, command=lambda _v: self.quality.set(int(float(_v))),
        ).grid(row=2, column=1, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(options, textvariable=self.quality, width=4).grid(
            row=2, column=4, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(options, text="グレースケール", variable=self.grayscale).grid(
            row=2, column=5, columnspan=2, sticky="w", padx=(PAD, 0), pady=(6, 0)
        )

        # --- 実行
        actions = ttk.Frame(self, padding=(0, PAD))
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(2, weight=1)
        self.run_button = ttk.Button(actions, text="変換する", command=self.start)
        self.run_button.grid(row=0, column=0)
        self.cancel_button = ttk.Button(
            actions, text="中断", command=self.request_cancel, state="disabled"
        )
        self.cancel_button.grid(row=0, column=1, padx=(PAD, 0))
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.grid(row=0, column=2, sticky="ew", padx=(PAD, 0))

        ttk.Label(self, textvariable=self.status).grid(row=5, column=0, sticky="w")

        log_frame = ttk.LabelFrame(self, text="ログ", padding=PAD)
        log_frame.grid(row=6, column=0, sticky="nsew", pady=(PAD, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        self.log = tk.Text(log_frame, height=8, wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

    def _update_size_mode(self) -> None:
        mode = self.size_mode.get()
        for entry, active in (
            (self.width_entry, mode == "pixels"),
            (self.height_entry, mode == "pixels"),
            (self.dpi_entry, mode == "dpi"),
            (self.scale_entry, mode == "scale"),
        ):
            entry.configure(state="normal" if active else "disabled")

    # --------------------------------------------------------------- 操作
    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="PDF を選択", filetypes=[("PDF", "*.pdf"), ("すべて", "*.*")]
        )
        self.add_paths([Path(p) for p in paths])

    def add_paths(self, paths: list[Path]) -> None:
        for path in paths:
            if path not in self.pdf_paths:
                self.pdf_paths.append(path)
                self.listbox.insert("end", str(path))
        self._refresh_status()

    def remove_selected(self) -> None:
        for index in sorted(self.listbox.curselection(), reverse=True):
            self.listbox.delete(index)
            del self.pdf_paths[index]
        self._refresh_status()

    def clear_files(self) -> None:
        self.listbox.delete(0, "end")
        self.pdf_paths.clear()
        self._refresh_status()

    def choose_output_dir(self) -> None:
        directory = filedialog.askdirectory(title="出力先を選択")
        if directory:
            self.output_dir.set(directory)

    def choose_color(self) -> None:
        _rgb, color = colorchooser.askcolor(color=self.background.get())
        if color:
            self.background.set(color)

    def _refresh_status(self) -> None:
        count = len(self.pdf_paths)
        self.status.set(
            "PDF を追加してください。" if not count else f"{count} 個の PDF を選択中。"
        )

    def log_line(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # --------------------------------------------------------------- 変換
    def collect_form(self) -> FormResult:
        """入力欄から設定を組み立てる（不正なら :class:`FormError`）."""
        return build_options(
            size_mode=self.size_mode.get(),
            width=self.width.get(),
            height=self.height.get(),
            dpi=self.dpi.get(),
            scale=self.scale.get(),
            fit=self.fit.get(),
            background=self.background.get(),
            quality=str(self.quality.get()),
            pages=self.pages.get(),
            grayscale=bool(self.grayscale.get()),
        )

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.pdf_paths:
            messagebox.showwarning("PDF が未選択", "変換する PDF を追加してください。")
            return
        try:
            form = self.collect_form()
        except FormError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        output_dir = Path(self.output_dir.get().strip() or "output")
        self.cancel.clear()
        self.progress.configure(value=0, maximum=100)
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set(f"変換中... ({describe_size(form.options)})")
        self.log_line(f"出力先: {output_dir}  設定: {describe_size(form.options)}")

        self.worker = threading.Thread(
            target=_convert_all,
            args=(list(self.pdf_paths), output_dir, form, self.outbox, self.cancel),
            daemon=True,
        )
        self.worker.start()

    def request_cancel(self) -> None:
        self.cancel.set()
        self.status.set("中断しています...")

    def _drain_queue(self) -> None:
        try:
            while True:
                message = self.outbox.get_nowait()
                if message.kind == "log":
                    self.log_line(message.text)
                elif message.kind == "progress":
                    self.progress.configure(
                        maximum=max(message.total, 1), value=message.current
                    )
                elif message.kind == "done":
                    self.status.set(message.text)
                    self.log_line(message.text)
                    self.run_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)


def main(argv: list[str] | None = None) -> int:
    """GUI を起動する。引数に PDF を渡すと最初から一覧に入る."""
    root = tk.Tk()
    root.title("CustomSizePDFtoJPG")
    root.minsize(720, 620)
    app = App(root)
    if argv:
        app.add_paths([Path(a) for a in argv])
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(main(sys.argv[1:]))
