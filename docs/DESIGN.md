# obsi-video-base 設計書

## 概要

親階層のフォルダを走査して、MP4ファイルを再帰的にスキャンし、
Obsidian用のMarkdownノートとサムネイル画像を自動生成するスクリプト。

---

## ディレクトリ構成

```
video\        ← videoルート兼親ディレクトリ
├── shorts\
│   └── sample.mp4
├── xx\
│   └── yy.mp4
└── obsidian\                      ← Obsidian vault / 作業ディレクトリ
    ├── bases\
    │   ├── videos.base            ← Bases ビュー定義
    │   └── BASES_SYNTAX.md        ← Bases文法メモ
    ├── metadata\
    │   └── {id}.md                ← 生成するMarkdown
    ├── thumb\
    │   ├── {id}-fp10.jpg          ← サムネイル（10%地点）
    │   ├── {id}-fp50.jpg          ← サムネイル（50%地点）
    │   └── {id}-fp80.jpg          ← サムネイル（80%地点）
    └── script\
        ├── gen.py                 ← 生成スクリプト
        └── DESIGN.md              ← 本書
```

---

## ID・ハッシュ生成方式

| 要素         | 値                              | 例              |
| ---------- | ------------------------------- | -------------- |
| `hash_src` | ファイル先頭128KB + 末尾128KB のバイト列 | —              |
| `id`       | SHA256(hash_src) の先頭12文字（hex） | `a1b2c3d4e5f6` |

- **ファイル内容ベース**のためリネーム・移動しても同じIDを維持
- 先頭128KB + 末尾128KB のみ読み込むので大きなMP4でも高速
- ファイル名・特殊文字を含まないためファイルシステム上も安全
- `title` フィールドにファイル名（拡張子なし）を別途保持するため検索性は維持
- 12文字（48bit）で10万件でも衝突確率 < 0.1%

---

## 処理フロー

```
python script\gen.py 起動
    │
    ▼
videoルート（..）を再帰スキャン（*.mp4）
obsidian/ 以下は除外
    │
    ├── Phase 1: 各MP4ファイルに対して
    │       │
    │       ▼
    │   ハッシュ計算（id算出）
    │   title / folder / src を算出
    │       │
    │       ▼
    │   欠損サムネイルを確認（MDの有無に関係なく）
    │       ├── 欠損あり → ffprobe で duration 取得
    │       │             → ffmpeg でサムネイル補完
    │       └── 欠損なし → スキップ
    │       │
    │       ▼
    │   metadata/{id}.md の処理
    │       ├── なし       → ffprobe（未取得なら）→ MD新規生成（created）
    │       ├── あり・変化なし → スキップ（skip）
    │       └── あり・移動/リネーム → title/source/folder/リンクを更新（updated）
    │
    ▼
Phase 2: 孤立ファイルの削除
    metadata/ 内のMDを走査
    Phase 1で収集したIDセットにないMD → 削除
    対応する thumb/{id}-fp10/50/80.jpg も削除
    │
    ▼
完了サマリー表示
（created / updated / skipped / errors / orphans deleted）
```

---

## folderフィールドの定義

MP4のパス（videoルート相対）から親ディレクトリ部分すべてを使用。

| MP4パス（相対） | folder値 |
|----------------|---------|
| `xx/yy.mp4` | `xx` |
| `aa/bb/cc.mp4` | `aa/bb` |
| `yy.mp4`（直下） | `""`（空） |

---

## 生成するMDフォーマット

パスは `obsidian/metadata/{id}.md` からの相対パスで記述する。

```markdown
---
id: a1b2c3d4e5f6
type: video
title: myvideo
source: ../../xx/myvideo.mp4
thumb: fp10
folder: xx
duration: 142
created: 2026-05-17
tags: []
---

# myvideo

## Preview

![[../thumb/a1b2c3d4e5f6-fp10.jpg]]
![[../thumb/a1b2c3d4e5f6-fp50.jpg]]
![[../thumb/a1b2c3d4e5f6-fp80.jpg]]

## Video

[[myvideo.mp4]]
![[myvideo.mp4]]
```

