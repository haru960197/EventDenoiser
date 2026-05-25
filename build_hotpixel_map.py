#!/usr/bin/env python3
"""
build_hotpixel_map.py - ホットピクセルマップの構築と検証ユーティリティ

hotpixel_maps/ ディレクトリ内の全 .txt ファイルを読み込み、
全ファイルに共通して出現するピクセル（ホットピクセル）を特定して表示します。

使用例:
    python build_hotpixel_map.py
    python build_hotpixel_map.py --hotpixel-dir /path/to/dir
    python build_hotpixel_map.py --min-count 8  # 10ファイル中8ファイル以上で出現
"""

import argparse
import logging
from pathlib import Path

from denoise import parse_hotpixel_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_pixel_frequency_map(
    hotpixel_dir: Path,
) -> tuple[dict[tuple[int, int], int], int]:
    """全ファイルでのピクセル出現回数マップと総ファイル数を返す。"""
    txt_files = sorted(hotpixel_dir.glob("*.txt"))
    if not txt_files:
        logger.warning(f"ファイルが見つかりません: {hotpixel_dir}")
        return {}, 0

    pixel_counts: dict[tuple[int, int], int] = {}
    for fp in txt_files:
        pixels = parse_hotpixel_file(fp)
        for px in pixels:
            pixel_counts[px] = pixel_counts.get(px, 0) + 1

    return pixel_counts, len(txt_files)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ホットピクセルマップの構築・統計表示",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--hotpixel-dir",
        type=Path,
        default=Path("hotpixel_maps"),
        help="ホットピクセル検出結果ファイルが入っているディレクトリ",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=None,
        help="ホットピクセルとみなす最小出現ファイル数 (デフォルト: 全ファイル数)",
    )
    args = parser.parse_args()

    pixel_counts, total_files = build_pixel_frequency_map(args.hotpixel_dir)

    if total_files == 0:
        return

    min_count = args.min_count if args.min_count is not None else total_files
    hotpixels = {px: cnt for px, cnt in pixel_counts.items() if cnt >= min_count}

    print(f"\n=== ホットピクセルマップ統計 ===")
    print(f"読み込んだファイル数        : {total_files}")
    print(f"ユニークピクセル総数        : {len(pixel_counts)}")
    print(f"ホットピクセル数 (閾値 {min_count}/{total_files}): {len(hotpixels)}")

    if hotpixels:
        print(f"\n--- ホットピクセル一覧 (x, y, 出現回数) ---")
        for (x, y), cnt in sorted(hotpixels.items(), key=lambda kv: -kv[1]):
            print(f"  ({x:4d}, {y:4d})  出現: {cnt}/{total_files}")

    # 出現頻度のヒストグラム
    from collections import Counter
    freq_hist = Counter(pixel_counts.values())
    print(f"\n--- 出現頻度ヒストグラム ---")
    for freq in sorted(freq_hist.keys(), reverse=True):
        bar = "█" * freq_hist[freq]
        print(f"  {freq:2d}/{total_files} ファイル: {freq_hist[freq]:4d} ピクセル  {bar}")


if __name__ == "__main__":
    main()
