#!/usr/bin/env bash
# Round 110b: the Climate TRACE by-gas archives (carbon dioxide, methane,
# nitrous oxide; about 5.6 GB) moved to their own repository and Pages site,
# culprits-tiles-gases, because culprits-tiles-more went over the 10 GB GitHub
# Pages will publish. That repository's only file of its own is
# .github/workflows/build.yml, which clones this repository's scripts/, gases/
# and .github/ and runs this with a job name, from its own root:
#   seed           copy the archives already built here, once
#   ct_gases, ct_gases_ch4, ct_gases_n2o   build as before, then save
set -uo pipefail
job="$1"
MORE="$(cd "$(dirname "$0")/.." && pwd)"
export CT_GASES_HERE=1
case "$job" in
  seed) python3 "$MORE/gases/seed.py" ;;
  ct_gases|ct_gases_ch4|ct_gases_n2o)
    st=0
    timeout 160m python3 "$MORE/scripts/$job.py" || st=$?
    bash "$MORE/.github/save.sh" "Build, $job" || st=$?
    exit $st ;;
  *) echo "run.sh: no job named $job"; exit 1 ;;
esac
