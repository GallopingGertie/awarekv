import json
import csv
from typing import List, Dict
from dakv.logging import get_logger


logger = get_logger()


class MetricsParser:
    @staticmethod
    def compute_statistics(results: List[Dict]) -> Dict:
        if not results:
            return {}
        
        latencies = [r["latency_ms"] for r in results if "latency_ms" in r]
        
        if not latencies:
            return {}
        
        latencies.sort()
        
        n = len(latencies)
        
        stats = {
            "total_requests": n,
            "mean_latency_ms": sum(latencies) / n,
            "median_latency_ms": latencies[n // 2],
            "p95_latency_ms": latencies[int(n * 0.95)] if n > 1 else latencies[0],
            "p99_latency_ms": latencies[int(n * 0.99)] if n > 1 else latencies[0],
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies)
        }
        
        return stats
    
    @staticmethod
    def export_results(results: List[Dict], output_path: str):
        ext = output_path.split(".")[-1]
        
        if ext == "json":
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
        elif ext == "csv":
            if results:
                with open(output_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=results[0].keys())
                    writer.writeheader()
                    writer.writerows(results)
        
        logger.info(f"Results exported to {output_path}")
