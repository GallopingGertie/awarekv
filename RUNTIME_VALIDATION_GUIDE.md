# P1-R Runtime Validation Package

## 📋 验证目标

在完整依赖环境中验证 P1-R 实现的生命周期方法能被实际调用并执行。

## 🔧 环境要求

### 必需依赖
```bash
Python 3.9+
PyTorch 2.1.0
vLLM 0.6.3.post1
PyYAML 6.0.1
requests 2.31.0
```

### 推荐环境
- GPU: V100/A100 (可选，CPU 也能运行基础测试)
- RAM: 16GB+
- OS: Linux (Ubuntu 20.04/22.04)

## 🚀 快速开始

### Step 1: 安装依赖

```bash
# 方式 1: 使用 requirements-runtime.txt
pip install -r requirements-runtime.txt

# 方式 2: 手动安装核心依赖
pip install torch==2.1.0
pip install vllm==0.6.3.post1
pip install pyyaml==6.0.1 requests==2.31.0
```

### Step 2: 验证结构 (无依赖要求)

```bash
# 纯 Python AST 分析，验证代码结构
python3 test_p1r_structure.py
```

**预期输出**:
```
======================================================================
 P1-R Structure Test - 纯 Python AST 分析
======================================================================

Test 1: 核心文件语法检查
----------------------------------------------------------------------
✅ connector/scheduler_side.py
✅ connector/worker_side.py
✅ connector/deadline_connector.py
✅ connector/state.py
✅ connector/metadata.py
✅ connector/vllm_adapter.py
✅ common/types.py
✅ config.py

[... 更多检查 ...]

通过: 6/6

🎉 所有结构测试通过！

✅ P1-R Structure Complete
⏳ Runtime validation pending (需要目标环境)
```

### Step 3: 运行生命周期集成测试

```bash
# 完整生命周期测试 (需要 torch)
python3 test_lifecycle_minimal.py
```

**预期输出**:
```
======================================================================
 P1-R-RUN 最小生命周期集成测试
======================================================================

Step 1: Connector 实例化
----------------------------------------------------------------------
✅ Connector 实例化成功
   - Role: kv_both
   - Scheduler side: True
   - Worker side: True
   - State manager: True

Step 2: get_num_new_matched_tokens - 模拟 manifest miss
----------------------------------------------------------------------
✅ get_num_new_matched_tokens 调用成功
   - Request ID: test_req_001
   - Matched tokens: 0
   - Is external: False
   - 预期: 0 tokens (manifest miss)
   - State status: MISS

[... 更多步骤 ...]

======================================================================
 测试总结
======================================================================

✅ 所有生命周期方法调用成功！

已验证的生命周期方法:
  1. ✅ __init__() - Connector 实例化
  2. ✅ get_num_new_matched_tokens() - Scheduler 查询 manifest
  3. ✅ update_state_after_alloc() - 绑定 allocated blocks
  4. ✅ build_connector_meta() - 构建 metadata
  5. ✅ start_load_kv() - Worker 开始加载 (调用成功)
  6. ✅ wait_for_layer_load() - 等待 layer KV
  7. ✅ save_kv_layer() - 保存 layer KV
  8. ✅ wait_for_save() - 等待保存完成
  9. ✅ request_finished() - 请求完成清理
 10. ✅ get_finished() - 获取已完成请求

⚠️  已知限制:
  - start_load_kv 无真实数据服务支持 (预期失败)
  - paged KV inject/extract 未验证 (需要真实 vLLM)
  - slot mapping 未验证 (需要真实 vLLM)
```

### Step 4: (可选) 启动支撑服务进行端到端测试

```bash
# Terminal 1: 启动 manifest 服务
python3 scripts/run_manifest_service.py --port 8081

# Terminal 2: 启动 data server
python3 scripts/run_data_server.py --port 9001

# Terminal 3: 运行完整集成测试
python3 test_lifecycle_with_services.py
```

## 📊 验收 Checklist

### ✅ 必须验证 (P1-R 范围)

