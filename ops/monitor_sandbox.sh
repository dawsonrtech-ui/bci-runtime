#!/usr/bin/env bash
# PROJECT SYNAPSE: Cloud Sandbox Ingress & Performance Telemetry Monitor
# Tracks container logs, frame transaction volume, and CPU limits per tenant window.
#
# Usage:
#   ./monitor_sandbox.sh <buyer-project-name>
#   ./monitor_sandbox.sh meta-reality-labs
#
# Output:
#   stdout: real-time metrics every 60s
#   data/audit_log_<buyer>.csv: structured append log for negotiation leverage

set -euo pipefail

BUYER_ID="${1:?Usage: monitor_sandbox.sh <buyer-project-name>}"
LOG_INTERVAL=60

# Docker compose project name matches the -p flag used at spin-up
CONTAINER_NAME="synapse-${BUYER_ID}-bci-runtime-1"
AUDIT_LOG="data/audit_log_${BUYER_ID}.csv"

mkdir -p ops data data/finalized_audits

echo "================================================================"
echo "  TELEMETRY ACTIVE: MONITORING AUDIT WINDOW"
echo "  Container:  $CONTAINER_NAME"
echo "  Audit log:  $AUDIT_LOG"
echo "  Interval:   ${LOG_INTERVAL}s"
echo "================================================================"

# Write CSV header if file is new
[ -f "$AUDIT_LOG" ] || echo "timestamp,cpu_pct,mem_used_mb,mem_total_mb,active_nodes,frame_bursts_5m" > "$AUDIT_LOG"

while true; do
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # 1. Container alive?
    RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo "false")
    if [ "$RUNNING" != "true" ]; then
        echo "[$TIMESTAMP]  ALERT: Container OFFLINE"
        echo "$TIMESTAMP,OFFLINE,0,0,0,0" >> "$AUDIT_LOG"
        sleep "$LOG_INTERVAL"
        continue
    fi

    # 2. CPU + memory from docker stats (single snapshot, no stream)
    STATS=$(docker stats --no-stream --format "{{.CPUPerc}}\t{{.MemUsage}}" "$CONTAINER_NAME" 2>/dev/null || echo "0%\t0MB / 0MB")
    CPU_PCT=$(echo "$STATS" | cut -f1 | sed 's/%//')
    MEM_RAW=$(echo "$STATS" | cut -f2)
    MEM_USED=$(echo "$MEM_RAW" | awk '{print $1}' | sed 's/MiB//;s/GiB/*1024/' | bc 2>/dev/null || echo 0)
    MEM_TOTAL=$(echo "$MEM_RAW" | awk '{print $3}' | sed 's/MiB//;s/GiB/*1024/' | bc 2>/dev/null || echo 0)

    # 3. Frame bursts from daemon stdout (sigmas= pattern every 2500 frames)
    FRAMES=$(docker logs --since "${LOG_INTERVAL}s" "$CONTAINER_NAME" 2>&1 | grep -cP '^\s+\[\s*\d+\]' || true)

    # 4. Active TCP connections on the evaluation port (5556)
    ACTIVE=$(docker exec "$CONTAINER_NAME" ss -tn 2>/dev/null | grep -c ':5556' || echo 0)

    echo "[$TIMESTAMP]  CPU: ${CPU_PCT}%  MEM: ${MEM_USED}MB / ${MEM_TOTAL}MB  Nodes: ${ACTIVE}  Frames/5m: ${FRAMES}"
    echo "$TIMESTAMP,${CPU_PCT},${MEM_USED},${MEM_TOTAL},${ACTIVE},${FRAMES}" >> "$AUDIT_LOG"

    sleep "$LOG_INTERVAL"
done
