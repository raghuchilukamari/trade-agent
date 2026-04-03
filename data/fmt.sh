#!/bin/bash
# format_discord_data.sh - Format specific channel or all channels
source "$(git rev-parse --show-toplevel)/.env"
set -e

# Configuration
RAW_DIR="$RAW_DIR"
FORMATTED_DIR="$FORMATTED_DIR"
PYTHON_SCRIPTS_DIR="$PYTHON_SCRIPTS_DIR"
LOG_FILE="/media/SHARED/logs/format_$(date +%Y%m%d_%H%M%S).log"

# Channels and their corresponding Python scripts
declare -A CHANNEL_SCRIPTS=(
    ["walter"]="walter.py"
    ["trade-room"]="trade-room.py"
    ["golden-sweeps"]="golden-sweeps-uw.py"
    ["bullseye"]="bullseye.py"
    ["trady-flow"]="trady-flow.py"
    ["breakouts"]="breakouts.py"
    ["ai-scalpers"]="ai-scalpers.py"
    ["callouts"]="callouts.py"
    ["sexy-flow"]="sexy-flow.py"
    ["sweeps"]="sweeps.py"
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

format_channel() {
    local channel_name=$1
    local script_name="${CHANNEL_SCRIPTS[$channel_name]}"
    local script_path="$PYTHON_SCRIPTS_DIR/$script_name"

    log "Processing channel: $channel_name"
    log "  Using script: $script_name"

    # Check if script exists
    if [[ ! -f "$script_path" ]]; then
        log "  ❌ Script not found: $script_path"
        return 1
    fi

    # Check if raw data exists
    if [[ ! -d "$RAW_DIR/$channel_name" ]]; then
        log "  ⚠️  No raw data directory for $channel_name"
        return 1
    fi

    # Run channel-specific Python script
    if python3 "$script_path" \
        --channel "$channel_name" \
        --raw-dir "$RAW_DIR" \
        --output-dir "$FORMATTED_DIR" \
        >> "$LOG_FILE" 2>&1; then

        log "  ✅ Formatted: $channel_name"
        return 0
    else
        log "  ❌ Failed: $channel_name"
        return 1
    fi
}

# Create directories
mkdir -p "$FORMATTED_DIR" "$(dirname "$LOG_FILE")"

log "=========================================="
log "Discord Data Formatting - $(date)"
log "=========================================="

# Check if channel name provided as argument
if [[ -n "$1" ]]; then
    CHANNEL_NAME="$1"

    # Check if channel exists in configuration
    if [[ ! -v CHANNEL_SCRIPTS[$CHANNEL_NAME] ]]; then
        echo "❌ Error: Unknown channel '$CHANNEL_NAME'"
        echo ""
        echo "Available channels:"
        for channel in "${!CHANNEL_SCRIPTS[@]}"; do
            echo "  - $channel"
        done
        exit 1
    fi

    log "Formatting single channel: $CHANNEL_NAME"

    if format_channel "$CHANNEL_NAME"; then
        log "✅ Success"
        exit 0
    else
        log "❌ Failed"
        exit 1
    fi
else
    # No argument - process all channels
    log "Formatting all channels"

    success_count=0
    fail_count=0

    for channel_name in "${!CHANNEL_SCRIPTS[@]}"; do
        if format_channel "$channel_name"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done

    log ""
    log "=========================================="
    log "Formatting Complete"
    log "Success: $success_count"
    log "Failed: $fail_count"
    log "Output directory: $FORMATTED_DIR"
    log "Log file: $LOG_FILE"
    log "=========================================="
fi

# Show CSV file sizes
log ""
log "CSV Files:"
for csv_file in "$FORMATTED_DIR"/*.csv; do
    if [[ -f "$csv_file" ]]; then
        size=$(du -h "$csv_file" | cut -f1)
        lines=$(wc -l < "$csv_file")
        log "  $(basename "$csv_file"): $size, $lines lines"
    fi
done

exit 0