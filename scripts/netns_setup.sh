#!/bin/bash

set -e

echo "Setting up network namespaces for DAKV testing..."

sudo ip netns add ns_infer || true
sudo ip netns add ns_kv || true

sudo ip link add veth_infer type veth peer name veth_kv || true

sudo ip link set veth_infer netns ns_infer
sudo ip link set veth_kv netns ns_kv

sudo ip netns exec ns_infer ip addr add 10.0.0.1/24 dev veth_infer
sudo ip netns exec ns_kv ip addr add 10.0.0.2/24 dev veth_kv

sudo ip netns exec ns_infer ip link set veth_infer up
sudo ip netns exec ns_kv ip link set veth_kv up

sudo ip netns exec ns_infer ip link set lo up
sudo ip netns exec ns_kv ip link set lo up

echo "Network namespaces created successfully"
echo "  ns_infer: 10.0.0.1"
echo "  ns_kv: 10.0.0.2"
