# P1-R 快速参考

## 📁 文件变更速查表

### 新增/重构的核心文件

| 文件 | 状态 | 说明 | 行数 |
|------|------|------|------|
| `scheduler_side.py` | 🔄 重构 | Scheduler-side 逻辑，集成 StateManager | ~350 |
| `worker_side.py` | 🔄 重构 | Worker-side 逻辑，改进错误处理 | ~450 |
| `deadline_connector.py` | ✅ 已有 | 主 Connector 类，集成 scheduler/worker | ~400 |
| `state.py` | ✅ 已有 | StateManager 状态管理 | ~220 |
| `metadata.py` | ✅ 已有 | Metadata 构建辅助函数 | ~200 |
| `types.py` | 🔧 修正 | WorkerLoadResult 字段定义 | ~200 |

## 🔄 生命周期方法速查

### Scheduler-Side 调用流程

```
1. get_num_new_matched_tokens()
   ↓ 调用 scheduler_side.prepare_request_state()
   ↓ 查询 manifest，生成 plan
   
2. update_state_after_alloc()
   ↓ 调用 scheduler_side.bind_allocated_blocks()
   ↓ 绑定 vLLM 分配的 block IDs
   
3. build_connector_meta()
   ↓ 调用 scheduler_side.build_request_metadata()
   ↓ 使用 build_metadata_from_state() 构建 metadata
   
4. request_finished()
   ↓ 清理 scheduler-side 状态
   ↓ 调用 worker_side.request_finished()
```

### Worker-Side 调用流程

```
1. start_load_kv()
   ↓ 调用 worker_side.start_load_kv()
   ↓ 加载 critical KV
   ↓ 返回 WorkerLoadResult
   
2. wait_for_layer_load() (每层调用一次)
   ↓ 调用 worker_side.wait_for_layer_load()
   ↓ 返回该层的 loaded KV tensor
   
3. save_kv_layer() (每层调用一次)
   ↓ 调用 worker_side.save_kv_layer()
   ↓ 提取并保存 prefix KV
   
4. wait_for_save()
   ↓ 调用 worker_side.wait_for_save()
   ↓ 等待保存完成
```

## 📊 关键数据流

### Request 状态转换

```
INIT
  ↓ manifest query
  ├─ hit → HIT_PLANNED
  │         ↓ start_load
  │         CRITICAL_LOADING
  │         ↓ load done
  │         CRITICAL_READY
  │         ↓ request done
  │         DONE
  │
  └─ miss → MISS (recompute)
            ↓
            DONE
```

### Metadata 构建流程

```
RequestTransferState (StateManager)
  ├─ prefix_key
  ├─ manifest (PrefixManifest)
  ├─ plan (TransferPlan)
  └─ allocated_block_ids
       ↓
  build_metadata_from_state()
       ↓
  DeadlineConnectorMetadata
  ├─ critical_object_id
  ├─ critical_codec
  ├─ need_refinement
  ├─ load_deadline_ms
  └─ allocated_block_ids
       ↓
  传递给 worker_side.start_load_kv()
```

## 🔧 常用代码片段

### 1. 创建 Connector 实例

```python
from dakv.connector.deadline_connector import DeadlinePrefixKVConnector

connector = DeadlinePrefixKVConnector(
    vllm_config=vllm_config,
    role="kv_both",  # or "kv_consumer" / "kv_producer"
    kv_cache_config=None
)
```

### 2. Scheduler-Side: 查询 Manifest

```python
# 在 connector.get_num_new_matched_tokens() 中调用
matched_tokens, is_external = connector.scheduler_side.prepare_request_state(
    request=request,
    num_computed_tokens=0
)
```

### 3. Worker-Side: 加载 KV

```python
# 在 connector.start_load_kv() 中调用
result = connector.worker_side.start_load_kv(
    forward_context=forward_context,
    metadata=metadata
)

if result.success:
    print(f"Loaded {result.loaded_tokens} tokens")
else:
    print(f"Load failed: {result.error_message}")
```

### 4. 构建 Metadata

```python
from dakv.connector.metadata import build_metadata_from_state

state = state_manager.get(request_id)
metadata = build_metadata_from_state(
    state=state,
    allocated_block_ids=[10, 11, 12, 13]
)
```

### 5. 创建 Load Result

```python
from dakv.connector.metadata import create_load_result

result = create_load_result(
    request_id="req_123",
    success=True,
    critical_done=True,
    loaded_tokens=100,
    loaded_blocks=10,
    critical_bytes=4096,
    critical_load_ms=15.5
)
```

## 🐛 调试技巧

### 1. 启用详细日志

```python
from dakv.logging import set_log_level
set_log_level("DEBUG")
```

### 2. 检查 Request 状态

```python
state = connector.state_manager.get(request_id)
print(f"Status: {state.status}")
print(f"Matched tokens: {state.matched_tokens}")
print(f"Plan: {state.plan.mode if state.plan else 'None'}")
```

### 3. 查看所有 Request 统计

```python
stats = connector.state_manager.get_stats()
print(stats)
# 输出: {'HIT_PLANNED': 5, 'MISS': 2, 'DONE': 3}
```

## 📝 验证命令

### 运行语法验证

```bash
python3 verify_p1r_syntax.py
```

### 运行完整测试（需要依赖）

```bash
pytest src/dakv/tests/test_connector_smoke.py -v
```

### 语法检查单个文件

```bash
python3 -m py_compile src/dakv/connector/scheduler_side.py
python3 -m py_compile src/dakv/connector/worker_side.py
```

## 📚 参考文档

- **完整交付报告**: `P1_R_DELIVERY_REPORT.md`
- **项目总结**: `PROJECT_SUMMARY.md`
- **快速入门**: `QUICKSTART.md`
- **架构文档**: `docs/ARCH.md`

## ✅ 验收清单

- [x] 所有文件语法正确
- [x] SchedulerSide 7 个方法完整
- [x] WorkerSide 9 个方法完整
- [x] DeadlinePrefixKVConnector 13 个生命周期方法
- [x] StateManager 9 个方法完整
- [x] metadata.py 4 个辅助函数
- [x] WorkerLoadResult 字段修正
- [x] 继承 KVConnectorBase_V1

---

**版本**: P1-R  
**日期**: 2026-03-26  
**状态**: ✅ 已完成
