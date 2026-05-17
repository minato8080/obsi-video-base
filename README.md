# obsi-video-base

ObsidianのBasesを動画ギャラリーとして扱うためのテンプレート。
親階層のフォルダを走査して、MP4ファイルを再帰的にスキャンし、Obsidian用のMarkdownノートとサムネイル画像を自動生成する。

## 必要なもの

- Python 3.8+
- ffmpeg / ffprobe（[ffmpeg.org](https://ffmpeg.org/) または `winget install ffmpeg`）

## 使い方

```powershell
python script\gen.py
```

| オプション | 説明 |
|-----------|------|
| `--dry-run` | ファイル操作なしで対象を確認 |
| `--force` | 既存MDとサムネイルを上書き再生成 |
| `--video-root PATH` | videoルートを明示指定（デフォルト: `..`） |

## 生成されるもの

1MP4あたり以下を生成する。

```
metadata/{id}.md          ← Markdownノート
thumb/{id}-fp10.jpg       ← サムネイル（動画の10%地点、640px幅）
thumb/{id}-fp50.jpg       ← サムネイル（50%地点）
thumb/{id}-fp80.jpg       ← サムネイル（80%地点）
```

## サムネイルの切り替え

各ノートの `thumb` プロパティ（`fp10` / `fp50` / `fp80`）を変更すると
Basesビューに表示されるサムネイルが切り替わる。

Obsidianのプロパティ設定で `thumb` をSelect型にし、
選択肢に `fp10` / `fp50` / `fp80` を追加するとドロップダウンで選択できる。

## 動作仕様

- **ID**: ファイル先頭+末尾128KBのSHA256（12文字）。リネーム・移動してもIDは変わらない
- **スキップ**: `metadata/{id}.md` が存在すれば処理をスキップ
- **更新**: ファイルが移動・リネームされた場合、MDの `title` / `source` / `folder` とVideoセクションのリンクを自動更新
- **サムネイル補完**: MDがあってもサムネイルが欠損していれば自動生成
- **孤立削除**: 対応するMP4が存在しないMDとサムネイルを自動削除

詳細は `DESIGN.md` を参照。
