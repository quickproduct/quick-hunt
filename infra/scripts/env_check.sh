#!/usr/bin/env bash
# Validate that all required environment variables are set in infra/.env
# Usage: bash infra/scripts/env_check.sh

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
ENV_FILE="$INFRA_DIR/.env"

OK="[OK]"
MISSING="[MISSING]"
EMPTY="[EMPTY]"

REQUIRED_VARS=(
    # API / Core
    ADMIN_API_KEY
    SECRET_KEY

    # Database
    DATABASE_URL

    # Redis & Celery
    REDIS_URL
    CELERY_BROKER_URL
    CELERY_RESULT_BACKEND

    # RabbitMQ
    RABBITMQ_URL

    # LLM providers
    GROQ_API_KEY

    # Email outreach
    RESEND_API_KEY
    RESEND_FROM_EMAIL
    BREVO_WEBHOOK_SECRET
)

echo "=== Environment Check — $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "Source: $ENV_FILE"
echo ""

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Copy infra/.env.example and fill in values."
    exit 1
fi

# Load env file into current shell (temp file avoids process-substitution issues)
set +u
_TMPENV=$(mktemp)
grep -v '^#' "$ENV_FILE" | grep '=' | sed 's/^/export /' > "$_TMPENV"
# shellcheck disable=SC1090
source "$_TMPENV"
rm -f "$_TMPENV"
set -u

PASS=0
FAIL=0
for VAR in "${REQUIRED_VARS[@]}"; do
    VAL="${!VAR:-}"
    if [[ -z "${!VAR+x}" ]]; then
        echo "  $MISSING $VAR"
        FAIL=$((FAIL + 1))
    elif [[ -z "$VAL" ]]; then
        echo "  $EMPTY  $VAR (set but empty)"
        FAIL=$((FAIL + 1))
    else
        # Mask value — show first 4 chars only
        MASKED="${VAL:0:4}****"
        echo "  $OK $VAR = $MASKED"
        PASS=$((PASS + 1))
    fi
done

echo ""
echo "Result: $PASS OK, $FAIL issues"

if [[ $FAIL -gt 0 ]]; then
    echo "Fix missing variables in $ENV_FILE before starting the stack."
    exit 1
fi
