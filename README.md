# EventDenoiser

イベントカメラ（DVS/DAVIS系）の CSV イベントデータに対してノイズ除去を行うPythonツールです。

## 機能概要

1. **ホットピクセル除去** - 事前に収集したホットピクセル検出結果ファイル（複数回）を読み込み、全ファイルに共通して出現するピクセルを「ホットピクセル」として検出。対応するイベントをデータからドロップします。
2. **Background Activity Noise Filter** - `dv-processing` の `BackgroundActivityNoiseFilter` を適用。局所的な時空間活動に基づくノイズ除去。
3. **Fast Decay Noise Filter** - `dv-processing` の `FastDecayNoiseFilter` を適用。低解像度減衰マップによる高速ノイズ除去。

## ディレクトリ構成

```
EventDenoiser/
├── denoise.py              # メインノイズ除去スクリプト
├── build_hotpixel_map.py   # ホットピクセルマップ確認ユーティリティ
├── requirements.txt        # 依存パッケージ
├── README.md               # このファイル
├── input/                  # 入力CSVファイルをここに置く
├── output/                 # 処理後のCSVが出力される
└── hotpixel_maps/          # ホットピクセル検出結果ファイル (.txt) をここに置く
```

## セットアップ

### 前提条件

- Python 3.10 以上
- `dv-processing` Python バインディング（インストール方法は [公式ドキュメント](https://dv-processing.inivation.com/master/installation.html) 参照）

### 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

> **注意**: `dv-processing` は pip では直接インストールできない場合があります。  
> 公式の手順（apt, conda, または wheel）に従ってインストールしてください。

## データ形式

### 入力CSVフォーマット

`input/` ディレクトリに以下の形式のCSVファイルを配置してください。

| カラム名    | 型      | 説明                              |
|------------|---------|----------------------------------|
| timestamp  | int     | タイムスタンプ（マイクロ秒）        |
| x          | int     | ピクセルX座標                     |
| y          | int     | ピクセルY座標                     |
| polarity   | int/bool | 極性 (0=OFF, 1=ON)               |

例:
```csv
timestamp,x,y,polarity
1000000,100,200,1
1000010,101,200,0
1000020,102,201,1
```

### ホットピクセル検出ファイルフォーマット

`hotpixel_maps/` ディレクトリに Raspberry Pi で取得したホットピクセル検出結果ファイルを配置します。  
ファイル名例: `hp_20260525_181225.txt`

```
% active_pixels_count 659
% ...
% end
33 0
139 0
143 0
```

`% end` 行以降の各行は `x y` 形式のホットピクセル座標です。

## 使い方

### 基本的な使い方

```bash
# input/ 内の全CSVを処理し、output/ に保存
python denoise.py

# ファイルを直接指定
python denoise.py --input input/events.csv

# 解像度を明示的に指定 (推奨)
python denoise.py --resolution 640x480
```

### フィルタの選択

```bash
# BackgroundActivityNoiseFilter のみ
python denoise.py --filter ba

# FastDecayNoiseFilter のみ
python denoise.py --filter fd

# 両方 (デフォルト)
python denoise.py --filter both

# フィルタなし (ホットピクセル除去のみ)
python denoise.py --filter none
```

### フィルタパラメータの調整

```bash
python denoise.py \
  --resolution 640x480 \
  --filter both \
  --ba-duration-ms 2 \
  --fd-half-life-ms 10 \
  --fd-subdivision 4 \
  --fd-noise-threshold 1.0
```

### ホットピクセルマップの確認

```bash
# 全ファイルに共通するホットピクセルを表示
python build_hotpixel_map.py

# 8ファイル以上に出現するものをホットピクセルとみなす
python build_hotpixel_map.py --min-count 8
```

## コマンドラインオプション

### `denoise.py`

| オプション             | デフォルト       | 説明                                                    |
|----------------------|-----------------|--------------------------------------------------------|
| `--input`, `-i`      | `input/`        | 入力CSVファイルまたはディレクトリ                         |
| `--output`, `-o`     | `output/`       | 出力ディレクトリ                                          |
| `--hotpixel-dir`     | `hotpixel_maps/`| ホットピクセルファイルのディレクトリ                       |
| `--resolution`       | 自動推定         | カメラ解像度 (例: `640x480`)                             |
| `--filter`           | `both`          | ノイズフィルタ種別: `ba`, `fd`, `both`, `none`           |
| `--ba-duration-ms`   | `1`             | BackgroundActivityFilter の活性期間 [ms]                |
| `--fd-half-life-ms`  | `10`            | FastDecayFilter の半減期 [ms]                           |
| `--fd-subdivision`   | `4`             | FastDecayFilter の解像度サブdivision係数                 |
| `--fd-noise-threshold`| `1.0`          | FastDecayFilter のノイズ閾値                             |

## Raspberry Pi での使用

本リポジトリはメインPCでの解析用ですが、Raspberry Pi でクローンして以下の操作を行えます。

### ホットピクセル検出

ラズパイ上でカメラを接続し、ホットピクセル検出コマンドを実行してください（`dv-runtime` 等）。  
検出結果ファイルを `hotpixel_maps/` にコピーして使用します。

推奨: 10回検出を実施し、全10ファイルに共通するピクセルをホットピクセルとして扱います。

### 撮影データの転送

Raspberry Pi で録画したイベントデータ（CSV形式）を `input/` に配置し、  
メインPCで `python denoise.py` を実行してください。

## ノイズフィルタの詳細

### BackgroundActivityNoiseFilter

- **動作原理**: 各イベントについて、空間的な近傍ピクセルで直近 `duration_ms` ms 以内に別のイベントが存在するか確認。存在する場合はノイズではなく信号とみなす。
- **参考**: [dv-processing ドキュメント](https://dv-processing.inivation.com/master/event_filtering.html#background-activity-noise-filter)

### FastDecayNoiseFilter

- **動作原理**: 低解像度の指数減衰マップで局所活動を追跡。BackgroundActivityNoiseFilter より低メモリ・高速。
- **参考**: [dv-processing ドキュメント](https://dv-processing.inivation.com/master/event_filtering.html#fast-decay-noise-filter)

## ライセンス

MIT License
