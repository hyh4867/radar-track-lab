#!/bin/bash
# Wait while swap used > 3 GB or free memory < 10% (PREREGISTRATION_4 8), polling every 5 min.
while true; do
  SW=$(sysctl -n vm.swapusage | sed -E 's/.*used = ([0-9.]+)M.*/\1/')
  FR=$(memory_pressure -Q | sed -nE 's/.*free percentage: ([0-9]+)%.*/\1/p')
  if awk -v s="$SW" -v f="$FR" 'BEGIN{exit !(s<=3072 && f>=10)}'; then exit 0; fi
  echo "$(date '+%T') guard: swap ${SW}M free ${FR}% -> wait 5 min"; sleep 300
done
