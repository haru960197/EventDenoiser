#!/usr/bin/env bash
# ===========================================================================
# collect_data.sh – Prophesee ホットピクセル検出データ収集スクリプト（半自動）
#
# 概要:
#   metavision_active_pixel_detection コマンドを繰り返し起動し、
#   出力される active_pixel_calib.txt をタイムスタンプ付きでリネーム・保存する。
#   完全自動化は不可（GUI 上でスペースキー操作が必要）なため、
#   ユーザーが GUI 操作を完了してコマンドが終了するたびに、
#   次のループへ進む「半自動」方式を採用。
#
# 使用方法:
#   ./collect_data.sh                    # デフォルト: 連続駆動モード, 5回
#   ./collect_data.sh -n 30
#   ./collect_data.sh -n 30 -i 30# 30秒カウントダウン付き
#
# ===========================================================================
set -euo pipefail

# -------------------------------------------------------------------------
# デフォルト設定
# -------------------------------------------------------------------------
NUM_MEASUREMENTS=5           # 測定回数
INTERVAL_SEC=30               # 測定間カウントダウン秒数 (0 = 手動エンター待ち)
SOURCE_DIR="${HOME}/.local/share/metavision/hal"
SOURCE_FILE="active_pixel_calib.txt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# -------------------------------------------------------------------------
# ヘルプ表示
# -------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

ホットピクセル検出データの半自動収集スクリプト。

OPTIONS:
  -n NUM    測定回数 (default: ${NUM_MEASUREMENTS})
  -i SEC    測定間カウントダウン秒数, 0=手動 (default: ${INTERVAL_SEC})
  -s DIR    active_pixel_calib.txt の検索元ディレクトリ (default: ${SOURCE_DIR})
  -h        このヘルプを表示

EXAMPLES:
  $(basename "$0")                       # 5回, 30秒間隔
  $(basename "$0") -n 30                 # 30回
  $(basename "$0") -n 30 -i 0            # 手動エンター待ちモード
EOF
    exit 0
}

# -------------------------------------------------------------------------
# 引数パース
# -------------------------------------------------------------------------
while getopts "n:i:s:h" opt; do
    case "$opt" in
        n) NUM_MEASUREMENTS="$OPTARG" ;;
        i) INTERVAL_SEC="$OPTARG" ;;
        s) SOURCE_DIR="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# -------------------------------------------------------------------------
# 出力先ディレクトリの決定
# -------------------------------------------------------------------------
OUTPUT_DIR="${PROJECT_ROOT}/hotpixel_maps"  # デフォルトの出力ディレクトリ

mkdir -p "$OUTPUT_DIR"

# -------------------------------------------------------------------------
# ユーティリティ関数
# -------------------------------------------------------------------------
timestamp() {
    date +"%Y%m%d_%H%M%S"
}

beep_alert() {
    # ターミナルベルを鳴らす (サウンドが設定されていれば)
    printf '\a'
}

countdown() {
    local secs=$1
    while [ "$secs" -gt 0 ]; do
        printf "\r  ⏳ 次の測定まで %3d 秒... " "$secs"
        sleep 1
        secs=$((secs - 1))
    done
    printf "\r  ✅ カウントダウン完了!          \n"
    beep_alert
}

wait_for_result() {
    # active_pixel_calib.txt が存在するか確認 (最大60秒待機)
    local src="${SOURCE_DIR}/${SOURCE_FILE}"
    local waited=0
    while [ ! -f "$src" ] && [ "$waited" -lt 60 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    if [ ! -f "$src" ]; then
        echo "[WARNING] ${src} が見つかりませんでした (60秒タイムアウト)"
        return 1
    fi
    return 0
}

# -------------------------------------------------------------------------
# メインループ
# -------------------------------------------------------------------------
echo "=============================================="
echo " ホットピクセル検出データ収集スクリプト"
echo "=============================================="
echo ""
echo "  測定回数     : ${NUM_MEASUREMENTS}"
echo "  インターバル : ${INTERVAL_SEC} 秒"
echo "  ソースパス   : ${SOURCE_DIR}/${SOURCE_FILE}"
echo "  出力先       : ${OUTPUT_DIR}/"
echo ""
echo "----------------------------------------------"
echo " ※ 遮光環境を確認してください"
echo " ※ カメラが接続されていることを確認してください"
echo "----------------------------------------------"
echo ""
read -rp "準備ができたら Enter を押して開始 → "
echo ""

for i in $(seq 1 "$NUM_MEASUREMENTS"); do
    echo "━━━ 測定 ${i}/${NUM_MEASUREMENTS} ━━━"

    # --- 既存の active_pixel_calib.txt を削除 (前回の残留を防止) ---
    if [ -f "${SOURCE_DIR}/${SOURCE_FILE}" ]; then
        rm -f "${SOURCE_DIR}/${SOURCE_FILE}"
    fi

    # --- ホットピクセル検出コマンドの実行 ---
    echo "  🔬 metavision_active_pixel_detection を起動します..."
    echo "     → GUI上でスペースキーを押して検出を完了してください"
    echo ""

    # コマンド実行 (終了を待つ)
    # 実際のコマンド: metavision_active_pixel_detection
    # テスト時は下記をダミーに置き換え可能
    if command -v metavision_active_pixel_detection &>/dev/null; then
        metavision_active_pixel_detection || {
            echo "[WARNING] 検出コマンドが異常終了しました (exit code: $?)"
        }
    else
        echo "  ⚠️  metavision_active_pixel_detection が見つかりません"
        echo "     ダミーモード: Enter を押すと次に進みます"
        read -rp "  → "
    fi

    # --- result.txt を収集 ---
    if wait_for_result; then
        ts=$(timestamp)
        dest_name="hp_${ts}.txt"
        dest="${OUTPUT_DIR}/${dest_name}"

        cp "${SOURCE_DIR}/${SOURCE_FILE}" "$dest"
        echo "  📁 保存完了: ${dest_name}"

        # ソースをクリーンアップ
        rm -f "${SOURCE_DIR}/${SOURCE_FILE}"
    else
        echo "  ❌ active_pixel_calib.txt の取得に失敗しました。この測定をスキップします。"
    fi

    echo ""

    # --- インターバル (最終回以外) ---
    if [ "$i" -lt "$NUM_MEASUREMENTS" ]; then
        if [ "$INTERVAL_SEC" -gt 0 ]; then
            countdown "$INTERVAL_SEC"
        else
            read -rp "  次の測定に進むには Enter を押してください → "
        fi
    fi
done

echo ""
echo "=============================================="
echo " 全 ${NUM_MEASUREMENTS} 回の測定が完了しました"
echo " データ保存先: ${OUTPUT_DIR}/"
echo "=============================================="
echo ""
