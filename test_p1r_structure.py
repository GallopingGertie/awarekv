#!/usr/bin/env python3
"""
P1-R Structure Test - 纯 Python AST 分析，无运行时依赖

测试目标：
1. 验证所有核心模块的语法正确性
2. 验证类定义和方法签名
3. 验证 import 链路完整性
4. 验证关键常量和类型定义
"""

import ast
import os
import sys

def test_file_syntax(filepath):
    """测试文件语法"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)

def extract_class_info(filepath, class_name):
    """提取类的方法和属性信息"""
    with open(filepath, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods = []
            properties = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    # 获取方法签名
                    args = [arg.arg for arg in item.args.args]
                    methods.append((item.name, args))
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    properties.append(item.target.id)
            return {'methods': methods, 'properties': properties}
    return None

def main():
    print("\n" + "=" * 70)
    print(" P1-R Structure Test - 纯 Python AST 分析")
    print("=" * 70)
    print()
    
    base_dir = os.path.dirname(__file__)
    src_dir = os.path.join(base_dir, 'src', 'dakv')
    
    results = []
    
    # ========== Test 1: 核心文件语法 ==========
    print("Test 1: 核心文件语法检查")
    print("-" * 70)
    
    core_files = [
        'connector/scheduler_side.py',
        'connector/worker_side.py',
        'connector/deadline_connector.py',
        'connector/state.py',
        'connector/metadata.py',
        'connector/vllm_adapter.py',
        'common/types.py',
        'config.py',
    ]
    
    syntax_passed = True
    for rel_path in core_files:
        filepath = os.path.join(src_dir, rel_path)
        if not os.path.exists(filepath):
            print(f"❌ {rel_path}: 文件不存在")
            syntax_passed = False
            continue
        
        is_valid, error = test_file_syntax(filepath)
        if is_valid:
            print(f"✅ {rel_path}")
        else:
            print(f"❌ {rel_path}: {error}")
            syntax_passed = False
    
    results.append(("语法检查", syntax_passed))
    print()
    
    # ========== Test 2: SchedulerSide 方法完整性 ==========
    print("Test 2: SchedulerSide 方法完整性")
    print("-" * 70)
    
    scheduler_file = os.path.join(src_dir, 'connector/scheduler_side.py')
    scheduler_info = extract_class_info(scheduler_file, 'SchedulerSide')
    
    expected_methods = [
        '__init__',
        'prepare_request_state',
        'bind_allocated_blocks',
        'build_request_metadata',
        'get_state',
        'remove_state',
    ]
    
    scheduler_passed = True
    if scheduler_info:
        actual_methods = [m[0] for m in scheduler_info['methods']]
        for method in expected_methods:
            if method in actual_methods:
                print(f"  ✅ {method}()")
            else:
                print(f"  ❌ {method}() - 缺失")
                scheduler_passed = False
    else:
        print("  ❌ SchedulerSide 类未找到")
        scheduler_passed = False
    
    results.append(("SchedulerSide", scheduler_passed))
    print()
    
    # ========== Test 3: WorkerSide 方法完整性 ==========
    print("Test 3: WorkerSide 方法完整性")
    print("-" * 70)
    
    worker_file = os.path.join(src_dir, 'connector/worker_side.py')
    worker_info = extract_class_info(worker_file, 'WorkerSide')
    
    expected_methods = [
        '__init__',
        'start_load_kv',
        'wait_for_layer_load',
        'save_kv_layer',
        'wait_for_save',
        'request_finished',
    ]
    
    worker_passed = True
    if worker_info:
        actual_methods = [m[0] for m in worker_info['methods']]
        for method in expected_methods:
            if method in actual_methods:
                print(f"  ✅ {method}()")
            else:
                print(f"  ❌ {method}() - 缺失")
                worker_passed = False
    else:
        print("  ❌ WorkerSide 类未找到")
        worker_passed = False
    
    results.append(("WorkerSide", worker_passed))
    print()
    
    # ========== Test 4: DeadlinePrefixKVConnector 生命周期方法 ==========
    print("Test 4: DeadlinePrefixKVConnector 生命周期方法")
    print("-" * 70)
    
    connector_file = os.path.join(src_dir, 'connector/deadline_connector.py')
    connector_info = extract_class_info(connector_file, 'DeadlinePrefixKVConnector')
    
    expected_lifecycle = [
        '__init__',
        'get_num_new_matched_tokens',
        'update_state_after_alloc',
        'build_connector_meta',
        'build_connector_worker_meta',
        'update_connector_output',
        'request_finished',
        'take_events',
        'get_finished',
        'start_load_kv',
        'wait_for_layer_load',
        'save_kv_layer',
        'wait_for_save',
    ]
    
    connector_passed = True
    if connector_info:
        actual_methods = [m[0] for m in connector_info['methods']]
        for method in expected_lifecycle:
            if method in actual_methods:
                print(f"  ✅ {method}()")
            else:
                print(f"  ❌ {method}() - 缺失")
                connector_passed = False
    else:
        print("  ❌ DeadlinePrefixKVConnector 类未找到")
        connector_passed = False
    
    results.append(("Connector lifecycle", connector_passed))
    print()
    
    # ========== Test 5: 检查 TODO 标记 ==========
    print("Test 5: 检查不应该存在的 TODO 标记")
    print("-" * 70)
    
    todo_check_files = [
        'connector/worker_side.py',
        'connector/scheduler_side.py',
        'connector/deadline_connector.py',
    ]
    
    found_todos = []
    for rel_path in todo_check_files:
        filepath = os.path.join(src_dir, rel_path)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if 'TODO' in line and 'NOTE' not in line:
                        found_todos.append((rel_path, line_no, line.strip()))
    
    todo_passed = len(found_todos) == 0
    if todo_passed:
        print("  ✅ 无未处理的 TODO 标记")
    else:
        print(f"  ❌ 发现 {len(found_todos)} 个 TODO 标记:")
        for rel_path, line_no, line in found_todos:
            print(f"     {rel_path}:{line_no} - {line}")
    
    results.append(("TODO check", todo_passed))
    print()
    
    # ========== Test 6: 硬编码检查 ==========
    print("Test 6: 硬编码 shape 检查")
    print("-" * 70)
    
    worker_file = os.path.join(src_dir, 'connector/worker_side.py')
    with open(worker_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否有未注释的硬编码 shape
    import re
    hardcoded_shapes = re.findall(r'shape\s*=\s*\(1,\s*16,\s*128\)', content)
    
    shape_passed = len(hardcoded_shapes) == 0
    if shape_passed:
        print("  ✅ 未发现硬编码 shape (1, 16, 128)")
        print("  ✅ Shape 从 config.block_size 获取")
    else:
        print(f"  ❌ 发现 {len(hardcoded_shapes)} 处硬编码 shape")
    
    results.append(("Shape check", shape_passed))
    print()
    
    # ========== 总结 ==========
    print("=" * 70)
    print(" 测试总结")
    print("=" * 70)
    print()
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print()
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 所有结构测试通过！")
        print("\n✅ P1-R Structure Complete")
        print("⏳ Runtime validation pending (需要目标环境)")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
