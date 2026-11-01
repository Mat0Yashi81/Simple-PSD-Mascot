# Simple PSD Mascot — Third-party software notices

本アプリの自作部分はMITです。第三者のライブラリ・ランタイム・そのソースに
MITを一律に適用するものではありません。各権利者の表示と条件を保持してください。

## Python packages

| 名前 | バージョン | ライセンス / 選択する条件 | 用途 |
|---|---|---|---|
| PySide6 / Essentials / Addons / shiboken6 | 6.7.3 | Qt/PySide本体の対象部分はLGPLv3。内蔵第三者部分は各条件 | GUI・音声 |
| psd-tools | 1.26.0 | MIT | PSD解析・合成 |
| Pillow | 13.0.0 | MIT-CMU＋付属第三者ライセンス | 画像処理 |
| NumPy | 2.5.4 | BSD-3-Clause＋0BSD/MIT/Zlib/CC0等＋付属バイナリの条件 | 合成計算 |
| attrs | 26.1.0 | MIT | 間接依存 |
| PyInstaller | 6.22.3 | GPL-2.0-or-later WITH Bootloader exception、実行時フック等Apache-2.0 | exe作成 |
| pyinstaller-hooks-contrib | 2026.9 | 通常フックGPL-2.0-or-later、実行時フックApache-2.0 | exe作成 |
| altgraph | 0.17.5 | MIT | ビルド |
| packaging | 26.3 | BSD-2-Clauseを選択（Apache-2.0との選択式） | ビルド |
| pefile | 2024.8.26 | MIT | ビルド・DLLインポート名の調整 |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause | ビルド |
| setuptools | 84.2.1 | MIT | ビルド |

正確な著作権表示・全文は `licenses/python-packages/` に収録しています。
`third-party-packages.json` は版とライセンスファイルの機械可読一覧です。
ビルド用の通常フックをアプリ本体として組み込んではいません。

## Native components

- CPython 3.12.0: Python Software Foundation License Version 2と付属条件。
  `licenses/Python-3.12.0-LICENSE.txt` を参照してください。
- Qt 6.7.3: Core, Gui, Widgets, Network, Multimedia, MultimediaWidgets,
  Qml, QmlModels, Quick, OpenGL、および残したWindows/FFmpegプラグイン。
  正式アイコンのICO表示に用いる `imageformats/qico.dll` はQt Base 6.7.3の対象ソース・LGPL条件に含まれます。
  本体の対象部分はLGPLv3を選択します。各第三者部分は別条件です。
- FFmpeg 7.0.2: 配布DLL自身の表示はLGPL-2.1-or-later。
  Qt 6.7.3の `src/3rdparty/ffmpeg/qt_attribution.json` が指定するn7.0.2ソースを収録。
  同ファイルにはBSD/ISC/MIT/MPL-2.0/IJG/Zlib/BSL等の第三者条件も記載されています。
  本ソフトウェアはLGPLv2.1以降のFFmpegを使用しています。
  対応するソースは同じ配布物の `third-party-sources/` から取得できます。
- OpenBLAS/LAPACK: NumPy同梱DLL、BSD系。GCC runtimeが含まれる部分は
  GPL-3.0-or-later WITH GCC-exception-3.1です。ライセンス全文と例外は
  `licenses/python-packages/numpy/` に含まれています。例外を削除しないでください。
- OpenSSL 3.0.11: Apache-2.0。CPython付属DLL。`licenses/OpenSSL-3.0.11-LICENSE.txt`。
- libffi 3.4.4: MIT。CPython 3.12.0の外部依存定義で版を確認。
  `licenses/libffi-3.4.4-LICENSE`。
- Windows / Microsoft Visual C++ runtime: OS・利用者が別途インストールする前提条件です。
  **Microsoft製ランタイムDLLは本配布物に含めません。** これらにMITを適用しません。

Portions of this software are copyright © 2024, 2026 The FreeType Project
(www.freetype.org). All rights reserved. FreeType部分はFTLを選択します。
This software is based in part on the work of the Independent JPEG Group.

Qtその他の第三者表示は `licenses/upstream-source-notices/` と
`third-party-qt-attributions.json` に原文のまま収録しています。
この収録は取りこぼしを避けるためソース全体を対象にしており、Linux用ヘッダ、
ビルドツール、テスト等の**Windows実行ファイルでは使用しない部分**も含みます。
GPLという語がその一覧にあるだけで、すべての項目が実行ファイルへリンクされるわけではありません。
GLSLコンパイラ生成物等にはBison例外、Linuxヘッダにはsyscall-note等の例外があります。

## Excluded components and modifications

Qt Virtual Keyboard、Qt PDFとPDF画像プラグイン、Qt WebEngine、Qt Charts/Graphs/
DataVisualization/Quick3D、未使用の画像・TLS・入力方式プラグインは同梱しません。
公式PySide6 Addons wheel全体を配布するものでもありません。

`THIRD_PARTY_MODIFICATIONS.json` に、同梱DLLの省略とバイナリの変更記録を記載します。
NumPyの2つのpyd、psd-toolsのRLE拡張のDLLインポート名を、専用名のMSVCPコピーから
利用者がインストールした標準名 `msvcp140.dll` へ変更しています。計算命令・圧縮処理・
画像形式は変更していません。再現用コードは `tools/normalize_msvc_imports.py` です。
Qt・PySide6・FFmpeg自体のバイナリは改変していません。

## LGPL rights and source

利用者はLGPL対象ライブラリを変更・差し替え、アプリと再結合し、実行できます。
この目的の改変のデバッグに必要なリバースエンジニアリングを妨げる条件は設けません。
この許可は、別途利用するWindows等の第三者ソフトウェアの条件を変更するものではありません。

ライセンス本文と著作権表示を削除しないでください。変更したライブラリを再配布する場合は、
その変更を含む対応ソースも必要です。手順は `BUILD.md` と `SOURCE_PROVISION.md` を参照してください。
商用利用・改造・再配布・再販売は、自作部分のMITと各第三者ライセンスの条件を守って行えます。
