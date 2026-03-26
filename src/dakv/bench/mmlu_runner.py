import time
from typing import List, Dict
from dakv.bench.client import VLLMClient
from dakv.logging import get_logger


logger = get_logger()


class MMLURunner:
    def __init__(self, client: VLLMClient):
        self.client = client
    
    def run(self, num_questions: int = 10) -> List[Dict]:
        logger.info(f"Running MMLU-style workload with {num_questions} questions")
        
        questions = self._get_sample_questions()[:num_questions]
        
        results = []
        
        for i, question in enumerate(questions):
            logger.info(f"\nQuestion {i+1}/{len(questions)}")
            
            result = self.client.generate(question, max_tokens=100)
            
            if result and result.get("success"):
                results.append({
                    "question_id": i,
                    "question": question,
                    "latency_ms": result["latency_ms"]
                })
                logger.info(f"  Latency: {result['latency_ms']:.1f}ms")
            
            time.sleep(0.5)
        
        return results
    
    def _get_sample_questions(self) -> List[str]:
        return [
            "What is the capital of France? A) London B) Paris C) Berlin D) Madrid",
            "Which planet is known as the Red Planet? A) Venus B) Mars C) Jupiter D) Saturn",
            "What is 2 + 2? A) 3 B) 4 C) 5 D) 6",
            "Who wrote Romeo and Juliet? A) Shakespeare B) Dickens C) Austen D) Orwell",
            "What is the speed of light? A) 300,000 km/s B) 150,000 km/s C) 500,000 km/s D) 1,000,000 km/s",
            "What is the largest ocean? A) Atlantic B) Indian C) Arctic D) Pacific",
            "What is H2O? A) Oxygen B) Water C) Hydrogen D) Carbon",
            "Who painted the Mona Lisa? A) Van Gogh B) Picasso C) Da Vinci D) Monet",
            "What is the smallest prime number? A) 0 B) 1 C) 2 D) 3",
            "What year did World War II end? A) 1943 B) 1944 C) 1945 D) 1946"
        ]
