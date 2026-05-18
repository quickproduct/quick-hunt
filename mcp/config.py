import os
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
COMPOSE_FILE = PROJECT_ROOT / "infra" / "docker-compose.yml"
LOG_DIR = PROJECT_ROOT / "backend" / "logs"

API_URL = os.getenv("JH_API_URL", "http://localhost:8001")
API_KEY = os.getenv("JH_ADMIN_API_KEY", "")

REDIS_URL = os.getenv("JH_REDIS_URL", "redis://localhost:6379/0")

RABBITMQ_BASE = os.getenv("JH_RABBITMQ_URL", "http://localhost:15672")
RABBITMQ_USER = os.getenv("JH_RABBITMQ_USER", "jobhunter")
RABBITMQ_PASS = os.getenv("JH_RABBITMQ_PASS", "jobhunter")

ALLOWED_DOCKER_SERVICES = {
    "api", "beat",
    "worker-scraping-bulk", "worker-scraping-realtime", "worker-enrichment",
    "worker-maintenance", "worker-cover-bulk", "worker-cover-ranking",
    "worker-cover-generation", "worker-cover-workflow", "worker-email",
    "worker-cover-batch", "dashboard", "redis", "rabbitmq", "postgres", "ollama",
}

# --- Kubernetes / KEDA ---
K8S_NAMESPACE = os.getenv("JH_K8S_NAMESPACE", "job-hunter")

# Workers with KEDA ScaledObjects — cover-batch and beat are intentionally excluded
# (fixed replicas; two instances of either would break correctness)
KEDA_SCALABLE_WORKERS = {
    "worker-scraping-bulk", "worker-scraping-realtime", "worker-enrichment",
    "worker-maintenance", "worker-cover-bulk", "worker-cover-ranking",
    "worker-cover-generation", "worker-cover-workflow", "worker-email",
}

ALLOWED_K8S_DEPLOYMENTS = KEDA_SCALABLE_WORKERS | {
    "api", "dashboard", "beat", "worker-cover-batch", "ollama",
}

# Port-forward map: name → (k8s_target, local_port, remote_port, description)
# Ports chosen to avoid host conflicts: 15672(k3d-lb), 5432(local-pg), 6379(local-redis)
K8S_PORT_FORWARDS: dict[str, tuple[str, int, int, str]] = {
    "api":       ("svc/api",       8002,  8000,  "http://localhost:8002"),
    "dashboard": ("svc/dashboard", 3001,  3000,  "http://localhost:3001"),
    "rabbitmq":  ("svc/rabbitmq",  15673, 15672, "http://localhost:15673 (admin/jobhunter)"),
    "postgres":  ("svc/postgres",  5433,  5432,  "localhost:5433 (user=jobhunter db=jobhunter)"),
    "redis":     ("svc/redis",     6380,  6379,  "localhost:6380"),
    "ollama":    ("svc/ollama",    11435, 11434, "http://localhost:11435"),
}

HTTP_TIMEOUT_QUICK = int(os.getenv("JH_HTTP_TIMEOUT_QUICK", "5"))
HTTP_TIMEOUT_NORMAL = int(os.getenv("JH_HTTP_TIMEOUT_NORMAL", "15"))
HTTP_TIMEOUT_LONG = int(os.getenv("JH_HTTP_TIMEOUT_LONG", "30"))

HTTP_MAX_RETRIES = int(os.getenv("JH_HTTP_MAX_RETRIES", "3"))
HTTP_RETRY_BACKOFF = float(os.getenv("JH_HTTP_RETRY_BACKOFF", "0.5"))

CACHE_TTL_DEFAULT = int(os.getenv("JH_CACHE_TTL_DEFAULT", "15"))
CACHE_TTL_HEALTH = int(os.getenv("JH_CACHE_TTL_HEALTH", "30"))
CACHE_TTL_STATS = int(os.getenv("JH_CACHE_TTL_STATS", "60"))
CACHE_MAX_ENTRIES = int(os.getenv("JH_CACHE_MAX_ENTRIES", "200"))

LOG_LEVEL = os.getenv("JH_MCP_LOG_LEVEL", "WARNING").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mcp")
