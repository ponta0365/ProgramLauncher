# Program Launcher

Windows 向けの常駐コマンドランチャーです。

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## 現在の実装範囲

- 検索兼コマンド入力
- `app` / `ps` / `file` / `url` 実行
- タスクトレイ常駐
- グローバルホットキー
- 設定 GUI からの追加・編集・削除
- グループ分け、並べ替え、一括登録
- JSON 設定保存とバックアップ / 復元
- ログ出力
- Windows スタートアップ登録

## 実行ファイル化

```powershell
.\.venv\Scripts\Activate.ps1
.\build_exe.ps1 -Clean
```

生成先:

- `dist\ProgramLauncher\ProgramLauncher.exe`

## 配布物に含めるファイル

ビルドスクリプトは以下を `dist\ProgramLauncher` にコピーします。

- `ProgramLauncher.exe`
- `ProgramLauncher.bat`
- `README.md`
- `THIRD_PARTY_NOTICES.txt`
- `licenses\PyInstaller-COPYING.txt`
- `LICENSE` または `LICENSE.txt` が存在する場合はそのファイル

## 配布時の注意

- ワンディレクトリ配布を前提にしています
- 設定は実行ファイルと同じベースディレクトリ配下の `data` に保存されます
- ログは `logs\app.log` に出力されます
- スタートアップ登録は `%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\ProgramLauncher.cmd` を使います

## ライセンス表記

- 第三者ライセンス情報は `THIRD_PARTY_NOTICES.txt` にまとめています
- PySide6 については `THIRD_PARTY_NOTICES.txt` に公式ライセンス情報への参照を記載しています
- 自作部分のライセンスを明示したい場合は、リポジトリ直下に `LICENSE` か `LICENSE.txt` を置いてからビルドしてください
