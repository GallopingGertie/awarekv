#!/bin/bash

set -e

echo "Running DAKV smoke test..."

echo "Step 1: Starting KV store..."
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml &
KV_STORE_PID=$!
sleep 3

echo "Step 2: Checking KV store health..."
curl -f http://127.0.0.1:8081/manifest/stats || { echo "KV store not ready"; kill $KV_STORE_PID; exit 1; }

echo "Step 3: KV store is ready!"
echo "  Manifest service: http://127.0.0.1:8081"
echo "  Data server: 127.0.0.1:9001"

echo ""
echo "Smoke test passed!"
echo "To stop KV store: kill $KV_STORE_PID"
echo ""
echo "Next steps:"
echo "  1. Start vLLM server: bash scripts/run_vllm_server.sh"
echo "  2. Run benchmark: python scripts/run_bench.py"
