# DAKV: Deadline-Aware Prefix KV for vLLM

> **⚠️ Project Status**: This project is under active development. Core components (vLLM connector lifecycle, paged KV apply/extract, prefix-level save/load) are being implemented.

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

## Project Status

### ✅ Completed
- Version pinning (torch==2.1.0, vLLM==0.6.3.post1)
- Module scaffolding (planner, codec, store, transport, tier, connector)
- Basic planner logic (deadline-aware mode selection)
- Codec implementations (fp16, int8)
- Transport protocol (critical/refinement channels)
- Manifest service and object storage

### 🚧 In Progress
- **vLLM Connector V1 lifecycle integration** (P1-R)
- **Prefix-level save/load main path** (P2-R)
- **Real paged KV apply/extract** (P3-R)
- **Background refinement mechanism** (P4-R)

### ⏳ Planned
- Paper-level benchmarking and metrics (P5-R)
- Comprehensive testing and documentation (P6)

## Features

- **Tiered Storage**: GPU HBM (T0) → CPU Pinned Memory (T1) → Remote KV Store (T2)
- **Deadline-Aware Transfer**: Critical (int8) + Refinement (fp16) two-tier transmission
- **vLLM Integration**: Custom KV connector for seamless integration
- **Network Simulation**: Support for bandwidth/RTT/loss injection via netns/tc

## Quick Start

### Quickstart-Minimal (Currently Available)

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Start Remote KV Store

```bash
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml
```

#### 3. Run Basic Tests

```bash
# Test codec
pytest src/dakv/tests/test_codec.py

# Test transport
pytest src/dakv/tests/test_transport.py

# Test manifest service
pytest src/dakv/tests/test_manifest.py
```

### Quickstart-Integration (Work In Progress)

> ⚠️ The full vLLM integration is being implemented. The following steps are not yet fully functional.

#### 3. Start vLLM Server (WIP)

```bash
bash scripts/run_vllm_server.sh
```

#### 4. Run Benchmark (WIP)

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
