# LGPL対応ソースの提供方法

## 採用する方法

Windows ZIPに、ライブラリのソース `third-party-sources/`、自作アプリのソース
`application-source/`、ライセンス文、ビルド情報、DLL差し替え方法を同梱する。
作者の返信に依存する「書面による提供の申し出」は使わない。

共有DLLは `_internal/` 以下に分離し、利用者が同じインターフェースの改変版へ
差し替えられる。LGPLv3第4条d1、LGPLv2.1第6条bの共有ライブラリ方式に沿う構成である。
ただしDLL自身の配布についても、対応ソース・表示の義務は残る。

ライセンス本文・著作権表示・必要なビルドスクリプトを保持することが必要であり、
「DLLを分けたからソース不要」「アプリがMITだから第三者条件も不要」とはならない。

## 配布先ごとの取得経路

| 配布先 | ファイル | 取得するもの |
|---|---|---|
| BOOTH | `Simple-PSD-Mascot-v1.0.1-windows.zip` | exe、ライブラリ、ライセンス、自作ソース、第三者ソースを同じZIPから取得 |
| GitHub Releases | `Simple-PSD-Mascot-v1.0.1-source.zip` と `Simple-PSD-Mascot-v1.0.1-third-party-sources.zip` | 前者が自作ソース/表示/手順、後者が第三者ソース実体。両方を同じReleaseに掲載 |

GitHub自作ソースZIPにDLLやexeは含めない。単体に第三者ソース実体がないことを明示し、
同じReleaseの対応ソースZIPを案内する。Windows ZIPはBOOTHだけで必要情報が揃うため、
GitHubへ移動しなければソースを入手できない構成ではない。

GitHubで自作ソースだけを配布する行為に、LGPLバイナリ配布と同じソース同梱義務が
発生するわけではない。GitHub向けの追加ソースZIPは入手しやすさのために用意する。
第三者ソースの取得元・SHA-256は自作ソースZIPの `third-party-source-manifest.json` にも収録する。

ソースに追加料金、秘密のパスワード、作者への請求を要求しない。
Windows ZIPにソースを同梱したまま配布を続ける。
別サーバーでソースを提供する方法もあるが、将来の管理を減らすため今回は使わない。

## 同梱対象と対応根拠

`third-party-sources/manifest.json` は取得元・版を含むファイル名・SHA-256・サイズの一覧。
未改変アーカイブには、メーカーのCMake/configure/setup.py等のビルド定義を含む。

- Qt 6.7.3: qtbase、qtdeclarative、qtmultimedia、qtshadertools等。
- PySide6/shiboken6 6.7.3: pyside-setup-everywhere-src。
- FFmpeg 7.0.2: 公式リリースと、Qtのattributionが指定するn7.0.2タグ。
- CPython 3.12.0、Pillow、NumPy、attrs、ビルドツール等の取得できたソースも同梱。
- psd-tools 1.26.0のsdistは今回PyPIで見つからず、依存ライブラリのソース実体は未収録。
  MITにはその同梱義務はなく、MIT本文と著作権表示は収録済み。

Qt/PySide6/FFmpegの対象DLLは公式wheelと照合済み。独自パッチは加えていない。
Microsoftランタイム省略のための参照名修正は、別のNumPy/psd-tools拡張3ファイルだけで、
`THIRD_PARTY_MODIFICATIONS.json` に記録する。

FFmpeg DLL内で確認した設定:

```text
--prefix=installed --disable-programs --disable-doc --disable-debug --enable-network
--disable-lzma --enable-pic --disable-vulkan --disable-v4l2-m2m
--disable-decoder=truemotion1 --toolchain=msvc --enable-shared --disable-static
```

DLL表示はLGPL 2.1以降で、設定にGPL機能の有効化は確認されていない。
Qt付属attributionもn7.0.2のソース取得元を指定している。

## 再ビルド義務と検証の区別

実際の版に対応するソース、必要な変更、インターフェース定義、ビルド/インストール用の
スクリプト等を提供することは必要である。一般的なコンパイラやOSの開発ツール自体を
すべて同梱するという意味ではない。

**配布者がQt/PySide6/FFmpegを全て実際に再ビルドすることは、一律のLGPL義務ではない。**
第三者ソース再ビルドは今回未実施で、ビルド手順の再現性を高める推奨検証として扱う。
「未実施だから直ちに違反」とも「無関係なソースと説明だけで十分」とも判断しない。

開発終了後もバグ修正や利用サポートを継続する義務はこの方式からは生じない。
配布中のソース提供、著作権表示、改変/再配布に関する権利等の条件は守る。

## 条文

- LGPLv3第4条: https://www.gnu.org/licenses/lgpl-3.0.html
- GPLv3第1条・第6条d: https://www.gnu.org/licenses/gpl-3.0.html
- LGPLv2.1第0条・第4条・第6条: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
- 本文コピーは `licenses/LGPL-3.0.txt`、`GPL-3.0.txt`、`LGPL-2.1.txt`。
