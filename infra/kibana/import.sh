#!/usr/bin/env bash
# Import Job Hunter saved objects (index pattern + saved searches) into Kibana.
#
# Run this once after `docker compose up`:
#   bash infra/kibana/import.sh
#
# Prerequisites: Kibana must be healthy at http://localhost:5601
# Re-running is safe — objects are upserted (overwriteMode=createOrOverwrite).

set -euo pipefail

KIBANA_URL="${KIBANA_URL:-http://localhost:5601}"
NDJSON="$(dirname "$0")/saved_objects.ndjson"

echo "Waiting for Kibana to be ready..."
for i in $(seq 1 30); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${KIBANA_URL}/api/status")
  if [ "$STATUS" = "200" ]; then
    echo "  Kibana is up."
    break
  fi
  echo "  Attempt $i/30 — HTTP $STATUS, retrying in 5s..."
  sleep 5
done

echo "Importing saved objects from ${NDJSON}..."
curl -s -X POST \
  "${KIBANA_URL}/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@${NDJSON}" \
  | python3 -m json.tool

echo ""
echo "Done. Open Kibana → Discover → use the [Job Hunter] saved searches."
echo "Tip: Stack Management → Data Views → verify 'jobhunter-*' has @timestamp as time field."
