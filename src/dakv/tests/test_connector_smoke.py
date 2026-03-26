import pytest
from dakv.connector.deadline_connector import DeadlinePrefixKVConnector


class MockVLLMConfig:
    def __init__(self):
        self.kv_connector_extra_config = {
            "model_id": "test_model",
            "ttft_slo_ms": 500,
            "enable_refinement": True,
            "manifest": {"url": "http://127.0.0.1:8081"},
            "data": {"host": "127.0.0.1", "port": 9001}
        }


def test_connector_initialization():
    vllm_config = MockVLLMConfig()
    
    connector = DeadlinePrefixKVConnector(vllm_config, role="kv_both")
    
    assert connector is not None
    assert connector.prefer_cross_layer_blocks == True
    assert connector.role == "kv_both"
    assert connector.scheduler_side is not None
    assert connector.worker_side is not None


def test_connector_no_matched_tokens():
    vllm_config = MockVLLMConfig()
    connector = DeadlinePrefixKVConnector(vllm_config, role="kv_both")
    
    class MockRequest:
        request_id = "test_req"
        prompt_token_ids = [1, 2, 3]
    
    request = MockRequest()
    
    matched_tokens, _ = connector.get_num_new_matched_tokens(request, 0)
    
    assert matched_tokens == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
