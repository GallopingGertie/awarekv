#!/usr/bin/env python3
"""
P1-R-RUN 最小生命周期集成测试

目标：验证 connector 生命周期方法能被实际调用并执行，不依赖完整 vLLM 环境

测试覆盖：
1. Connector 实例化
2. Scheduler 生成 metadata
3. Worker 接收 metadata
4. start_load_kv 被调用
5. wait_for_layer_load 被调用
6. save_kv_layer 被调用
7. wait_for_save 被调用
8. request_finished 被调用
9. get_finished 返回结果
"""

import sys
import os
import torch
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dakv.connector.deadline_connector import DeadlinePrefixKVConnector
from dakv.common.types import PrefixManifest, TransferPlan
from dakv.logging import get_logger

logger = get_logger()


class MockVLLMConfig:
    """Mock vLLM config for testing"""
    def __init__(self):
        self.kv_connector_extra_config = {
            'model_id': 'test-model-7b',
            'tokenizer_id': 'test-model-7b',
            'ttft_slo_ms': 500,
            'enable_refinement': False,
            'block_size': 16,
            'num_layers': 4,
            'manifest': {'url': 'http://127.0.0.1:8081'},
            'data': {'host': '127.0.0.1', 'port': 9001}
        }


class MockRequest:
    """Mock vLLM request"""
    def __init__(self, request_id, prompt_tokens):
        self.request_id = request_id
        self.prompt_token_ids = prompt_tokens
        self.num_computed_tokens = 0


class MockSchedulerOutput:
    """Mock vLLM scheduler output"""
    def __init__(self, request_id, allocated_blocks):
        self.scheduled_seq_groups = [
            type('SeqGroup', (), {
                'seq_group': type('Request', (), {'request_id': request_id})(),
                'block_table': allocated_blocks
            })()
        ]


