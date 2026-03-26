# DAKV Evaluation Guide

> **⚠️ Status**: This evaluation guide describes the planned metrics and experiments. Many features marked as (WIP) are currently being implemented.

## Current Status

### ✅ Currently Available Metrics

- Manifest query/hit rate
- Transport layer put/get operations
- Basic codec encode/decode timing
- Planner mode selection (in logs)

### 🚧 Work In Progress

- TTFT/TPOT/ITL measurements (P5-R)
- Request-level tracking (P1-R)
- Real prefix hit/miss flow (P2-R)
- Refinement success/drop metrics (P4-R)

### ⏳ Planned

- Paper-level benchmark automation
- Network sweep experiments
- Quality degradation analysis

---

## Quick Start (Minimal)

### 1. Start KV Store
```bash
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml
```

### 2. Run Basic Tests
```bash
# Test transport
pytest src/dakv/tests/test_transport.py -v

# Test manifest
pytest src/dakv/tests/test_manifest.py -v

# Test end-to-end local
pytest src/dakv/tests/test_end_to_end_local.py -v -s
```

### 3. Verify Services
```bash
# Check manifest service
curl http://127.0.0.1:8081/manifest/stats

# Check data server (put/get)
# (See test_end_to_end_local.py for examples)
```

---

## Quick Start (Integration - WIP)

> ⚠️ The following requires vLLM connector integration (P1-R~P3-R in progress)

### 2. Start vLLM Server (WIP)
```bash
bash scripts/run_vllm_server.sh
```

### 3. Run Benchmark (WIP)
```bash
python scripts/run_bench.py --workload shared_prefix
```

---

## Network Simulation

### Setup Network Namespaces
```bash
sudo bash scripts/netns_setup.sh
```

### Apply Network Profile (1Gbps, 20ms RTT)
```bash
sudo bash scripts/tc_profile_1g_20ms.sh
```

### Apply Network Profile (100Mbps, 50ms RTT, 1% loss)
```bash
sudo bash scripts/tc_profile_100m_50ms_loss1.sh
```

### Teardown
```bash
sudo bash scripts/netns_teardown.sh
```

---

## Running Tests

### Unit Tests (Available Now)
```bash
# Test codec
pytest src/dakv/tests/test_codec.py -v

# Test planner
pytest src/dakv/tests/test_planner.py -v

# Test transport
pytest src/dakv/tests/test_transport.py -v
```

### Integration Tests (Available Now)
```bash
pytest src/dakv/tests/test_end_to_end_local.py -v -s
```

### Connector Tests (WIP)
```bash
# Will be available after P1-R completion
pytest src/dakv/tests/test_connector_smoke.py -v
pytest src/dakv/tests/test_connector_lifecycle.py -v
```

### Smoke Test (WIP)
```bash
bash scripts/smoke_test.sh
```

---

## Metrics Collection (Planned)

### Prometheus Metrics (Planned for P5-R)
Access metrics at: `http://localhost:9090/metrics`

**Planned metrics:**
- `dakv_manifest_queries_total{hit=...}`
- `dakv_plan_mode_total{mode=...}`
- `dakv_recompute_total{reason=...}`
- `dakv_critical_bytes_total`
- `dakv_refinement_bytes_total`
- `dakv_critical_load_latency_ms`
- `dakv_refinement_load_latency_ms`
- `dakv_ttft_ms_bucket`
- `dakv_tpot_ms_bucket`

### Request-Level Metrics (Planned for P5-R)
Metrics will be logged for each request:
```json
{
  "request_id": "req_123",
  "prefix_hit": true,
  "matched_tokens": 256,
  "plan_mode": "CRITICAL_INT8_THEN_FP16",
  "critical_bytes": 1048576,
  "refine_bytes": 2097152,
  "critical_load_ms": 41.2,
  "refine_load_ms": 72.8,
  "refine_applied": true,
  "refine_dropped": false,
  "ttft_ms": 188.7,
  "tpot_ms": 12.3,
  "fallback": false,
  "fallback_reason": null
}
```

---

## Experimental Workflows (Planned)

### Experiment 1: TTFT vs Network Bandwidth (P5-R)
1. Configure different network profiles
2. Run shared prefix workload
3. Measure TTFT for first vs second request
4. Compare critical-only vs critical+refinement
5. Track fallback rate

**Expected output:**
- CSV with columns: network_profile, request_num, ttft_ms, plan_mode, prefix_hit
- TTFT P50/P95 comparison

### Experiment 2: Prefix Hit Rate (P2-R + P5-R)
1. Run workload with varying prefix overlap
2. Measure manifest hit rate
3. Track remote load success rate
4. Analyze recompute fallback rate

**Expected output:**
- Manifest hit ratio
- Load success ratio
- Fallback reason distribution

