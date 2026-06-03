# Resource Optimization Plan — accept slower throughput, cut RAM + CPU

## Current state (measured)

**OrbStack host process** consumes:
- **CPU: 265%** of one core (~2.6 cores fully busy)
- **RAM: 3.9 GB** (24% of host memory)

**k3d node** (the VM OrbStack runs):
- Capacity: 8 Gi RAM, 10 CPU
- Memory **requests** sum: 5.7 Gi (71% of capacity — almost full just from reservations)
- Memory **limits** sum: 20.5 Gi (250% overcommit — this is why CoreDNS got OOM-killed)

**Hottest 5 pods by real RSS** (`kubectl top`):

| Pod | RSS | CPU |
|---|---|---|
| `worker-scraping-realtime` × 2 | ~900 Mi each (1.8 Gi total) | 1.2 cores total |
| `worker-enrichment` | 800 Mi | idle |
| `worker-scraping-detail` | 500 Mi | 0.63 cores |
| `worker-cover-bulk` × 4 | ~210 Mi each (840 Mi total) | idle |
| `rabbitmq` | 133 Mi | 76 m |

The expensive consumers are **Playwright-based scrapers** (realtime + detail). They drive most of the OrbStack CPU and ~60% of OrbStack RAM.

---

## Plan: three layers, ordered by impact-per-effort

### Layer 1 — Quick KEDA + replica caps (no code, ~5 min, biggest win)

**Estimated savings: ~3 Gi RAM, ~1.5 host CPU cores.** Trade-off: scraping takes ~2–3× longer when queues are deep; cover-letter generation runs in trickle mode instead of parallel.

Concrete edits to `k8s/workers/*.yaml`:

| Deployment | Change | Why |
|---|---|---|
| `worker-scraping-realtime` | `maxReplicaCount: 2 → 1`, `--concurrency=4 → 1` | Single biggest CPU consumer. One Playwright at a time. |
| `worker-scraping-detail` | already 1, drop `--concurrency` to 1 | Stop running 2 Playwright contexts per pod |
| `worker-scraping-bulk` | `--concurrency=2 → 1`, `maxReplicaCount: 2 → 1` | Same |
| `worker-cover-bulk` | `maxReplicaCount: 6 → 2`, `--concurrency=4 → 1` | 4 idle pods × 210Mi = wasted 600Mi |
| `worker-cover-generation` | `maxReplicaCount: 6 → 2`, `--concurrency=3 → 1` | Same pattern |
| `worker-cover-ranking` | `maxReplicaCount: 4 → 1` | Embedding scoring is fast; one is enough |
| `worker-cover-workflow` | `maxReplicaCount: 6 → 2` | Orchestration only — barely uses CPU |
| `worker-email` | `maxReplicaCount: 6 → 2` | Sending is I/O-bound, 2 is plenty |
| `worker-enrichment` | `maxReplicaCount: 8 → 2`, drop request mem 384Mi → 192Mi | 800Mi RSS for one pod looks like a leak — investigate later |
| All dispatch workers (`mnc-dispatch`, `consulting-dispatch`) | `minReplicaCount: 1 → 0` | They're idle 99 % of the time. KEDA spawns on demand. |
| `worker-maintenance` | `maxReplicaCount: 3 → 1` | Already idle most of the time |

Also bump `cooldownPeriod: 60 → 300` on all of them so pods don't thrash up/down.

### Layer 2 — Right-size container limits (code touches values only, ~15 min)

Many limits are 3–5× actual usage. Match limits to observed RSS + 40% headroom. Lower limits = kernel OOM-kills the *correct* pod under pressure, not CoreDNS.

| Deployment | Current limits.memory | Proposed |
|---|---|---|
| `worker-scraping-realtime` | 1536Mi | **1100Mi** |
| `worker-scraping-detail` | 1280Mi | **800Mi** |
| `worker-scraping-consulting-company` | 1500Mi | **1100Mi** |
| `worker-scraping-mnc-company` | 1500Mi | **1100Mi** |
| `worker-scraping-bulk` | 2Gi | **1Gi** |
| `worker-cover-bulk` | 1Gi | **400Mi** |
| `worker-cover-generation` | 512Mi | **300Mi** |
| `worker-enrichment` | 1536Mi | **800Mi** *(needs leak investigation first — see Layer 3)* |
| `ollama` | 1Gi | **scale to 0 replicas when not actively used** |

This also reduces the *sum* of memory limits from 20.5 Gi → ~10 Gi, killing the dangerous overcommit.

### Layer 3 — Structural / code (deeper, optional)

These need code or process changes but compound the savings:

1. **Lower RabbitMQ memory threshold** so producers back-pressure instead of accumulating 2000-message backlogs that then trigger KEDA scale-ups. Edit RabbitMQ config: `vm_memory_high_watermark.relative = 0.4`.
2. **Investigate `worker-enrichment` 800 Mi RSS at idle** — likely a leak or held HTTP client pools. Sample with `py-spy dump` once and fix.
3. **Consolidate cover-letter workers**: today there are 5 separate cover-* deployments. Many overlap. Merge into one or two with multiple `-Q` flags. Cuts ~6 pods worth of Celery overhead (~600 Mi).
4. **Idle Ollama**: it sits at 512 Mi reserved and 1 Gi limit even with no embedding traffic. Scale to 0 and have the embedding task wake it on demand, or move to a smaller model.
5. **Purge the current backlog**: `jh_scraping_detail` = 2205 messages, `jh_scraping_realtime` = 399. These accumulated during the earlier crash cascade and will pin workers at 100% CPU for hours. `rabbitmqctl purge_queue jh_scraping_detail` (and realtime) — if these are stale, drop them.

### Layer 4 — OrbStack host-level (one-time, outside the repo)

OrbStack's VM gets dynamic CPU/RAM by default. The host process at 265% CPU means scraping workers are competing for cores. Two options in **OrbStack → Settings → System**:

- **Reduce CPU limit**: set to `4` cores instead of unlimited. Forces scheduler discipline; everything just runs slower. Lowers fan + battery drain dramatically.
- **Reduce Memory limit**: set to `6 GB`. Forces the node to actually fit; KEDA can't overschedule.

If you do this *and* Layer 1, the cluster will fit comfortably with headroom.

---

## Expected end-state

| Metric | Before | After Layer 1+2 | After all layers |
|---|---|---|---|
| OrbStack host CPU | 265 % | ~100 % | ~60 % |
| OrbStack host RAM | 3.9 GB | ~2.2 GB | ~1.5 GB |
| Pods (steady-state) | 24 running | ~16 running | ~12 running |
| Memory limit sum | 20.5 Gi | ~10 Gi | ~7 Gi |
| Detail-queue drain rate | 25 jobs/min | ~10 jobs/min | ~10 jobs/min |
| Cover-letter throughput | ~4 parallel | 1–2 parallel | 1–2 parallel |
| Crash-cascade risk (CoreDNS OOM) | High | Eliminated | Eliminated |

---

## Recommended execution order

1. **Layer 4 first** (OrbStack settings) — 30-second host change, biggest comfort win, reversible.
2. **Layer 1** — edit the YAMLs in one batch, `kubectl apply -f k8s/workers/`, force-scale the over-replicated ones to the new caps. ~5 min.
3. **Layer 2** — bump container limits in the same YAMLs (one PR's worth of `sed`).
4. **Layer 3** items as time allows; the enrichment-leak investigation is the only one that's not pure config.

Each layer is independently reversible — just `git revert` the YAML change and `kubectl apply` again.