- [ ] **结构验证**: `test_p1r_structure.py` 全部通过
- [ ] **语法检查**: 所有核心文件无语法错误
- [ ] **方法完整性**: 13 个生命周期方法全部存在
- [ ] **TODO 标记**: 无未处理的 TODO (已明确标注为 P2/P3)
- [ ] **Shape 来源**: 无硬编码，从 config 获取
- [ ] **Connector 实例化**: 成功创建 connector 实例
- [ ] **Scheduler 方法调用**: prepare_request_state, build_request_metadata 成功调用
- [ ] **Worker 方法调用**: start_load_kv, save_kv_layer 成功调用
- [ ] **State 管理**: StateManager 正常工作
- [ ] **Metadata 构建**: build_metadata_from_state 成功

### ⚠️ 预期失败 (无真实服务)

- [ ] **Manifest query**: 无真实服务，预期返回 miss
- [ ] **KV load**: 无真实 data server，预期失败
- [ ] **KV save**: 无真实 saver，预期 deferred

### ❌ 不在 P1-R 范围 (P2/P3)

- [ ] Save flush to saver (明确标注为 P2)
- [ ] Refinement apply (明确标注为 P3)
- [ ] Paged KV inject/extract (P2)
- [ ] Slot mapping alignment (P2)
- [ ] 真实 vLLM 集成 (P2)

## 🔍 预期日志关键字

### 成功标志
```
✅ Connector 实例化成功
✅ get_num_new_matched_tokens 调用成功
✅ build_connector_meta 调用成功
✅ start_load_kv 调用完成
✅ save_kv_layer 调用成功
✅ request_finished 调用成功
```

### 预期失败 (正常)
```
❌ manifest miss (无真实服务)
❌ start_load_kv 调用完成 (预期失败) - Error: Connection refused
```

### 不应该出现
```
❌ TODO: ... (应该都被替换为 NOTE)
❌ Placeholder shape (应该从 config 获取)
❌ 语法错误
❌ 方法未找到
```

## 📝 验证报告模板

完成验证后，请填写以下报告：

```markdown
# P1-R Runtime Validation Report

## 环境信息
- Python version: 
- PyTorch version: 
- vLLM version: 
- GPU: 
- OS: 

## 测试结果

### 结构测试
- test_p1r_structure.py: [ ] PASS / [ ] FAIL
- 通过率: __/6

### 运行时测试
- test_lifecycle_minimal.py: [ ] PASS / [ ] FAIL
- 生命周期方法验证: __/10 成功调用

### 关键日志
```
[粘贴关键日志片段]
```

## 验证状态

- [ ] ✅ P1-R structure complete
- [ ] ✅ P1-R runtime validation complete
- [ ] ⏳ Ready to proceed to P2

## 遗留问题
[列出任何发现的问题]
```

## 🆘 故障排查

### 问题 1: ModuleNotFoundError: No module named 'torch'
```bash
pip install torch==2.1.0
```

### 问题 2: ModuleNotFoundError: No module named 'yaml'
```bash
pip install pyyaml==6.0.1
```

### 问题 3: ImportError: cannot import name 'KVConnectorBase_V1'
**原因**: vLLM 版本不匹配

**解决**:
```bash
pip install vllm==0.6.3.post1 --force-reinstall
```

### 问题 4: 测试报告 "start_load_kv failed"
**原因**: 这是预期行为，没有真实 data server

**验证**: 检查日志是否包含 "Error code: load_failed" 和 "Connection refused"

## 📚 相关文档

- `P1_R_DELIVERY_REPORT.md` - P1-R 初始交付报告
- `P1_R_RUN_VERIFICATION.md` - Runtime validation 状态报告
- `P1_R_QUICK_REFERENCE.md` - 快速参考
- `UPDATE_PROGRESS.md` - 项目进度
- `README.md` - 项目概览

---

**Package Version**: P1-R-RUN-FIX  
**Status**: Ready for runtime validation  
**Date**: 2026-03-26
