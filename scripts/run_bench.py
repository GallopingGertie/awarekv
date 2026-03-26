#!/usr/bin/env python3

import argparse
import time
import requests
import json
from typing import List
from dakv.logging import get_logger


logger = get_logger()


class BenchmarkClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate(self, prompt: str, max_tokens: int = 100) -> dict:
        url = f"{self.base_url}/v1/completions"
        
        payload = {
            "model": "meta-llama/Llama-2-7b-hf",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": 0.0
        }
        
        start_time = time.time()
        
        response = requests.post(url, json=payload, timeout=60)
        
        end_time = time.time()
        
        if response.status_code != 200:
            logger.error(f"Request failed: {response.status_code}")
            return None
        
        result = response.json()
        
        elapsed_ms = (end_time - start_time) * 1000
        
        return {
            "prompt": prompt,
            "response": result,
            "elapsed_ms": elapsed_ms
        }


def run_shared_prefix_benchmark(client: BenchmarkClient):
    logger.info("Running shared prefix benchmark...")
    
    shared_prefix = "The quick brown fox jumps over the lazy dog. " * 20
    
    suffixes = [
        "What does this mean?",
        "Can you explain this?",
        "Tell me more about this.",
        "What is the significance?"
    ]
    
    results = []
    
    for i, suffix in enumerate(suffixes):
        prompt = shared_prefix + suffix
        logger.info(f"Request {i+1}/{len(suffixes)}: {len(prompt)} chars")
        
        result = client.generate(prompt, max_tokens=50)
        
        if result:
            results.append(result)
            logger.info(f"  Completed in {result['elapsed_ms']:.1f}ms")
        
        time.sleep(1)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Run DAKV Benchmark")
    parser.add_argument("--url", type=str, default="http://localhost:8000",
                        help="vLLM server URL")
    parser.add_argument("--workload", type=str, default="shared_prefix",
                        choices=["shared_prefix", "random"],
                        help="Workload type")
    
    args = parser.parse_args()
    
    client = BenchmarkClient(args.url)
    
    if args.workload == "shared_prefix":
        results = run_shared_prefix_benchmark(client)
    else:
        logger.error(f"Unknown workload: {args.workload}")
        return
    
    logger.info(f"\n{'='*60}")
    logger.info("Benchmark Results:")
    logger.info(f"Total requests: {len(results)}")
    
    if results:
        avg_latency = sum(r['elapsed_ms'] for r in results) / len(results)
        logger.info(f"Average latency: {avg_latency:.1f}ms")
    
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
