"""GUI のテスト。tkinter とディスプレイが無い環境ではスキップされる."""

import queue
import threading
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

tk = pytest.importorskip("tkinter")

from pdf2jpg.form import build_options  # noqa: E402
from pdf2jpg.gui import App, _convert_all  # noqa: E402


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    for index in range(2):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 144), f"page {index + 1}", fontsize=48)
    document.save(path)
    document.close()
    return path


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:  # ディスプレイなし
        pytest.skip(f"ディスプレイを開けません: {exc}")
    window.withdraw()
    yield window
    window.destroy()


def _drain(outbox: "queue.Queue") -> list:
    messages = []
    while not outbox.empty():
        messages.append(outbox.get_nowait())
    return messages


def test_worker_converts_and_reports_progress(sample_pdf, tmp_path):
    """ワーカーは tkinter 抜きでも動く（GUI なし環境でも実行される）."""
    outbox: "queue.Queue" = queue.Queue()
    form = build_options(size_mode="pixels", width="400", height="300")
    _convert_all([sample_pdf], tmp_path / "out", form, outbox, threading.Event())

    messages = _drain(outbox)
    assert messages[-1].kind == "done"
    assert "2 枚" in messages[-1].text
    assert max(m.current for m in messages if m.kind == "progress") == 2

    files = sorted((tmp_path / "out").glob("*.jpg"))
    assert len(files) == 2
    with Image.open(files[0]) as image:
        assert image.size == (400, 300)


def test_worker_reports_missing_file(tmp_path):
    outbox: "queue.Queue" = queue.Queue()
    form = build_options(size_mode="dpi", dpi="72")
    _convert_all([tmp_path / "missing.pdf"], tmp_path, form, outbox, threading.Event())

    messages = _drain(outbox)
    assert any("✗" in m.text for m in messages if m.kind == "log")
    assert "エラー" in messages[-1].text


def test_worker_stops_when_cancelled(sample_pdf, tmp_path):
    outbox: "queue.Queue" = queue.Queue()
    cancel = threading.Event()
    cancel.set()
    _convert_all(
        [sample_pdf], tmp_path / "out", build_options(size_mode="dpi", dpi="72"),
        outbox, cancel,
    )
    assert "中断" in _drain(outbox)[-1].text


def test_app_collects_form_values(root, sample_pdf, tmp_path):
    app = App(root)
    app.add_paths([sample_pdf])
    app.width.set("640")
    app.height.set("480")
    app.fit.set("cover")
    app.pages.set("2")

    result = app.collect_form()
    assert (result.options.width, result.options.height) == (640, 480)
    assert result.options.fit == "cover"
    assert result.pages_for_document(2) == [1]
    assert app.pdf_paths == [sample_pdf]


def test_app_size_mode_toggles_entry_state(root):
    app = App(root)
    assert str(app.width_entry["state"]) == "normal"
    assert str(app.dpi_entry["state"]) == "disabled"

    app.size_mode.set("dpi")
    app._update_size_mode()
    assert str(app.width_entry["state"]) == "disabled"
    assert str(app.dpi_entry["state"]) == "normal"


def test_app_file_list_management(root, tmp_path):
    app = App(root)
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    app.add_paths([first, second, first])  # 重複は無視される
    assert app.pdf_paths == [first, second]
    assert app.listbox.size() == 2

    app.listbox.selection_set(0)
    app.remove_selected()
    assert app.pdf_paths == [second]

    app.clear_files()
    assert app.pdf_paths == [] and app.listbox.size() == 0


def test_app_end_to_end_conversion(root, sample_pdf, tmp_path):
    app = App(root)
    app.add_paths([sample_pdf])
    app.output_dir.set(str(tmp_path / "gui-out"))
    app.width.set("320")
    app.height.set("240")
    app.start()

    app.worker.join(timeout=60)
    assert app.worker is not None and not app.worker.is_alive()
    app._drain_queue()
    root.update()

    files = sorted((tmp_path / "gui-out").glob("*.jpg"))
    assert len(files) == 2
    with Image.open(files[0]) as image:
        assert image.size == (320, 240)
    assert "完了" in app.status.get()
