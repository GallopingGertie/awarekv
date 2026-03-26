import requests
import time
from typing import List, Dict
from dakv.logging import get_logger


logger = get_logger()


class VLLMClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.0) -> Dict:
        url = f"{self.base_url}/v1/completions"
        
        payload = {
            "model": "meta-llama/Llama-2-7b-hf",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        start_time = time.time()
        
        try:
            response = requests.post(url, json=payload, timeout=120)
            
            if response.status_code != 200:
                logger.error(f"Request failed: {response.status_code}")
                return None
            
            end_time = time.time()
            
            result = response.json()
            
            return {
                "success": True,
                "latency_ms": (end_time - start_time) * 1000,
                "response": result
            }
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
