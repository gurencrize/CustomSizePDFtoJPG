# CustomSizePDFtoJPG

PDF のページを **任意のサイズ**の JPG 画像に変換するツール（CLI + Python ライブラリ）。

- 幅・高さをピクセル単位で指定（片方だけの指定ならアスペクト比を維持）
- `--dpi` / `--scale` によるサイズ指定にも対応
- 縦横比が合わないときの処理を `contain` / `cover` / `stretch` から選択
- ページ範囲指定、JPEG 品質、グレースケール出力、複数 PDF の一括変換

## インストール

```bash
pip install -e .
# 依存だけ入れる場合
pip install -r requirements.txt
```

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

## 実装メモ

- レンダリングは PyMuPDF、リサイズと JPEG 書き出しは Pillow（LANCZOS）。
- 目標サイズ以上の倍率で一度ラスタライズしてから縮小するため、拡大による
  ぼやけが起きにくくなっています。
- 1 ページあたりのピクセル数は 1 億で頭打ちにして、メモリ使用量を抑えています。
- パスワード保護された PDF、存在しないページなどは `ConversionError` を送出します。

## テスト

```bash
pip install -e ".[dev]"
pytest
```