### thumbプロパティの運用

- 値は `fp10` / `fp50` / `fp80`（アルファベット始まりの文字列）
- デフォルト: `fp10`
- ObsidianのプロパティタイプをSelectに設定し3択ドロップダウンで切り替え
- Basesのformulaが値をそのままサムネイルパスに結合して表示に反映

**Obsidian設定手順:** 設定 → プロパティ → `thumb` → 型を **Select** → 選択肢に `fp10` / `fp50` / `fp80` を追加

---

## 移動・リネーム追跡

ファイルが移動またはリネームされた場合、ハッシュは変わらないためIDは同じMDに対応する。
スクリプト実行時に以下のフィールドを自動更新する：

| フィールド | 更新内容 |
|-----------|---------|
| `title` | 新しいファイル名（拡張子なし） |
| `source` | 新しい相対パス |
| `folder` | 新しいフォルダパス |
| `[[...mp4]]` | Videoセクションのリンク |
| `![[...mp4]]` | Videoセクションの埋め込み |

`thumb` / `tags` / `created` などユーザー編集済みフィールドは変更しない。

---

## サムネイル抽出

- ツール: `ffmpeg`
- 抽出タイミング: **10% / 50% / 80%** の3点
- 出力サイズ: **640px幅**（縦は比率維持、`scale=640:-2`）
- duration取得失敗時のフォールバック秒数: `fp10`=0.5s / `fp50`=2.5s / `fp80`=5.0s
- 命名: `{id}-fp10.jpg`, `{id}-fp50.jpg`, `{id}-fp80.jpg`
- MDが存在してもサムネイルが欠損していれば補完生成する

---

## duration取得

- ツール: `ffprobe`
- 出力: 秒数（float → int に切り捨て）
- 呼び出し条件: サムネイル欠損あり、またはMD新規生成時のみ（両方そろっていれば呼ばない）

---

## Bases連携

`bases/videos.base` でメタデータノートと動画・サムネイルを紐付けてカード表示。

```yaml
formulas:
  thumbnail: image("thumb/" + file.name.replace(/\.md$/, "") + "-" + thumb + ".jpg")
  open: link(source)
views:
  - type: cards
    name: 動画一覧
    filters:
      and:
        - file.folder == "obsidian/metadata"
    order:
      - title
      - folder
      - created
      - tags
      - formula.open
    sort: []
    image: formula.thumbnail
```

---

## 依存関係

| 依存 | 用途 | 入手方法 |
|------|------|---------|
| Python 3.8+ | スクリプト本体 | python.org |
| ffmpeg | サムネイル抽出・リサイズ | ffmpeg.org / winget |
| ffprobe | duration取得 | ffmpegに同梱 |

標準ライブラリのみ使用（`pathlib`, `hashlib`, `re`, `subprocess`, `datetime`, `argparse`）。

---

## CLIオプション

| オプション | 説明 |
|-----------|------|
| （なし） | 未処理のMP4のみ生成、孤立ファイルを削除 |
| `--force` | 既存MDとサムネイルを上書き再生成 |
| `--dry-run` | ファイル操作なしで対象と孤立ファイルを表示 |
| `--video-root PATH` | videoルートを明示指定（デフォルト: `..`） |

---

## エラーハンドリング方針

| ケース | 対応 |
|--------|------|
| ffmpeg/ffprobeが見つからない | 起動時に検出し即終了、インストール手順を表示 |
| duration取得失敗 | `duration: 0` で続行、フォールバック秒数でサムネ抽出 |
| サムネイル抽出失敗 | 警告出力して続行（MDは生成） |
| MD書き込み失敗 | エラーログに記録し次のファイルへ継続 |

---

## 実行例

```powershell
python script\gen.py
python script\gen.py --dry-run
python script\gen.py --force
```

---

## 今後の拡張候補（現時点では実装しない）

- タグの自動付与（フォルダ名ベース）
- 既存MDのduration更新のみ行うモード
