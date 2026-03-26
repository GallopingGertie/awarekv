from typing import List, Tuple


class Workload:
    @staticmethod
    def shared_prefix_workload(prefix_tokens: int = 400) -> List[Tuple[str, str]]:
        shared_prefix = "The quick brown fox jumps over the lazy dog. " * (prefix_tokens // 10)
        
        queries = [
            "What does this mean?",
            "Can you explain this in detail?",
            "Tell me more about the significance.",
            "What are the implications?",
            "How does this relate to the topic?",
            "Can you provide examples?",
            "What is the context here?",
            "Why is this important?"
        ]
        
        return [(shared_prefix, q) for q in queries]
    
    @staticmethod
    def random_workload(num_requests: int = 10) -> List[str]:
        prompts = [
            "Write a short story about a robot.",
            "Explain quantum mechanics in simple terms.",
            "What is the meaning of life?",
            "Describe a beautiful sunset.",
            "How does photosynthesis work?",
            "Tell me about the history of computers.",
            "What are the benefits of exercise?",
            "Explain the theory of relativity.",
            "Write a poem about nature.",
            "What is artificial intelligence?"
        ]
        
        return prompts[:num_requests]
