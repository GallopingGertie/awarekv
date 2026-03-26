# DAKV: Deadline-Aware Prefix KV for vLLM

A deadline-aware prefix KV caching system with tiered storage for vLLM.

## System Requirements

### Tested Environment
- **Python**: 3.9+
- **PyTorch**: 2.1.0
- **CUDA**: 11.8+
- **vLLM**: 0.6.3.post1
- **GPU**: 4×V100 (32GB) or equivalent
- **OS**: Linux (tested on Ubuntu 20.04/22.04)

### Important Note on Versions
This project uses **fixed versions** to ensure stability. Do not upgrade dependencies without testing, as vLLM's KV Connector V1 API may change between versions.

## Features

- **Tiered Storage**: GPU HBM (T0) → CPU Pinned Memory (T1) → Remote KV Store (T2)
- **Deadline-Aware Transfer**: Critical (int8) + Refinement (fp16) two-tier transmission
- **vLLM Integration**: Custom KV connector for seamless integration
- **Network Simulation**: Support for bandwidth/RTT/loss injection via netns/tc

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Remote KV Store

```bash
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml
```

### 3. Start vLLM Server

```bash
bash scripts/run_vllm_server.sh
```

### 4. Run Benchmark

```bash
python scripts/run_bench.py --workload shared_prefix
```

## Architecture

- **src/dakv/common**: Shared types and utilities
- **src/dakv/codec**: KV encoding/decoding (fp16, int8)
- **src/dakv/store**: Manifest and object storage
- **src/dakv/transport**: Network protocol and channels
- **src/dakv/planner**: Deadline-aware transfer planning
- **src/dakv/tier**: Host cache and GPU operations
- **src/dakv/connector**: vLLM connector implementation
- **src/dakv/metrics**: Metrics collection and export

## Configuration

See `configs/` directory for example configurations.

## Testing

```bash
pytest src/dakv/tests/
```
