#!/bin/bash
# Orchestrates the full memory-scaling study, sequentially, so nothing
# contends with anything else on Ollama. Safe to re-run: each step is
# skipped if its output file already exists, except the pool build itself
# (already resumable on its own terms).
#
# Order: wait for the already-running dataset-A k=4 job → finish the dataset-A
# sweep (k=0,1,2,8) → dataset-B held-out check (k=0,4) → build the 3000-row
# external pool → slice nested tiers → k=4 on each tier + one shared k=0.
#
# Progress: tail this script's own stdout, or DOCUMENTATION/experiments/
# memory_scaling/*.log per step. Results: DOCUMENTATION/ASSISTANT_AUDIT_SUMMARY.md
# once someone (me, next session) reads the *.md outputs here and writes the
# comparison — this script only produces the raw runs.
set -uo pipefail
cd "$(dirname "$0")/../../.."
EXP="DOCUMENTATION/experiments/memory_scaling"
PY=".venv/bin/python3"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*"; }

run_audit() {
    # run_audit <out_stem> <extra args...>
    local stem="$1"; shift
    local out="$EXP/$stem.md"
    if [ -f "$out" ]; then
        log "skip $stem (already exists)"
        return
    fi
    log "start $stem: $PY -m scripts.audit_assistant --out $out $*"
    $PY -m scripts.audit_assistant --out "$out" "$@" > "$EXP/$stem.log" 2>&1
    log "done  $stem (exit $?)"
}

log "waiting for the already-running dataset-A k=4 job to finish, if any"
while pgrep -f "run8-k4" > /dev/null 2>&1; do
    sleep 30
done
log "clear to proceed"

# --- dataset A: real history, full k-sweep ---------------------------------
run_audit "A_k0" --memory --memory-k 0
run_audit "A_k1" --memory --memory-k 1
run_audit "A_k2" --memory --memory-k 2
# k4 already produced run8-k4.md by the earlier interactive run; copy it in if present
if [ -f "/private/tmp/claude-501/-Users-USER-Desktop-Personal-Projects-MACalendar"/*/scratchpad/run8-k4.md ]; then
    cp /private/tmp/claude-501/-Users-USER-Desktop-Personal-Projects-MACalendar/*/scratchpad/run8-k4.md "$EXP/A_k4.md" 2>/dev/null || true
fi
run_audit "A_k4" --memory --memory-k 4
run_audit "A_k8" --memory --memory-k 8

# --- dataset B: held-out day + corrupted row removed ------------------------
if [ ! -f "$EXP/dataset_b_heldout.db" ]; then
    log "building dataset B (held-out day, corrupted row removed)"
    cp ~/.assistant_tools/nlu_memory.db "$EXP/dataset_b_heldout.db"
    sqlite3 "$EXP/dataset_b_heldout.db" <<SQL
DELETE FROM examples WHERE date(ts,'unixepoch') = (
    SELECT date(ts,'unixepoch') FROM examples GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1
);
DELETE FROM examples WHERE id = 46;
DELETE FROM example_records WHERE example_id NOT IN (SELECT id FROM examples);
SQL
fi
run_audit "B_k0" --memory --memory-k 0 --memory-source "$EXP/dataset_b_heldout.db"
run_audit "B_k4" --memory --memory-k 4 --memory-source "$EXP/dataset_b_heldout.db"

# --- dataset C: external pool, built once, sliced into nested tiers ---------
log "building the external pool (this is the long one)"
$PY -m scripts.build_memory_scaling_pool >> "$EXP/build.log" 2>&1
log "pool build finished (or already complete)"
$PY -m scripts.build_memory_scaling_pool --slice-tiers

run_audit "C_k0_shared" --memory --memory-k 0 --memory-source "$EXP/pool_3000.db"
for n in 60 300 1000 3000; do
    run_audit "C_${n}_k4" --memory --memory-k 4 --memory-source "$EXP/pool_${n}.db"
done

log "ALL DONE — raw run outputs are in $EXP/*.md"
