import time
from typing import List, Dict
from dakv.bench.client import VLLMClient
from dakv.bench.workloads import Workload
from dakv.logging import get_logger


logger = get_logger()


class LongBenchRunner:
    def __init__(self, client: VLLMClient):
        self.client = client
    
    def run(self, num_iterations: int = 5) -> List[Dict]:
        logger.info(f"Running LongBench-style workload with {num_iterations} iterations")
        
        workload = Workload.shared_prefix_workload(prefix_tokens=1000)
        
        results = []
        
        for iteration in range(num_iterations):
            logger.info(f"\nIteration {iteration + 1}/{num_iterations}")
            
            for i, (prefix, query) in enumerate(workload):
                prompt = prefix + query
                
                logger.info(f"  Request {i+1}/{len(workload)}: {len(prompt)} chars")
                
                result = self.client.generate(prompt, max_tokens=50)
                
                if result and result.get("success"):
                    results.append({
                        "iteration": iteration,
                        "request_id": i,
                        "prompt_length": len(prompt),
                        "latency_ms": result["latency_ms"]
                    })
                    logger.info(f"    Latency: {result['latency_ms']:.1f}ms")
                
                time.sleep(0.5)
        
        return results
