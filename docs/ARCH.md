# DAKV Architecture

## Overview

DAKV (Deadline-Aware KV) is a tiered KV caching system for vLLM that enables deadline-aware prefix KV loading from remote storage.

## System Architecture

```
┌─────────────────┐
│  vLLM Engine    │
│  with DAKV      │
│  Connector      │
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
    ┌────▼─────┐    ┌─────▼──────┐
    │Scheduler │    │   Worker   │
    │   Side   │    │    Side    │
    └────┬─────┘    └─────┬──────┘
         │                │
         │                │
    ┌────▼─────┐    ┌─────▼──────┐
    │ Planner  │    │  Loader /  │
    │          │    │   Saver    │
    └──────────┘    └─────┬──────┘
                          │
                    ┌─────▼──────┐
                    │ Transport  │
                    │  Layer     │
                    └─────┬──────┘
                          │
                    ┌─────▼──────┐
                    │   Remote   │
                    │ KV Store   │
                    └────────────┘
```

## Storage Tiers

- **T0 (GPU HBM)**: Active KV cache in vLLM
- **T1 (CPU Pinned Memory)**: Local host cache for recently accessed KV
- **T2 (Remote Storage)**: Distributed KV store with manifest service

## Transfer Modes

1. **FULL_FP16**: Full precision transfer (fast network)
2. **CRITICAL_INT8_ONLY**: Int8 only (degraded quality)
3. **CRITICAL_INT8_THEN_FP16**: Int8 critical + fp16 refinement (normal)
4. **RECOMPUTE**: Skip remote load, recompute KV

## Components

### Planner
- Bandwidth estimation (EWMA)
- Deadline-aware transfer planning
- Mode selection based on network conditions

### Codec
- FP16 raw encoding (baseline)
- Int8 symmetric quantization (critical)
- Residual encoding (future)

### Transport
- Binary protocol with length-prefixed frames
- Critical channel (high priority, strict deadline)
- Refinement channel (low priority, droppable)

### Connector
- Scheduler-side: Manifest query, transfer planning
- Worker-side: Remote load/save, codec operations
- vLLM integration via KVConnectorBase_V1
