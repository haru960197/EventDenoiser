#!/usr/bin/env python3
"""
EventDenoiser - イベントカメラデータのノイズ除去スクリプト

処理の流れ:
1. dv-processing の EventStore にイベントをプッシュ
2. BackgroundActivityNoiseFilter および FastDecayNoiseFilter でノイズ除去
3. 結果を output/ に保存
"""

import argparse
import logging
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import dv_processing as dv


# ─────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)




# ─────────────────────────────────────────
# CSV 読み込み
# ─────────────────────────────────────────

# CSV カラム定義（ヘッダー行なし、実際の列順）
_CSV_COLUMNS = ["x", "y", "polarity", "timestamp"]


def parse_csv_geometry(csv_path: Path) -> tuple[int, int] | None:
    """
    CSV ファイルの先頭にある `%geometry:W,H` 行を読み取り、
    解像度 (W, H) を返す。該当行がなければ None を返す。

    例: `%geometry:320,320`  →  (320, 320)
    """
    with open(csv_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if not line.startswith("%"):
                break  # データ行に達したら終了
            if line.startswith("%geometry:"):
                try:
                    _, wh = line.split(":")
                    w, h = wh.strip().split(",")
                    return (int(w), int(h))
                except ValueError:
                    logger.warning(f"geometry 行のパースに失敗: '{line}'")
    return None


def load_events_csv(csv_path: Path) -> pd.DataFrame:
    """
    CSV ファイルからイベントデータを読み込む。

    フォーマット:
    - 先頭に `%geometry:W,H` などの `%` で始まるメタデータ行が含まれる場合がある
    - ヘッダー行なし
    - 列順: x, y, polarity, timestamp
    - polarity は 0/1
    - timestamp は整数 (マイクロ秒)

    例:
        %geometry:320,320
        133,123,0,3406784
        180,58,1,3406785
    """
    # % で始まる行数を数えてスキップ行数を決定
    skip_rows = 0
    with open(csv_path, "r") as f:
        for line in f:
            if line.strip().startswith("%"):
                skip_rows += 1
            else:
                break

    df = pd.read_csv(
        csv_path,
        header=None,
        names=_CSV_COLUMNS,
        skiprows=skip_rows,
    )

    df["timestamp"] = df["timestamp"].astype(int)
    df["x"] = df["x"].astype(int)
    df["y"] = df["y"].astype(int)
    df["polarity"] = df["polarity"].astype(bool)

    # タイムスタンプの昇順ソート（念のため）
    df = df.sort_values("timestamp").reset_index(drop=True)
    logger.info(f"CSV 読み込み完了: {len(df)} イベント (メタデータ行スキップ数: {skip_rows})")
    return df




# ─────────────────────────────────────────
# dv-processing ノイズフィルタ
# ─────────────────────────────────────────

def build_event_store(df: pd.DataFrame) -> dv.EventStore:
    """
    DataFrame の各行を dv.EventStore にプッシュして返す。
    """
    store = dv.EventStore()
    for row in df.itertuples(index=False):
        store.push_back(int(row.timestamp), int(row.x), int(row.y), bool(row.polarity))
    logger.info(f"EventStore 構築完了: {len(store)} イベント")
    return store


def apply_background_activity_filter(
    store: dv.EventStore,
    resolution: tuple[int, int],
    duration_ms: int = 1,
) -> dv.EventStore:
    """
    BackgroundActivityNoiseFilter を適用する。

    隣接ピクセルの直近 `duration_ms` ms 以内に別のイベントがあれば、
    そのイベントを「信号」とみなしてノイズと判定しない。
    """
    noise_filter = dv.noise.BackgroundActivityNoiseFilter(
        resolution,
        backgroundActivityDuration=timedelta(milliseconds=duration_ms),
    )
    noise_filter.accept(store)
    filtered = noise_filter.generateEvents()
    logger.info(
        f"BackgroundActivityNoiseFilter: {len(store)} → {len(filtered)} イベント "
        f"(削減率: {noise_filter.getReductionFactor():.4f})"
    )
    return filtered


def apply_fast_decay_filter(
    store: dv.EventStore,
    resolution: tuple[int, int],
    half_life_ms: int = 10,
    subdivision_factor: int = 4,
    noise_threshold: float = 1.0,
) -> dv.EventStore:
    """
    FastDecayNoiseFilter を適用する。

    低解像度の減衰マップを用いた高速ノイズフィルタ。
    メモリフットプリントが小さく、高速処理が可能。
    """
    noise_filter = dv.noise.FastDecayNoiseFilter(
        resolution,
        halfLife=timedelta(milliseconds=half_life_ms),
        subdivisionFactor=subdivision_factor,
        noiseThreshold=noise_threshold,
    )
    noise_filter.accept(store)
    filtered = noise_filter.generateEvents()
    logger.info(
        f"FastDecayNoiseFilter: {len(store)} → {len(filtered)} イベント "
        f"(削減率: {noise_filter.getReductionFactor():.4f})"
    )
    return filtered


# ─────────────────────────────────────────
# EventStore → DataFrame
# ─────────────────────────────────────────

def event_store_to_dataframe(store: dv.EventStore) -> pd.DataFrame:
    """dv.EventStore を pandas DataFrame に変換する (列順: x, y, polarity, timestamp)。"""
    rows = []
    for ev in store:
        rows.append({
            "x": ev.x(),
            "y": ev.y(),
            "polarity": int(ev.polarity()),
            "timestamp": ev.timestamp(),
        })
    return pd.DataFrame(rows, columns=_CSV_COLUMNS)


# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────

def detect_resolution(df: pd.DataFrame) -> tuple[int, int]:
    """DataFrame から解像度を推定する (width, height)。"""
    width = int(df["x"].max()) + 1
    height = int(df["y"].max()) + 1
    return (width, height)


def process_file(
    csv_path: Path,
    output_dir: Path,
    resolution: tuple[int, int] | None,
    filter_mode: str,
    ba_duration_ms: int,
    fd_half_life_ms: int,
    fd_subdivision: int,
    fd_noise_threshold: float,
) -> None:
    """1 つの CSV ファイルに対してノイズ除去処理を実行する。"""
    logger.info(f"=== 処理開始: {csv_path.name} ===")

    # 1. CSV 読み込み
    df = load_events_csv(csv_path)

    if df.empty:
        logger.warning("入力イベントがありません。スキップします。")
        return

    # 3. 解像度を決定
    #    優先順位: コマンドライン引数 > CSVの%geometry行 > データから自動推定
    if resolution:
        res = resolution
    else:
        res = parse_csv_geometry(csv_path) or detect_resolution(df)
    logger.info(f"使用する解像度: width={res[0]}, height={res[1]}")

    # 4. EventStore 構築
    store = build_event_store(df)

    # 5. dv-processing ノイズフィルタ
    if filter_mode in ("ba", "both"):
        store = apply_background_activity_filter(store, res, ba_duration_ms)
    if filter_mode in ("fd", "both"):
        store = apply_fast_decay_filter(store, res, fd_half_life_ms, fd_subdivision, fd_noise_threshold)

    # 6. 結果を DataFrame に変換して保存（入力と同じ列順: x, y, polarity, timestamp）
    df_out = event_store_to_dataframe(store)
    out_path = output_dir / csv_path.name
    df_out.to_csv(out_path, index=False)
    logger.info(f"保存完了: {out_path}  (残イベント数: {len(df_out)})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="イベントカメラデータのノイズ除去ツール",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("input"),
        help="入力 CSV ファイルまたはディレクトリのパス",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output"),
        help="出力ディレクトリのパス",
    )

    parser.add_argument(
        "--resolution",
        type=str,
        default=None,
        metavar="WxH",
        help="カメラ解像度 (例: 640x480)。省略時はデータから自動推定",
    )
    parser.add_argument(
        "--filter",
        choices=["ba", "fd", "both", "none"],
        default="both",
        dest="filter_mode",
        help="適用するノイズフィルタ: ba=BackgroundActivity, fd=FastDecay, both=両方, none=なし",
    )
    parser.add_argument(
        "--ba-duration-ms",
        type=int,
        default=1,
        help="BackgroundActivityNoiseFilter の活性期間 [ms]",
    )
    parser.add_argument(
        "--fd-half-life-ms",
        type=int,
        default=10,
        help="FastDecayNoiseFilter の半減期 [ms]",
    )
    parser.add_argument(
        "--fd-subdivision",
        type=int,
        default=4,
        help="FastDecayNoiseFilter の解像度サブdivision係数",
    )
    parser.add_argument(
        "--fd-noise-threshold",
        type=float,
        default=1.0,
        help="FastDecayNoiseFilter のノイズ閾値",
    )
    args = parser.parse_args()

    # 解像度のパース
    resolution: tuple[int, int] | None = None
    if args.resolution:
        try:
            w, h = args.resolution.lower().split("x")
            resolution = (int(w), int(h))
        except ValueError:
            logger.error("--resolution の形式が不正です。例: 640x480")
            sys.exit(1)

    # 出力ディレクトリの確認・作成
    args.output.mkdir(parents=True, exist_ok=True)



    # 入力ファイルの列挙
    input_path: Path = args.input
    if input_path.is_file():
        csv_files = [input_path]
    elif input_path.is_dir():
        csv_files = sorted(input_path.glob("*.csv"))
    else:
        logger.error(f"入力パスが存在しません: {input_path}")
        sys.exit(1)

    if not csv_files:
        logger.error(f"CSV ファイルが見つかりません: {input_path}")
        sys.exit(1)

    logger.info(f"処理対象 CSV ファイル数: {len(csv_files)}")

    # 各 CSV を処理
    for csv_path in csv_files:
        try:
            process_file(
                csv_path=csv_path,
                output_dir=args.output,

                resolution=resolution,
                filter_mode=args.filter_mode,
                ba_duration_ms=args.ba_duration_ms,
                fd_half_life_ms=args.fd_half_life_ms,
                fd_subdivision=args.fd_subdivision,
                fd_noise_threshold=args.fd_noise_threshold,
            )
        except Exception as e:
            logger.error(f"{csv_path.name} の処理中にエラーが発生しました: {e}")
            raise

    logger.info("=== 全ファイルの処理が完了しました ===")


if __name__ == "__main__":
    main()
