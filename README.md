# CustomSizePDFtoJPG

PDF のページを **任意のサイズ**の JPG 画像に変換するツール（GUI + CLI + Python ライブラリ）。

- 幅・高さをピクセル単位で指定（片方だけの指定ならアスペクト比を維持）
- `--dpi` / `--scale` によるサイズ指定にも対応
- 縦横比が合わないときの処理を `contain` / `cover` / `stretch` から選択
- ページ範囲指定、JPEG 品質、グレースケール出力、複数 PDF の一括変換
- tkinter 製の GUI（進捗表示・中断つき）

## インストール

```bash
pip install -e .
# 依存だけ入れる場合
pip install -r requirements.txt
```

## 使い方（GUI）

```bash
pdf2jpg-gui           # インストール済みの場合
python -m pdf2jpg --gui   # リポジトリ内から直接
python -m pdf2jpg --gui doc.pdf   # 最初から一覧に追加した状態で起動
```

標準ライブラリの tkinter を使います。入っていない場合は OS のパッケージを入れてください
（例: Debian/Ubuntu なら `sudo apt install python3-tk`、macOS の Homebrew なら `brew install python-tk`）。

GUI でできること:

- PDF を複数追加して一括変換（追加 / 削除 / すべて消去）
- 出力先フォルダの選択
- サイズの決め方を「ピクセル指定 / 解像度 (dpi) / 倍率」から選択（選んだ欄以外は自動で無効化）
- 合わせ方（収める・切り抜く・引き伸ばす）、余白色（カラーピッカー付き）、ページ指定、品質、グレースケール
- 変換は別スレッドで実行するので画面が固まらず、進捗バー・ログ表示・中断ボタンが使える

## 使い方（CLI）

```bash
# 1920x1080 に収める（余白は白）
pdf2jpg doc.pdf --size 1920x1080

# 幅 1080px、高さはアスペクト比から自動決定
pdf2jpg doc.pdf --size 1080x

# 高さ 720px、幅は自動
pdf2jpg doc.pdf --size x720

# 正方形サムネイルとして中央を切り抜く
pdf2jpg doc.pdf --size 800x800 --fit cover

# 300dpi で 1〜3 ページと 7 ページのみ、出力先を指定
pdf2jpg doc.pdf --dpi 300 --pages 1-3,7 -o images/

# 複数 PDF をまとめて変換
pdf2jpg a.pdf b.pdf --size 1200x630 --quality 95
```

出力ファイル名は `<PDF名>_p001.jpg` の形式（既定の出力先は `output/`）。

### オプション

| オプション | 説明 | 既定値 |
| --- | --- | --- |
| `-o, --output-dir` | 出力先ディレクトリ | `output` |
| `-s, --size` | 出力サイズ `WIDTHxHEIGHT` / `WIDTHx` / `xHEIGHT` | 未指定（dpi を使用） |
| `--dpi` | `--size` 未指定時の解像度 | `150` |
| `--scale` | `--size` 未指定時の倍率（`--dpi` より優先） | 未指定 |
| `--fit` | 幅と高さを両方指定したときの合わせ方 | `contain` |
| `--background` | `contain` の余白色 | `#ffffff` |
| `-q, --quality` | JPEG 品質（1〜100） | `90` |
| `-p, --pages` | 変換するページ（`1,3-5,8-`） | 全ページ |
| `--grayscale` | グレースケールで出力 | オフ |
| `--quiet` | 進捗を表示しない | オフ |

### `--fit` の違い

指定した幅・高さがページの縦横比と一致しない場合の挙動です。

- `contain`: 全体が収まるよう縮小し、余りを `--background` の色で埋める（既定）
- `cover`: 指定サイズを埋めるよう拡大し、はみ出す部分を中央基準で切り抜く
- `stretch`: 縦横比を無視して引き伸ばす

## 使い方（ライブラリ）

```python
from pdf2jpg import ConvertOptions, convert_pdf

paths = convert_pdf(
    "doc.pdf",
    "output",
    ConvertOptions(width=1920, height=1080, fit="contain", quality=95),
)
print(paths)  # [PosixPath('output/doc_p001.jpg'), ...]
```

ページ数が多い場合は逐次処理版も使えます。

```python
from pdf2jpg import ConvertOptions, iter_convert_pdf, parse_pages

for path in iter_convert_pdf("doc.pdf", "output", ConvertOptions(dpi=300)):
    print("生成:", path)
```

## 構成

| ファイル | 役割 |
| --- | --- |
| `pdf2jpg/converter.py` | 変換のコア処理 |
| `pdf2jpg/cli.py` | コマンドライン |
| `pdf2jpg/form.py` | GUI 入力（文字列）の検証とオプション生成。tkinter に非依存 |
| `pdf2jpg/gui.py` | tkinter の画面と変換ワーカー |

## 実装メモ

- レンダリングは PyMuPDF、リサイズと JPEG 書き出しは Pillow（LANCZOS）。
- 目標サイズ以上の倍率で一度ラスタライズしてから縮小するため、拡大による
  ぼやけが起きにくくなっています。
- 1 ページあたりのピクセル数は 1 億で頭打ちにして、メモリ使用量を抑えています。
- パスワード保護された PDF、存在しないページなどは `ConversionError` を送出します。
- GUI の入力検証は `pdf2jpg/form.py` に切り出してあるため、tkinter が無い環境でもテストできます。

## テスト

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_gui.py` は tkinter が無い環境では自動でスキップされます。
ディスプレイの無い環境で GUI ごとテストする場合は仮想ディスプレイを使ってください。

```bash
xvfb-run -a pytest
```
