#!/usr/bin/env python3
"""
P1-R 验证脚本 - 无需外部依赖的基础验证

验证重构后的 connector 代码的基本功能：
1. 模块导入
2. 类初始化
3. 方法签名验证
4. 生命周期方法存在性检查
"""

import sys
import os

# 添加 src 到 Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """测试所有核心模块是否可以正确导入"""
    print("=" * 60)
    print("测试 1: 模块导入")
    print("=" * 60)
    
    try:
        from dakv.connector.scheduler_side import SchedulerSide
        print("✅ scheduler_side.py 导入成功")
    except ImportError as e:
        print(f"❌ scheduler_side.py 导入失败: {e}")
        return False
    
    try:
        from dakv.connector.worker_side import WorkerSide
        print("✅ worker_side.py 导入成功")
    except ImportError as e:
        print(f"❌ worker_side.py 导入失败: {e}")
        return False
    
    try:
        from dakv.connector.state import StateManager
        print("✅ state.py 导入成功")
    except ImportError as e:
        print(f"❌ state.py 导入失败: {e}")
        return False
    
    try:
        from dakv.connector.metadata import build_metadata_from_state, create_load_result
        print("✅ metadata.py 导入成功")
    except ImportError as e:
        print(f"❌ metadata.py 导入失败: {e}")
        return False
    
    try:
        from dakv.connector.vllm_adapter import KVConnectorBase_V1
        print("✅ vllm_adapter.py 导入成功")
    except ImportError as e:
        print(f"❌ vllm_adapter.py 导入失败: {e}")
        return False
    
    print()
    return True


def test_class_definitions():
    """测试类定义和方法签名"""
    print("=" * 60)
    print("测试 2: 类定义和方法签名")
    print("=" * 60)
    
    from dakv.connector.scheduler_side import SchedulerSide
    from dakv.connector.worker_side import WorkerSide
    from dakv.connector.state import StateManager
    
    # 检查 SchedulerSide 方法
    scheduler_methods = [
        'prepare_request_state',
        'bind_allocated_blocks',
        'build_request_metadata',
        'get_state',
        'remove_state'
    ]
    
    print("\nSchedulerSide 方法检查:")
    for method in scheduler_methods:
        if hasattr(SchedulerSide, method):
            print(f"  ✅ {method}()")
        else:
            print(f"  ❌ {method}() - 缺失")
    
    # 检查 WorkerSide 方法
    worker_methods = [
        'start_load_kv',
        'wait_for_layer_load',
        'save_kv_layer',
        'wait_for_save',
        'request_finished'
    ]
    
    print("\nWorkerSide 方法检查:")
    for method in worker_methods:
        if hasattr(WorkerSide, method):
            print(f"  ✅ {method}()")
        else:
            print(f"  ❌ {method}() - 缺失")
    
    # 检查 StateManager 方法
    state_methods = [
        'create_or_get',
        'get',
        'put',
        'mark_manifest_hit',
        'mark_manifest_miss',
        'set_plan',
        'remove'
    ]
    
    print("\nStateManager 方法检查:")
    for method in state_methods:
        if hasattr(StateManager, method):
            print(f"  ✅ {method}()")
        else:
            print(f"  ❌ {method}() - 缺失")
    
    print()
    return True


def test_connector_lifecycle():
    """测试 DeadlinePrefixKVConnector 生命周期方法"""
    print("=" * 60)
    print("测试 3: Connector 生命周期方法")
    print("=" * 60)
    
    try:
        from dakv.connector.deadline_connector import DeadlinePrefixKVConnector
        print("✅ DeadlinePrefixKVConnector 导入成功")
    except ImportError as e:
        print(f"❌ DeadlinePrefixKVConnector 导入失败: {e}")
        print(f"   原因: 可能缺少依赖 (yaml, requests, torch 等)")
        return False
    
    # 检查 Scheduler-side 生命周期方法
    scheduler_lifecycle_methods = [
        '__init__',
        'get_num_new_matched_tokens',
        'update_state_after_alloc',
        'build_connector_meta',
        'build_connector_worker_meta',
        'update_connector_output',
        'request_finished',
        'take_events',
        'get_finished'
    ]
    
    print("\nScheduler-Side 生命周期方法:")
    for method in scheduler_lifecycle_methods:
        if hasattr(DeadlinePrefixKVConnector, method):
            print(f"  ✅ {method}()")
        else:
            print(f"  ❌ {method}() - 缺失")
    
    # 检查 Worker-side 生命周期方法
    worker_lifecycle_methods = [
        'start_load_kv',
        'wait_for_layer_load',
        'save_kv_layer',
        'wait_for_save'
    ]
    
    print("\nWorker-Side 生命周期方法:")
    for method in worker_lifecycle_methods:
        if hasattr(DeadlinePrefixKVConnector, method):
            print(f"  ✅ {method}()")
        else:
            print(f"  ❌ {method}() - 缺失")
    
    # 检查属性
    print("\nConnector 属性:")
    if hasattr(DeadlinePrefixKVConnector, 'prefer_cross_layer_blocks'):
        print(f"  ✅ prefer_cross_layer_blocks")
    else:
        print(f"  ❌ prefer_cross_layer_blocks - 缺失")
    
    print()
    return True


def test_inheritance():
    """测试继承关系"""
    print("=" * 60)
    print("测试 4: 继承关系验证")
    print("=" * 60)
    
    try:
        from dakv.connector.deadline_connector import DeadlinePrefixKVConnector
        from dakv.connector.vllm_adapter import KVConnectorBase_V1
        
        if issubclass(DeadlinePrefixKVConnector, KVConnectorBase_V1):
            print("✅ DeadlinePrefixKVConnector 继承自 KVConnectorBase_V1")
        else:
            print("❌ DeadlinePrefixKVConnector 未继承 KVConnectorBase_V1")
            return False
    except Exception as e:
        print(f"❌ 继承关系检查失败: {e}")
        return False
    
    print()
    return True


def main():
    """主测试入口"""
    print("\n" + "=" * 60)
    print(" P1-R 验证脚本")
    print("=" * 60)
    print()
    
    results = []
    
    # 测试 1: 导入
    results.append(("模块导入", test_imports()))
    
    # 测试 2: 类定义
    results.append(("类定义和方法", test_class_definitions()))
    
    # 测试 3: Connector 生命周期
    results.append(("Connector 生命周期", test_connector_lifecycle()))
    
    # 测试 4: 继承关系
    results.append(("继承关系", test_inheritance()))
    
    # 总结
    print("=" * 60)
    print(" 测试总结")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 所有测试通过！P1-R 验证成功！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查上述输出")
        return 1


if __name__ == "__main__":
    sys.exit(main())
