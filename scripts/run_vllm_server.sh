#!/bin/bash

set -e

CONFIG_FILE="${1:-configs/deadline_kv_local.yaml}"

export VLLM_KV_TRANSFER_CONFIG='{
  "kv_connector": "DeadlinePrefixKVConnector",
  "kv_connector_module_path": "dakv.connector.deadline_connector",
  "kv_role": "kv_both",
  "kv_rank": 0,
  "kv_parallel_size": 1,
  "kv_load_failure_policy": "recompute"
}'

MODEL=${MODEL:-"meta-llama/Llama-2-7b-hf"}
TP=${TP:-1}
PORT=${PORT:-8000}

echo "Starting vLLM server with DAKV connector"
echo "Model: $MODEL"
echo "Tensor Parallel: $TP"
echo "Port: $PORT"
echo "Config: $CONFIG_FILE"

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --tensor-parallel-size "$TP" \
    --port "$PORT" \
    --enable-prefix-caching \
    --kv-connector-config "$VLLM_KV_TRANSFER_CONFIG" \
    --kv-connector-extra-config "@$CONFIG_FILE"