### Experiment 3: Quality Degradation (P4-R + P5-R)
1. Compare outputs: full fp16 vs int8-only vs int8+fp16
2. Measure perplexity difference
3. Evaluate generation quality (BLEU/ROUGE)

**Expected output:**
- Quality metrics per mode
- Latency vs quality tradeoff

### Experiment 4: Mode Ablation (P5-R)
Fix workload, compare:
- No external KV (baseline / recompute)
- Full FP16 load
- INT8 only
- INT8 then FP16

**Expected output:**
- Latency/bandwidth/quality tradeoff table

---

## Configuration Tuning

### Key Parameters

**Deadline Control:**
- `ttft_slo_ms`: Target TTFT (default: 500ms)
- `planner.alpha`: Budget allocation (default: 0.8)

**Network:**
- `network.timeout_ms`: Critical timeout (default: 1000ms)
- `network.refine_timeout_ms`: Refinement timeout (default: 150ms)

**Cache:**
- `host_cache.max_bytes`: T1 cache size (default: 4GB)
- `storage.ttl_seconds`: Object TTL (default: 3600s)

**Planner:**
- `planner.min_prefix_tokens`: Minimum prefix length (default: 128)

**Codec:**
- `critical_codec`: int8_symm / int8_asymm
- `refinement_codec`: fp16_raw / fp16_compressed

---

## Troubleshooting

### Issue: Manifest service not responding
**Solution:** Check if port 8081 is available
```bash
lsof -i :8081
# Restart KV store if needed
```

### Issue: Data server connection refused
**Solution:** Verify data server is running on port 9001
```bash
lsof -i :9001
# Check logs in KV store output
```

### Issue: vLLM fails to load connector (WIP)
**Solution:** 
- Ensure PYTHONPATH includes src/
- Check connector config format
- Verify vLLM version matches (0.6.3.post1)

### Issue: Low prefix hit rate (After P2-R)
**Solution:** 
- Increase `planner.min_prefix_tokens`
- Check tokenizer consistency
- Verify prefix_key computation logic

---

## Performance Expectations (Target)

| Network | Mode | Target TTFT | Compression |
|---------|------|-------------|-------------|
| 1Gbps, 10ms | FULL_FP16 | < 100ms | 1x |
| 1Gbps, 20ms | INT8+FP16 | < 200ms | 2x |
| 100Mbps, 50ms | INT8_ONLY | < 500ms | 2x |
| <10Mbps | RECOMPUTE | fallback | N/A |

*These are target numbers; actual performance will be measured after P2-R~P5-R completion.*

---

## Data Collection (Planned for P5-R)

### Export Metrics to CSV/JSON

```python
from dakv.metrics.exporter import MetricsExporter

# Collect metrics from benchmark
results = run_benchmark(...)

# Export
MetricsExporter.export_to_csv(results, "results.csv")
MetricsExporter.export_to_json(results, "results.json")
```

### Parse Logs

```python
from dakv.bench.report import parse_request_logs

# Parse from vLLM/DAKV logs
metrics = parse_request_logs("vllm.log")

# Generate report
generate_summary_report(metrics, output="summary.md")
```

---

## Roadmap

### P1-R: vLLM Connector Lifecycle
- **Goal**: Real connector integration with vLLM
- **Metrics unlocked**: Request-level state tracking

### P2-R: Prefix-Level Save/Load
- **Goal**: Real save/load cycle with manifest
- **Metrics unlocked**: Manifest hit/miss, prefix reuse

### P3-R: Paged KV Apply/Extract
- **Goal**: Real paged KV buffer interaction
- **Metrics unlocked**: Load success, KV injection latency

### P4-R: Refinement Background
- **Goal**: Async refinement with timeout/drop
- **Metrics unlocked**: Refine success/drop, degraded mode

### P5-R: Paper-Level Benchmarking
- **Goal**: Automated experiments and reporting
- **Metrics unlocked**: TTFT/TPOT P50/P95, plan mode distribution, quality metrics

### P6: Testing and Documentation
- **Goal**: Comprehensive testing and final docs
- **Deliverable**: Reproducible experimental setup

---

## Current Limitations

1. **TTFT/TPOT measurement**: Requires vLLM integration (P1-R~P3-R)
2. **Prefix hit tracking**: Requires save/load cycle (P2-R)
3. **Refinement metrics**: Requires background refine (P4-R)
4. **Automated benchmark**: Requires full integration (P5-R)

## Next Steps

1. Complete P1-R: Make connector a real `KVConnectorBase_V1` subclass
2. Complete P2-R: Implement prefix-level object save/load with manifest
3. Complete P3-R: Add real paged KV apply/extract operations
4. Complete P4-R: Implement async refinement with drop mechanism
5. Complete P5-R: Upgrade benchmark to measure TTFT/TPOT/plan_mode/etc.

---

**Last Updated**: 2026-03-26  
**Status**: P0-HOTFIX complete, P1-R~P6 in progress
