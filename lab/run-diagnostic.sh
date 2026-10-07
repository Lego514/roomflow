#!/usr/bin/env bash
# Supplementary timing diagnosis; preserves the original full-factorial batch.
set -euo pipefail
diag_output="${1:-results/linux/diagnostic}"
if [[ -e "$diag_output" ]]; then
  echo "Refusing to replace existing diagnostic results: $diag_output" >&2
  exit 1
fi
mkdir -p "$diag_output"
snapshot() {
  date -u
  uname -a
  for item in /proc/stat /proc/uptime /proc/softirqs /proc/net/softnet_stat /proc/interrupts; do
    printf '\n%s\n' "$item"
    cat "$item"
  done
}
snapshot > "$diag_output/environment-before.txt"
python3 lab/timing_probe.py > "$diag_output/timing-before.json"
for trial in idle-start r1-fifo r1-sqm r1-meeting r2-sqm r2-meeting r2-fifo r3-meeting r3-fifo r3-sqm idle-end; do
  case "$trial" in
    idle-*) diag_mode=sqm; diag_scenario=idle; diag_duration=10 ;;
    *) diag_mode="${trial#*-}"; diag_scenario=both; diag_duration=15 ;;
  esac
  python3 lab/netlab.py run --mode "$diag_mode" --scenario "$diag_scenario" \
    --duration "$diag_duration" --warmup 3 --output "$diag_output/$trial" \
    > "$diag_output/$trial.log" 2>&1
  printf 'Measured diagnostic: %s\n' "$trial"
done
python3 lab/timing_probe.py > "$diag_output/timing-after.json"
snapshot > "$diag_output/environment-after.txt"