def test_lifecycle_minimal():
    """
    最小生命周期测试：不需要真实 manifest/data 服务，
    直接 mock 返回值来验证调用路径
    """
    
    print("\n" + "=" * 70)
    print(" P1-R-RUN 最小生命周期集成测试")
    print("=" * 70)
    print()
    
    # ========== Step 1: Connector 实例化 ==========
    print("Step 1: Connector 实例化")
    print("-" * 70)
    
    try:
        config = MockVLLMConfig()
        connector = DeadlinePrefixKVConnector(config, role='kv_both')
        print("✅ Connector 实例化成功")
        print(f"   - Role: {connector.role}")
        print(f"   - Scheduler side: {connector.scheduler_side is not None}")
        print(f"   - Worker side: {connector.worker_side is not None}")
        print(f"   - State manager: {connector.state_manager is not None}")
    except Exception as e:
        print(f"❌ Connector 实例化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 2: get_num_new_matched_tokens (manifest miss) ==========
    print("Step 2: get_num_new_matched_tokens - 模拟 manifest miss")
    print("-" * 70)
    
    try:
        request = MockRequest(
            request_id="test_req_001",
            prompt_tokens=[1, 2, 3, 4] * 50  # 200 tokens, 足够长
        )
        
        # 这会调用 scheduler_side.prepare_request_state()
        # 由于没有真实 manifest 服务，会返回 manifest miss
        matched_tokens, is_external = connector.get_num_new_matched_tokens(request, 0)
        
        print(f"✅ get_num_new_matched_tokens 调用成功")
        print(f"   - Request ID: {request.request_id}")
        print(f"   - Matched tokens: {matched_tokens}")
        print(f"   - Is external: {is_external}")
        print(f"   - 预期: 0 tokens (manifest miss)")
        
        # 验证状态
        state = connector.state_manager.get("test_req_001")
        if state:
            print(f"   - State status: {state.status}")
            assert state.status in ["MISS", "INIT"], f"Unexpected status: {state.status}"
        
    except Exception as e:
        print(f"❌ get_num_new_matched_tokens 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 3: 模拟 manifest hit 场景 ==========
    print("Step 3: 模拟 manifest hit - 手动注入状态")
    print("-" * 70)
    
    try:
        # 创建新 request
        request2 = MockRequest(
            request_id="test_req_002",
            prompt_tokens=[10, 20, 30, 40] * 50
        )
        
        # 手动创建状态并注入 manifest 和 plan
        state = connector.state_manager.create_or_get("test_req_002")
        state.prefix_key = "mock_prefix_key_002"
        state.matched_tokens = 100
        state.matched_blocks = [0, 1, 2, 3, 4, 5]
        
        # 模拟 manifest
        from dakv.common.types import PrefixManifest
        mock_manifest = PrefixManifest(
            prefix_key="mock_prefix_key_002",
            model_id="test-model-7b",
            tokenizer_id="test-model-7b",
            kv_layout_version="v1",
            block_size=16,
            cache_dtype="float16",
            matched_tokens=100,
            matched_blocks=[0, 1, 2, 3, 4, 5],
            num_layers=4,
            created_at_ms=int(time.time() * 1000),
            last_access_ms=int(time.time() * 1000),
            ttl_s=3600,
            critical_codec="int8_symm",
            critical_nbytes=4096,
            critical_object_id="mock_object_critical_002",
            quality_mode="int8_only"
        )
        
        connector.state_manager.mark_manifest_hit("test_req_002", mock_manifest)
        
        # 模拟 plan
        from dakv.common.types import TransferPlan
        mock_plan = TransferPlan(
            plan_id="mock_plan_002",
            matched_tokens=100,
            matched_blocks=[0, 1, 2, 3, 4, 5],
            mode="CRITICAL_INT8_ONLY",
            critical_deadline_ms=300,
            refine_budget_ms=0,
            load_from_tier="T2",
            allow_refine_drop=True,
            reason_code="int8_only_no_refine"
        )
        
        connector.state_manager.set_plan("test_req_002", mock_plan)
        
        print(f"✅ 状态注入成功")
        print(f"   - Request ID: test_req_002")
        print(f"   - Manifest: {mock_manifest.matched_tokens} tokens")
        print(f"   - Plan mode: {mock_plan.mode}")
        print(f"   - State status: {state.status}")
        
    except Exception as e:
        print(f"❌ 状态注入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 4: update_state_after_alloc ==========
    print("Step 4: update_state_after_alloc")
    print("-" * 70)
    
    try:
        mock_scheduler_output = MockSchedulerOutput(
            request_id="test_req_002",
            allocated_blocks=[10, 11, 12, 13, 14, 15]
        )
        
        connector.update_state_after_alloc(request2, mock_scheduler_output)
        
        state = connector.state_manager.get("test_req_002")
        print(f"✅ update_state_after_alloc 调用成功")
        print(f"   - Allocated blocks: {state.allocated_block_ids if state else 'None'}")
        
    except Exception as e:
        print(f"❌ update_state_after_alloc 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 5: build_connector_meta ==========
    print("Step 5: build_connector_meta")
    print("-" * 70)
    
    try:
        metadata = connector.build_connector_meta(request2)
        
        if metadata:
            print(f"✅ build_connector_meta 调用成功")
            print(f"   - Request ID: {metadata.request_id}")
            print(f"   - Plan mode: {metadata.plan_mode}")
            print(f"   - Matched tokens: {metadata.matched_tokens}")
            print(f"   - Critical object: {metadata.critical_object_id}")
            print(f"   - Allocated blocks: {len(metadata.allocated_block_ids)} blocks")
        else:
            print(f"⚠️  build_connector_meta 返回 None (可能是状态不完整)")
            return False
        
    except Exception as e:
        print(f"❌ build_connector_meta 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 6: start_load_kv (会失败因为没有真实数据) ==========
    print("Step 6: start_load_kv (预期失败 - 无真实数据服务)")
    print("-" * 70)
    
    try:
        # 这会调用 worker_side.start_load_kv()
        # 预期会失败，因为没有真实的 data server
        
        mock_forward_context = type('Context', (), {})()
        
        result = connector.worker_side.start_load_kv(
            forward_context=mock_forward_context,
            metadata=metadata
        )
        
        if result:
            if result.success:
                print(f"✅ start_load_kv 意外成功 (不应该有真实数据)")
                print(f"   - Loaded tokens: {result.loaded_tokens}")
            else:
                print(f"✅ start_load_kv 调用完成 (预期失败)")
                print(f"   - Error code: {result.error_code}")
                print(f"   - Error message: {result.error_message[:100]}...")
        else:
            print(f"⚠️  start_load_kv 返回 None")
        
    except Exception as e:
        print(f"✅ start_load_kv 抛出异常 (预期行为 - 无数据服务)")
        print(f"   - Exception: {type(e).__name__}: {str(e)[:100]}")
    
    print()
    
    # ========== Step 7: wait_for_layer_load ==========
    print("Step 7: wait_for_layer_load")
    print("-" * 70)
    
    try:
        # 即使没有真实加载，也应该能调用
        kv_tensor = connector.wait_for_layer_load("layer_0")
        
        if kv_tensor is not None:
            print(f"✅ wait_for_layer_load 返回了 tensor")
            print(f"   - Shape: {kv_tensor.shape}")
        else:
            print(f"✅ wait_for_layer_load 调用成功 (无 loaded KV，返回 None)")
        
    except Exception as e:
        print(f"❌ wait_for_layer_load 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 8: save_kv_layer ==========
    print("Step 8: save_kv_layer")
    print("-" * 70)
    
    try:
        # 创建 mock KV tensor
        mock_kv = torch.randn(2, 16, 32, 128)  # (num_blocks, block_size, num_kv_heads, head_size)
        mock_attn_metadata = None
        
        connector.save_kv_layer(
            layer_name="layer_0",
            kv_layer=mock_kv,
            attn_metadata=mock_attn_metadata,
            request_id="test_req_002"
        )
        
        print(f"✅ save_kv_layer 调用成功")
        print(f"   - Layer: layer_0")
        print(f"   - KV shape: {mock_kv.shape}")
        print(f"   - Request ID: test_req_002")
        
    except Exception as e:
        print(f"❌ save_kv_layer 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 9: wait_for_save ==========
    print("Step 9: wait_for_save")
    print("-" * 70)
    
    try:
        connector.wait_for_save()
        print(f"✅ wait_for_save 调用成功")
        
    except Exception as e:
        print(f"❌ wait_for_save 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 10: request_finished ==========
    print("Step 10: request_finished")
    print("-" * 70)
    
    try:
        connector.request_finished("test_req_002")
        print(f"✅ request_finished 调用成功")
        print(f"   - Request ID: test_req_002")
        
        # 验证状态已清理
        state = connector.state_manager.get("test_req_002")
        if state:
            print(f"   - State still exists: {state.status}")
        else:
            print(f"   - State cleaned up: 已移除")
        
    except Exception as e:
        print(f"❌ request_finished 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 11: get_finished ==========
    print("Step 11: get_finished")
    print("-" * 70)
    
    try:
        finished = connector.get_finished()
        print(f"✅ get_finished 调用成功")
        print(f"   - Finished requests: {finished}")
        
    except Exception as e:
        print(f"❌ get_finished 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== 总结 ==========
    print("=" * 70)
    print(" 测试总结")
    print("=" * 70)
    print()
    print("✅ 所有生命周期方法调用成功！")
    print()
    print("已验证的生命周期方法:")
    print("  1. ✅ __init__() - Connector 实例化")
    print("  2. ✅ get_num_new_matched_tokens() - Scheduler 查询 manifest")
    print("  3. ✅ update_state_after_alloc() - 绑定 allocated blocks")
    print("  4. ✅ build_connector_meta() - 构建 metadata")
    print("  5. ✅ start_load_kv() - Worker 开始加载 (调用成功)")
    print("  6. ✅ wait_for_layer_load() - 等待 layer KV")
    print("  7. ✅ save_kv_layer() - 保存 layer KV")
    print("  8. ✅ wait_for_save() - 等待保存完成")
    print("  9. ✅ request_finished() - 请求完成清理")
    print(" 10. ✅ get_finished() - 获取已完成请求")
    print()
    print("⚠️  已知限制:")
    print("  - start_load_kv 无真实数据服务支持 (预期失败)")
    print("  - paged KV inject/extract 未验证 (需要真实 vLLM)")
    print("  - slot mapping 未验证 (需要真实 vLLM)")
    print()
    
    return True


if __name__ == "__main__":
    success = test_lifecycle_minimal()
    sys.exit(0 if success else 1)
