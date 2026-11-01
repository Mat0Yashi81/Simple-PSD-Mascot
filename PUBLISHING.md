# GitHub / BOOTHで公開する手順

## 公開時の配置

| 場所 | 掲載するもの |
|---|---|
| GitHubリポジトリ | 自作ソース、説明書、LICENSE、licenses、第三者一覧。実行時データは登録しない |
| 同じGitHub Release | `Simple-PSD-Mascot-v1.0.0-source.zip` と `Simple-PSD-Mascot-v1.0.0-third-party-sources.zip` |
| BOOTH | `Simple-PSD-Mascot-v1.0.0-windows.zip` 全体 |

対応ソースZIPは大きいため、Gitの通常ファイルにせずReleaseの添付ファイルにします。
GitHub自動生成の「Source code (zip)」だけでは、添付した第三者ソースまでは含まれません。
GitHubで自作ソースのみ配る場合の追加ZIPは、一律のLGPL義務ではなく利便性のための運用です。
今回の案内文のまま使う場合は、その案内と一致するよう同じReleaseへ添付してください。

Windows ZIPはライセンス文・自作ソース・対応ソースを同梱済みです。
BOOTHだけで必要なソースを受け取れます。exeだけ、または `_internal/` だけを抜き出して
掲載しないでください。対応するバイナリの配布中にソースだけを削除しないでください。
ソース取得に追加料金や作者への請求を要求せず、ライセンス上の改変等の権利を妨げる
独自規約を追加しないでください。

## GitHubのREADME / Release説明の記載例

```text
Simple PSD Mascot v1.0.0 の自作コードはMITです。商用利用・改造・再配布・再販売を許可します。
著作権表示とライセンス文を保持してください。第三者部分は各ライセンスに従ってください。

自作ソースは、このReleaseの Simple-PSD-Mascot-v1.0.0-source.zip にあります。
Qt/PySide6 6.7.3・FFmpeg 7.0.2等の対応ソースは、同じReleaseの
Simple-PSD-Mascot-v1.0.0-third-party-sources.zip にあります。
BUILD.md、SOURCE_PROVISION.md、licenses/も参照してください。
Qt/PySide6はLGPLv3、FFmpegはLGPLv2.1以降の条件で使用しています。
```

## BOOTHの商品説明の記載例

```text
Simple PSD Mascot v1.0.0 は、ユーザーが用意したPSDを読み込むWindows x64用デスクトップマスコットです。
Pythonは不要です。Microsoft公式の最新Visual C++ x64ランタイムが必要です。
PSD・音声素材は含まれません。ZIP全体を展開してexeを起動してください。

自作部分はMITです。商用利用・改造・再配布・再販売を許可します。
著作権表示とライセンス文を保持してください。第三者部分は各ライセンスに従ってください。

Qt/PySide6（LGPLv3）、FFmpeg（LGPLv2.1以降）を使用しています。
ライセンス文はlicenses/、対応ソースはthird-party-sources/、
自作ソースはapplication-source/に同梱しています。DLLの変更・差し替えを妨げる制限はありません。

動作保証なし・サポート保証なし・更新未定です。
VCランタイム公式案内: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
```

GitHub/BOOTHのURLは、実際に公開先を作成してから相互に記載します。
架空のURLや、作者への問い合わせだけをソース取得方法として記載しないでください。

## 最小限の公開確認

1. GitHubの同じReleaseに2つのZIPがあることを確認します。
2. ログアウト状態または利用者の立場で取得できることを確認します。
3. BOOTHのZIPに `licenses/`、`application-source/`、`third-party-sources/` があることを確認します。
4. 商品説明のライセンス・ソース取得場所・VCランタイム案内を確認します。

これは「必要情報を実際に提供する」ための確認で、別VMでの品質検査とは区別します。
公開操作と公開後のダウンロード確認は今回行っていません。

全ライブラリの再コンパイル、別OSのVM検査、全バイナリの逆解析は、今回のLGPL方式で
一律に要求される公開前作業ではありません。品質や確信度を高める推奨事項です。
対応ソースに具体的な欠落が見つかった場合の修正は別です。

## v1.0.0のREADME

GitHub用ソースZIPはREADME.mdを保持します。BOOTH用Windows ZIPの案内はUTF-8 BOM付き・CRLF改行のREADME.txtです。同梱application-sourceでもREADME.mdを除きREADME.txtを保持します。第三者ライセンス文・対応ソースは変換しません。
