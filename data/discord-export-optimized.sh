#!/usr/bin/env bash
set -euo pipefail
source "$(git rev-parse --show-toplevel)/.env"

# Configuration

DISCORD_TOKEN="$DISCORD_TOKEN"
BASE_OUTPUT_DIR="$BASE_OUTPUT_DIR"
MERGED_OUTPUT_DIR="$MERGED_OUTPUT_DIR"
EXPORTER_PATH="$EXPORTER_PATH"
LOG_DIR="$BASE_OUTPUT_DIR/logs"
STATE_DIR="$BASE_OUTPUT_DIR/state"

mkdir -p "$LOG_DIR" "$STATE_DIR"

# Log file with timestamp
LOG_FILE="$LOG_DIR/export_$(date +%Y%m%d_%H%M%S).log"

# Function to log messages
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    log "❌ Missing required command: $1"
    exit 1
  }
}

require_cmd jq
require_cmd date

# Extract messages array from exporter JSON (supports either top-level array or {messages:[...]})
jq_messages_filter='
  if type=="array" then .
  elif type=="object" and (.messages? | type=="array") then .messages
  else [] end
'

# Export a channel with checkpointing + dedupe
export_channel() {
  local channel_id="$1"
  local channel_name="$2"

  local output_dir="$BASE_OUTPUT_DIR/$channel_name"
  mkdir -p "$output_dir"

  local state_file="$STATE_DIR/channel_${channel_id}.state"
  local merged_file="$MERGED_OUTPUT_DIR/${channel_name}_latest.json"

  # Initialize watermark on first run: pull last 7 days (adjust as you like)
  local last_ts
  if [[ -f "$state_file" ]]; then
    last_ts="$(cat "$state_file")"
  else
    last_ts="$(date -u -d "1 days ago" +"%Y-%m-%dT%H:%M:%SZ")"
  fi

  # Add a small overlap to avoid missing messages with same timestamp resolution
  local after_ts
  after_ts="$(date -u -d "${last_ts} - 30 seconds" +"%Y-%m-%dT%H:%M:%SZ")"

  local output_file="$output_dir/${channel_name}_$(date +%Y%m%d_%H%M%S).json"
  local tmp_out="${output_file}.tmp"

  log "Starting export for channel: $channel_name (ID: $channel_id)"
  log "Output directory: $output_dir"
  log "Checkpoint (last_ts): $last_ts"
  log "Fetching messages after (with overlap): $after_ts"

  # Run export to a temp file
  if "$EXPORTER_PATH" export \
      --token "$DISCORD_TOKEN" \
      --channel "$channel_id" \
      --after "$after_ts" \
      --format Json \
      --output "$tmp_out" >> "$LOG_FILE" 2>&1; then

    # Normalize tmp_out to messages array for merging/deduping
    # (We keep the raw temp output too by moving it to output_file at end.)
    local new_max_ts
    new_max_ts="$(
      jq -r "
        ($jq_messages_filter)
        | map(select(.timestamp? != null and .id? != null))
        | .[].timestamp
      " "$tmp_out" 2>/dev/null | sort | tail -n 1
    )"

    # Merge into per-channel "latest" and de-dupe by .id
    if [[ -f "$merged_file" ]]; then
      jq -s "
        def msgs(x): (x | $jq_messages_filter);
        (msgs(.[0]) + msgs(.[1]))
        | map(select(.id? != null))
        | unique_by(.id)
        | sort_by(.timestamp // \"\")
      " "$merged_file" "$tmp_out" > "${merged_file}.new"
      mv "${merged_file}.new" "$merged_file"
    else
      # First merge file becomes normalized messages array
      jq "
        ($jq_messages_filter)
        | map(select(.id? != null))
        | unique_by(.id)
        | sort_by(.timestamp // \"\")
      " "$tmp_out" > "$merged_file"
    fi

    # Update checkpoint based on merged file (most robust)
    local merged_max_ts
    merged_max_ts="$(
      jq -r '
        map(select(.timestamp? != null))
        | .[].timestamp
      ' "$merged_file" 2>/dev/null | sort | tail -n 1
    )"

    if [[ -n "${merged_max_ts:-}" && "${merged_max_ts}" != "null" ]]; then
      echo "$merged_max_ts" > "$state_file"
      log "Updated checkpoint to: $merged_max_ts"
    elif [[ -n "${new_max_ts:-}" && "${new_max_ts}" != "null" ]]; then
      # Fallback: update from this run only
      echo "$new_max_ts" > "$state_file"
      log "Updated checkpoint (fallback) to: $new_max_ts"
    else
      log "No messages found in export; checkpoint unchanged."
    fi

    # Keep a timestamped raw export file for auditing
    mv "$tmp_out" "$output_file"

    log "✅ Successfully exported $channel_name"
    log "   Raw export: $output_file"
    log "   Deduped merged: $merged_file"
    return 0
  else
    log "❌ Failed to export $channel_name"
    rm -f "$tmp_out" || true
    return 1
  fi
}

# Start export process
log "=========================================="
log "Starting Discord Export (checkpointed)"
log "=========================================="

# Channel configuration: channel_id|channel_name
declare -a CHANNELS=(
    "$SEXY"
    "$TRADY"
    "$GOLDEN"
    "$SWEEPS"
    "$BKOUT"
    "$BULLSEYE"
    "$AI_SCALP"
    "$CALLOUT"
    "$WALTER"
)


success_count=0
fail_count=0

for channel_config in "${CHANNELS[@]}"; do
  IFS='|' read -r channel_id channel_name <<< "$channel_config"

  if export_channel "$channel_id" "$channel_name"; then
    success_count=$((success_count + 1))
  else
    fail_count=$((fail_count + 1))
  fi

  sleep 2
done

log "=========================================="
log "Export Summary"
log "Successful: $success_count"
log "Failed: $fail_count"
log "=========================================="

# Cleanup old logs (keep last 30 days)
find "$LOG_DIR" -name "export_*.log" -mtime +30 -delete

# Optional: Send notification
#if command -v notify-send &> /dev/null; then
#  notify-send "Discord Export Complete" "Success: $success_count, Failed: $fail_count"
#fi

exit 0
