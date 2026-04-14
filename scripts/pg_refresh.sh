#!/usr/bin/env bash
set -euo pipefail
source "$(git rev-parse --show-toplevel)/.env"

# psql command wrapper
PSQL=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q)

# -----------------------------
# Helpers
# -----------------------------
require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $1" >&2
    exit 1
  }
}

require_file() {
  local f="$1"
  [[ -f "$f" ]] || { echo "ERROR: file not found: $f" >&2; exit 1; }
  [[ -r "$f" ]] || { echo "ERROR: file not readable: $f" >&2; exit 1; }
}

# Build a quoted column list from the first line of a pipe-delimited CSV.
# Example header: Date|Time|Symbol -> "Date","Time","Symbol"
csv_header_to_cols() {
  local f="$1"
  local header
  header="$(head -n 1 "$f" | tr -d '\r')"
  if [[ -z "$header" ]]; then
    echo "ERROR: empty header in $f" >&2
    exit 1
  fi

  # Split by '|' into lines, trim spaces, then wrap each col in double quotes.
  # Note: assumes headers do not contain literal '|' characters.
  echo "$header" \
    | awk -v FS='|' '{
        for (i=1; i<=NF; i++) {
          gsub(/^[ \t]+|[ \t]+$/, "", $i);
          if ($i == "") continue;
          # Escape any embedded double quotes in header names
          gsub(/"/, "\"\"", $i);
          cols[++n] = "\"" $i "\""
        }
      }
      END {
        for (i=1; i<=n; i++) {
          printf "%s%s", cols[i], (i<n ? "," : "")
        }
      }'
}

# Refresh a single table from a CSV (truncate + copy)
refresh_table() {
  local table="$1"   # e.g. sweeps
  local file="$2"

  require_file "$file"

  local fqtn="${DB_SCHEMA}.${table}"
  local cols
  cols="$(csv_header_to_cols "$file")"

  echo "----"
  echo "Refreshing ${fqtn} from ${file}"
  echo "Detected columns: ${cols}"

  # TRUNCATE first for true refresh
  "${PSQL[@]}" -c "TRUNCATE TABLE ${fqtn};"

  # Use \copy with explicit column list to avoid column order issues
  # We pass \copy through psql -c; newlines are fine.
  "${PSQL[@]}" -c "\
\\copy ${fqtn}(${cols}) \
FROM '${file}' \
WITH (FORMAT csv, HEADER true, DELIMITER '|')"

  # Basic count
  local count
  count="$("${PSQL[@]}" -t -c "SELECT COUNT(*) FROM ${fqtn};" | tr -d '[:space:]')"
  echo "Loaded rows into ${fqtn}: ${count}"
}

# -----------------------------
# Main
# -----------------------------
require_cmd psql
require_cmd head
require_cmd awk
require_cmd tr

refresh_table "golden_sweeps"  "$GOLDEN_CSV"
refresh_table "sweeps"         "$SWEEPS_CSV"
refresh_table "trady_flow"     "$TRADY_CSV"
refresh_table "sexy_flow"      "$SEXY_CSV"
refresh_table "walter"         "$WALTER_CSV"
refresh_table "walter_openai"  "$WALTER_OPENAI_CSV"

echo "----"
echo "All CSV refreshes completed successfully."

# ── Post-refresh: Sector flow persistence ──
echo "----"
echo "Persisting sector flow history..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
conda run -n tradingbot python3 "${SCRIPT_DIR}/persist_sector_flow.py" || {
  echo "WARN: persist_sector_flow.py failed (non-fatal)"
}

# ── Post-refresh: Generate alerts ──
echo "----"
echo "Generating stock alerts..."
conda run -n tradingbot python3 "${SCRIPT_DIR}/generate_alerts.py" || {
  echo "WARN: generate_alerts.py failed (non-fatal)"
}

echo "----"
echo "All refreshes and post-processing completed successfully."
