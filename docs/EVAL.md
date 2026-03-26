# DAKV Evaluation Guide

## Quick Start

### 1. Start KV Store
```bash
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml
```

### 2. Start vLLM Server
```bash
bash scripts/run_vllm_server.sh
```

### 3. Run Benchmark
```bash
python scripts/run_bench.py --workload shared_prefix
```

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

## Running Tests

### Unit Tests
```bash
pytest src/dakv/tests/test_codec.py -v
pytest src/dakv/tests/test_planner.py -v
pytest src/dakv/tests/test_transport.py -v
```

### Integration Tests
```bash
pytest src/dakv/tests/test_end_to_end_local.py -v -s
```

### Smoke Test
```bash
bash scripts/smoke_test.sh
```

## Metrics Collection

### Prometheus Metrics
Access metrics at: `http://localhost:9090/metrics`

Key metrics:
- `dakv_manifest_queries_total`
- `dakv_manifest_hit_total`
- `dakv_remote_critical_bytes_total`
- `dakv_ttft_ms_bucket`
- `dakv_tpot_ms_bucket`

### Request-Level Metrics
Metrics are logged for each request:
```json
{
  "request_id": "...",
  "prefix_hit": true,
  "matched_tokens": 256,
  "plan_mode": "CRITICAL_INT8_THEN_FP16",
  "critical_bytes": 1048576,
  "refine_bytes": 2097152,
  "ttft_ms": 188.7,
  "fallback": false
}
```

## Experimental Workflows

### Experiment 1: TTFT vs Network Bandwidth
1. Configure different network profiles
2. Run shared prefix workload
3. Measure TTFT for first vs second request
4. Compare critical-only vs critical+refinement

### Experiment 2: Prefix Hit Rate
1. Run workload with varying prefix overlap
2. Measure manifest hit rate
3. Track remote load success rate
4. Analyze recompute fallback rate

### Experiment 3: Quality Degradation
1. Compare outputs: full fp16 vs int8-only vs int8+fp16
2. Measure perplexity difference
3. Evaluate generation quality

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

## Troubleshooting

### Issue: Manifest service not responding
**Solution:** Check if port 8081 is available, restart KV store

### Issue: Data server connection refused
**Solution:** Verify data server is running on port 9001

### Issue: vLLM fails to load connector
**Solution:** Ensure PYTHONPATH includes src/, check config format

### Issue: Low prefix hit rate
**Solution:** Increase prefix length, check tokenizer consistency

## Performance Expectations

| Network | Mode | Expected TTFT | Compression |
|---------|------|---------------|-------------|
| 1Gbps, 10ms | FULL_FP16 | < 100ms | 1x |
| 1Gbps, 20ms | INT8+FP16 | < 200ms | 2x |
| 100Mbps, 50ms | INT8_ONLY | < 500ms | 2x |

## Data Collection

Export metrics to CSV/JSON:
```python
from dakv.metrics.exporter import MetricsExporter

results = [...]  # Your metrics
MetricsExporter.export_to_csv(results, "results.csv")
MetricsExporter.export_to_json(results, "results.json")
```
