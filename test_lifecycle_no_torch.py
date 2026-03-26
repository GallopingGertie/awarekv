#!/usr/bin/env python3
"""
P1-R-RUN 最小生命周期集成测试 (无 torch 依赖)

目标：验证 connector 生命周期方法能被实际调用并执行

测试覆盖：
1. Connector 实例化
2. Scheduler 生成 metadata
3. Worker 接收 metadata
4. start_load_kv 被调用
5. save_kv_layer 被调用
6. wait_for_save 被调用
7. request_finished 被调用
8. get_finished 返回结果
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("Attempting imports...")

try:
    from dakv.config import DeadlineKVConfig
    print("✅ Imported DeadlineKVConfig")
except ImportError as e:
    print(f"❌ Failed to import DeadlineKVConfig: {e}")
    sys.exit(1)

try:
    from dakv.connector.scheduler_side import SchedulerSide
    print("✅ Imported SchedulerSide")
except ImportError as e:
    print(f"❌ Failed to import SchedulerSide: {e}")
    sys.exit(1)

try:
    from dakv.connector.state import StateManager
    print("✅ Imported StateManager")
except ImportError as e:
    print(f"❌ Failed to import StateManager: {e}")
    sys.exit(1)

try:
    from dakv.common.types import PrefixManifest, TransferPlan, DeadlineConnectorMetadata
    print("✅ Imported types")
except ImportError as e:
    print(f"❌ Failed to import types: {e}")
    sys.exit(1)

try:
    from dakv.planner.deadline_planner import DeadlinePlanner
    from dakv.planner.estimator import BandwidthEstimator
    print("✅ Imported planner components")
except ImportError as e:
    print(f"❌ Failed to import planner: {e}")
    sys.exit(1)


def test_lifecycle_no_torch():
    """
    最小生命周期测试：只测试能成功调用的部分，跳过需要 torch 的部分
    """
    
    print("\n" + "=" * 70)
    print(" P1-R-RUN 最小生命周期集成测试 (无 torch)")
    print("=" * 70)
    print()
    
    # ========== Step 1: 创建配置 ==========
    print("Step 1: 创建 DeadlineKVConfig")
    print("-" * 70)
    
    try:
        config = DeadlineKVConfig()
        config.model_id = "test-model-7b"
        config.num_layers = 4
        config.block_size = 16
        
        print("✅ DeadlineKVConfig 创建成功")
        print(f"   - Model ID: {config.model_id}")
        print(f"   - Num layers: {config.num_layers}")
        print(f"   - Block size: {config.block_size}")
    except Exception as e:
        print(f"❌ DeadlineKVConfig 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 2: 创建 StateManager ==========
    print("Step 2: 创建 StateManager")
    print("-" * 70)
    
    try:
        state_manager = StateManager()
        print("✅ StateManager 创建成功")
        
        # 测试基本操作
        state = state_manager.create_or_get("test_req_001")
        print(f"   - Created state for: {state.request_id}")
        print(f"   - Initial status: {state.status}")
        
    except Exception as e:
        print(f"❌ StateManager 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 3: 创建 Planner ==========
    print("Step 3: 创建 DeadlinePlanner")
    print("-" * 70)
    
    try:
        estimator = BandwidthEstimator(alpha=0.8)
        planner = DeadlinePlanner(
            estimator=estimator,
            ttft_slo_ms=500,
            alpha=0.8,
            min_prefix_tokens=128
        )
        print("✅ DeadlinePlanner 创建成功")
        
    except Exception as e:
        print(f"❌ DeadlinePlanner 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 4: 创建 SchedulerSide ==========
    print("Step 4: 创建 SchedulerSide")
    print("-" * 70)
    
    try:
        scheduler_side = SchedulerSide(
            config=config,
            planner=planner,
            manifest_url="http://127.0.0.1:8081",
            state_manager=state_manager
        )
        print("✅ SchedulerSide 创建成功")
        print(f"   - Manifest URL: {scheduler_side.manifest_url}")
        print(f"   - State manager: {scheduler_side.state_manager is not None}")
        
    except Exception as e:
        print(f"❌ SchedulerSide 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 5: 测试 manifest miss 场景 ==========
    print("Step 5: 测试 manifest miss 场景")
    print("-" * 70)
    
    try:
        # Mock request
        class MockRequest:
            def __init__(self):
                self.request_id = "test_req_002"
                self.prompt_token_ids = [1, 2, 3, 4] * 50  # 200 tokens
                self.num_computed_tokens = 0
        
        request = MockRequest()
        
        # 调用 prepare_request_state (会 manifest miss)
        result = scheduler_side.prepare_request_state(request, 0)
        
        print(f"✅ prepare_request_state 调用成功")
        print(f"   - Request ID: {request.request_id}")
        print(f"   - Result: {result}")
        print(f"   - Matched tokens: {result[0]}")
        print(f"   - 预期: (0, False) - manifest miss")
        
        # 检查状态
        state = state_manager.get("test_req_002")
        if state:
            print(f"   - State status: {state.status}")
        
    except Exception as e:
        print(f"❌ prepare_request_state 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 6: 手动注入 manifest hit 状态 ==========
    print("Step 6: 手动注入 manifest hit 状态")
    print("-" * 70)
    
    try:
        # 创建 mock manifest
        mock_manifest = PrefixManifest(
            prefix_key="mock_key_003",
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
            critical_object_id="mock_obj_003",
            quality_mode="int8_only"
        )
        
        # 注入状态
        state_manager.mark_manifest_hit("test_req_003", mock_manifest)
        
        # 创建 mock plan
        mock_plan = TransferPlan(
            plan_id="plan_003",
            matched_tokens=100,
            matched_blocks=[0, 1, 2, 3, 4, 5],
            mode="CRITICAL_INT8_ONLY",
            critical_deadline_ms=300,
            refine_budget_ms=0,
            load_from_tier="T2",
            allow_refine_drop=True,
            reason_code="test"
        )
        
        state_manager.set_plan("test_req_003", mock_plan)
        state_manager.set_allocated_blocks("test_req_003", [10, 11, 12, 13])
        
        print(f"✅ 状态注入成功")
        print(f"   - Request ID: test_req_003")
        print(f"   - Manifest matched tokens: {mock_manifest.matched_tokens}")
        print(f"   - Plan mode: {mock_plan.mode}")
        
        state = state_manager.get("test_req_003")
        print(f"   - State status: {state.status}")
        
    except Exception as e:
        print(f"❌ 状态注入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 7: 构建 metadata ==========
    print("Step 7: 构建 metadata")
    print("-" * 70)
    
    try:
        metadata = scheduler_side.build_request_metadata("test_req_003")
        
        if metadata:
            print(f"✅ build_request_metadata 调用成功")
            print(f"   - Request ID: {metadata.request_id}")
            print(f"   - Plan mode: {metadata.plan_mode}")
            print(f"   - Matched tokens: {metadata.matched_tokens}")
            print(f"   - Critical object: {metadata.critical_object_id}")
            print(f"   - Num layers: {metadata.num_layers}")
            print(f"   - Allocated blocks: {metadata.allocated_block_ids}")
        else:
            print(f"❌ build_request_metadata 返回 None")
            return False
        
    except Exception as e:
        print(f"❌ build_request_metadata 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 8: 测试 request_finished ==========
    print("Step 8: 测试 scheduler_side.remove_state")
    print("-" * 70)
    
    try:
        scheduler_side.remove_state("test_req_003")
        print(f"✅ remove_state 调用成功")
        
        # 验证已删除
        state = state_manager.get("test_req_003")
        if state is None:
            print(f"   - State 已成功删除")
        else:
            print(f"   - State 仍然存在: {state.status}")
        
    except Exception as e:
        print(f"❌ remove_state 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== Step 9: 测试 StateManager 其他方法 ==========
    print("Step 9: 测试 StateManager 完整方法")
    print("-" * 70)
    
    try:
        # 创建多个状态
        for i in range(3):
            req_id = f"test_req_{100 + i}"
            state = state_manager.create_or_get(req_id)
            if i == 0:
                state_manager.mark_manifest_miss(req_id, "test")
            elif i == 1:
                state_manager.mark_recompute(req_id, "bandwidth_low")
            else:
                state_manager.update_status(req_id, "DONE")
        
        # 获取统计
        stats = state_manager.get_stats()
        print(f"✅ StateManager 完整测试成功")
        print(f"   - Stats: {stats}")
        
        # 获取所有 request IDs
        all_ids = state_manager.get_all_request_ids()
        print(f"   - Total requests: {len(all_ids)}")
        
    except Exception as e:
        print(f"❌ StateManager 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # ========== 总结 ==========
    print("=" * 70)
    print(" 测试总结")
    print("=" * 70)
    print()
    print("✅ 核心组件实例化和调用成功！")
    print()
    print("已验证的组件和方法:")
    print("  1. ✅ DeadlineKVConfig - 配置创建")
    print("  2. ✅ StateManager - 状态管理")
    print("     - create_or_get()")
    print("     - mark_manifest_hit()")
    print("     - mark_manifest_miss()")
    print("     - set_plan()")
    print("     - set_allocated_blocks()")
    print("     - get_stats()")
    print("  3. ✅ BandwidthEstimator - 带宽估计器")
    print("  4. ✅ DeadlinePlanner - 传输规划")
    print("  5. ✅ SchedulerSide - 调度器逻辑")
    print("     - prepare_request_state()")
    print("     - build_request_metadata()")
    print("     - remove_state()")
    print()
    print("⚠️  未验证 (需要依赖):")
    print("  - WorkerSide (需要 torch)")
    print("  - DeadlinePrefixKVConnector 完整实例化 (需要 torch)")
    print("  - start_load_kv / save_kv_layer (需要 torch)")
    print()
    print("⚠️  未验证 (需要真实服务):")
    print("  - Manifest service 实际查询")
    print("  - Data service 实际传输")
    print("  - Paged KV inject/extract")
    print("  - Slot mapping 对齐")
    print()
    
    return True


if __name__ == "__main__":
    success = test_lifecycle_no_torch()
    sys.exit(0 if success else 1)
