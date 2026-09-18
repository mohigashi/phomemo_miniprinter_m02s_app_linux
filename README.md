# Phomemo M02S GUI (Linux)

Phomemo M02S ミニ感熱プリンタを Bluetooth 経由で操作する Linux デスクトップ GUI。

## 機能
- **Bluetooth 接続**: M02S の MAC アドレスを入力して RFCOMM 接続（チャンネル 6）。接続時にファームウェアバージョンを表示。
- **プレビュー**: 用紙（幅 512 ドット）上に配置結果をリアルタイム表示。
- **拡大/縮小**: ズームスライダー（10%〜400%）。
- **移動**: 画像上を**ドラッグ**で印刷位置を移動。
- **回転**: ボタン（90°左/右、180°）または**マウスホイール**で回転。
- **印刷**: 合成した用紙画像を 1:1（512 ドット幅）で印刷。
- **リセット**: 変形をすべて初期化。

## セットアップ（初回のみ）
```bash
cd /home/mhigashi/phomemo-m02s-gui
./setup.sh
```

## 起動
```bash
cd /home/mhigashi/phomemo-m02s-gui
./run.sh
```

## 構成
- `phomemo_gui/app.py` — GUI アプリ本体（tkinter）。
- `phomemo_gui/config.ini` — 接続情報（MAC アドレス）を保存。
- `../phomemo_m02s/` — 下位ライブラリ（Bluetooth 通信・ESC/POS ラスタ送信）。

## Bluetooth 事前準備
1. M02S の電源を入れる。
2. （必要なら）ペアリング: `bluetoothctl` で M02S を探し `pair <MAC>` / `trust <MAC>`。
3. GUI の MAC 欄に M02S の MAC アドレスを入力して「接続」。

> 注: 接続・印刷は M02S 実機が必要。プリンタ未接続でもプレビュー/変形操作は動作します。
