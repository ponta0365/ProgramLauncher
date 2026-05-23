# ProgramLauncher Release

Windows向けの常駐ランチャーです。

## 変更点
- ホットキー起動
- Alt 2回押し起動
- グループ管理
- 一括登録
- バックアップ/復元
- EXE配布
- GitHub ActionsによるWindowsビルド

## 配布物
- `ProgramLauncher_release.zip`
- `ProgramLauncher.exe`

## 注意
- 起動時の自動起動は `ProgramLauncher.cmd` を使用します
- 設定は `data/launcher_config.json` に保存されます

## 謝辞
- Python, PySide6 / Qt for Python, PyInstaller の開発者の皆様に感謝します
- それぞれのライブラリがなければ、このツールは成立しませんでした
