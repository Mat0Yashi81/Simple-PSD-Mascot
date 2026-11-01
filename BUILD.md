# ビルドとライブラリの差し替え

## アプリのビルド

Windows x64、Python **3.12.0**、Microsoft公式Visual C++ x64ランタイムを用意します。
ソースを新しい作業フォルダに展開し、PowerShellで実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --require-hashes -r requirements-lock.txt
.\build.ps1
```

`dist/Simple-PSD-Mascot-v1.0.0/` が実行用フォルダです。exeだけを取り出さないでください。
`build.ps1` はビルド用PATHをWindowsのみに限定し、外部のQtや画像DLLの混入を抑えます。
専用venvには他のPySide6世代・Pdf・WebEngineパッケージを追加しないでください。

`public-release.spec` が未使用のGPL/PDFプラグイン等を除外します。
`tools/normalize_msvc_imports.py` が3つの拡張モジュールのMSVCP参照名を調整し、
MicrosoftランタイムDLLを省略します。変更と省略はJSONに記録します。
画像処理の命令やPSDの合成順は変更しません。

このビルド操作だけでは、ライセンス文・アプリソース・対応ソースの同梱は完了しません。
最終配布フォルダにはこの公開準備版と同じ文書と `third-party-sources/` を必ず収録してください。
公開先での配置と必要な表示は `PUBLICATION_STATUS.md`、`PUBLISHING.md` を参照してください。

## 自作コードのテスト

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

テストは人工的に作成したPSDを使い、作者・利用者の実際のPSDを必要としません。
`--distribution-check INPUT_DIR NEW_OUTPUT_DIR` は配布exe専用の任意診断です。
INPUT_DIRに人工PSD `fixture.psd` と自作テスト音声 `sample.wav/mp3/ogg` を置きます。
NEW_OUTPUT_DIRは未作成のパスを指定します。通常の設定・キャッシュは読み書きしません。

## LGPLライブラリの差し替え

この配布形式はDLLを `_internal/` 以下に分離しています。署名検証・改変禁止チェック・
作者の承認を必要とする仕組みはありません。利用者は自分のコピーで差し替えられます。
配布物のSHA-256一覧は取得時の照合用であり、起動時に改変DLLを拒否する仕組みではありません。

主な配置先:

- Qt: `_internal/PySide6/Qt6*.dll`
- PySide6: `_internal/PySide6/pyside6.abi3.dll` と各 `Qt*.pyd`
- shiboken6: `_internal/shiboken6/` 内のDLLとpyd
- FFmpeg: `_internal/PySide6/avcodec-61.dll`、`avformat-61.dll`、`avutil-59.dll`、
  `swresample-5.dll`、`swscale-8.dll`

1. 対象版に対応するソースを `third-party-sources/` から取り出します。
2. メーカーのビルド定義に従い、Windows x64・同じABI向けの共有ライブラリをビルドします。
3. アプリを終了し、作業用コピーの対応DLLを差し替えます。
4. 必要に応じてPySide6/shiboken6も同じQtに対してビルドし、専用venvへインストールします。
5. そのvenvでアプリを再ビルドします。改変版wheelはハッシュが変わるため、通常版の
   `requirements-lock.txt` への一致は要求せず、自分の改変版として別途記録してください。

同じインターフェースのDLLを差し替えるだけなら、通常はアプリ自体の再ビルドは不要です。
改変版ライブラリを使ってアプリを作り直す場合、`build.ps1` の公式版向け環境チェックで
止まる場合があります。その場合は、改変版を導入した専用venvで次を直接実行できます。

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist --workpath work\pyinstaller public-release.spec
```

これは公式wheel版との完全一致を要求するチェックを通さない方法です。
作者の許可・署名・キーは不要です。再配布する場合は変更内容・対象版・対応ソースを更新してください。

Qt: ソース付属のCMake/configure定義を使います。必要なモジュールはqtbase、
qtdeclarative、qtmultimedia等で、Virtual Keyboard/PDF/WebEngineは不要です。
Qt MultimediaはFFmpeg avformat/avcodec/avutil/swresample/swscaleの共有ライブラリを使います。

PySide6/shiboken6: pyside-setup付属READMEとsetup.pyを参照してください。
Qtのqmake/qtpaths、CMake、Ninja、適切なMSVC Build Tools、libclang等の開発用ツールが必要です。
公式手順: https://doc.qt.io/qtforpython-6.7/building_from_source/index.html

FFmpeg: SOURCE_PROVISION.mdの設定を基準にMSVC共有ライブラリとしてビルドします。
同じメジャーABIのDLL群をまとめて `_internal/PySide6/` の対応DLLと差し替えます。
Qt6Multimedia/FFmpeg pluginとの互換性が必要です。GPLオプションを有効化した改変版を
再配布する場合、その改変版のGPL条件を改めて確認してください。

**これら第三者ライブラリ自身のソースビルド手順は今回実行検証していません。**
その実証は品質・再現性向上の推奨事項で、一律のLGPL義務ではありません。
実際の版に対応するソースと必要なビルド定義等を提供し、利用者の差し替えを妨げないことは必要です。
Qtの公式wheelを利用したアプリのクリーンビルドと、配布DLLの差し替え確認とは区別します。
一切の改変版が無条件に動くことを保証するものではありません。

## 正式アイコンの再生成

`src/psd_mascot/assets/app-icon.png` が原本です。専用venvで `python tools/generate_icon.py` を実行すると、256/128/64/48/32/16px入りのICOとmanifestを再生成できます。ビルド定義はICOをexeリソースへ埋め込み、同じICOをアプリと通知領域へ設定します。ICO表示用のqicoプラグインはQt Baseの対象ソース・ライセンスに含まれます。
