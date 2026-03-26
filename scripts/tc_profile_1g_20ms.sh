#!/bin/bash

set -e

NETNS="${1:-ns_kv}"
DEVICE="${2:-veth_kv}"
BANDWIDTH="${3:-1000mbit}"
LATENCY="${4:-20ms}"

echo "Configuring network profile: $BANDWIDTH, $LATENCY RTT"

sudo ip netns exec "$NETNS" tc qdisc del dev "$DEVICE" root 2>/dev/null || true

sudo ip netns exec "$NETNS" tc qdisc add dev "$DEVICE" root handle 1: htb default 10

sudo ip netns exec "$NETNS" tc class add dev "$DEVICE" parent 1: classid 1:10 htb rate "$BANDWIDTH"

sudo ip netns exec "$NETNS" tc qdisc add dev "$DEVICE" parent 1:10 handle 10: netem delay "$LATENCY"

echo "Network profile applied successfully"
