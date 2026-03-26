#!/bin/bash

set -e

echo "Tearing down network namespaces..."

sudo ip netns del ns_infer || true
sudo ip netns del ns_kv || true

echo "Network namespaces removed"
