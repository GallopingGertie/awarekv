# DAKV v2.0 开发进度报告

> 基于 README_next_next_stage_dev_tasks_awarekv_v2.md 任务书

## P0-HOTFIX: 文档修正 ✅ 已完成

### 完成时间
2026-03-26

### 修改文件清单

1. **README.md**
   - 添加项目状态警告
   - 添加"项目状态"章节，明确区分已完成/进行中/计划中
   - 将 Quick Start 分为两部分：Minimal（可用）和 Integration（WIP）

2. **QUICKSTART.md**
   - 完全重写，移除"100%完成"的声明
   - 明确标注当前状态和各部分进度
   - Quick Start 分为 Minimal 和 Integration（WIP）
   - 添加详细的开发路线图
   - 添加"当前可以做到的"和"当前无法做到的"章节

3. **docs/EVAL.md**
   - 添加状态警告和进度说明
   - 区分"当前可用指标"和"计划中指标"
   - 标注所有 WIP 功能
   - 添加"当前限制"章节
   - 明确下一步行动计划

4. **PROJECT_SUMMARY.md**
   - 完全重写，移除"100%完成 ✅"的声明
   - 添加真实的完成度表格（总体55%）
   - 详细列出已完成/进行中/计划中的内容
   - 添加"当前可以做到的"和"当前无法做到的"章节
   - 更新验收标准达成情况（0/4）
   - 添加项目状态总结表

### 核心修正点

#### 1. 移除过度声明
- ❌ "项目已完整实现"
- ❌ "100% 完成"
- ❌ "可直接用于论文实验"
- ✅ 改为真实的进度状态

#### 2. 明确当前能力边界

**✅ 可以做到:**
- 启动 KV Store 和 Manifest Service
- 运行单元测试（codec, transport, planner）
- 测试 transport layer 的 put/get
- 验证 manifest query/put

**❌ 暂不能做到:**
- vLLM 真实集成（connector 需重写）
- Prefix 复用闭环（save/load 未打通）
- Paged KV 真实操作（使用硬编码）
- Refinement 后台补齐（只是框架）
- 论文级 TTFT/TPOT 测量

#### 3. 添加明确的路线图

所有文档现在都包含清晰的开发路线图：
- P0-HOTFIX ✅ 完成
- P1-R ~ P6 待完成

---

## P1-R: vLLM Connector 生命周期 🚧 即将开始

### 目标
让 `DeadlinePrefixKVConnector` 成为真正符合 vLLM KVConnectorBase_V1 的实现。

### 当前状态分析

#### 已完成的准备工作
- ✅ 数据结构定义完整（types.py）
- ✅ vLLM adapter 版本隔离层
- ✅ Scheduler side 框架
- ✅ Worker side 框架
- ✅ Save session 机制

#### 待修复的核心问题

1. **deadline_connector.py**
   - 问题：未显式继承 KVConnectorBase_V1
   - 问题：多个生命周期方法是空实现或返回占位值
   - 问题：使用单请求全局状态，不支持并发

2. **scheduler_side.py**
   - 问题：只返回 matched_tokens，未真正生成 metadata
   - 问题：plan 结果未存入 state
   - 问题：无法为 worker 构建完整 metadata

3. **worker_side.py**
   - 问题：使用 current_request_id 全局状态
   - 问题：save_kv_layer 直接调用 critical_channel.store()
   - 问题：load 使用硬编码 shape

4. **state.py / metadata.py**
   - 问题：功能单薄，缺少真正的状态机
   - 问题：metadata 字段不完整

### P1-R 详细任务清单

#### Step 1: 重写 deadline_connector.py

**目标**: 让主类真正成为 vLLM connector

**修改要点**:
```python
# 1. 显式继承
from dakv.connector.vllm_adapter import KVConnectorBase_V1

class DeadlinePrefixKVConnector(KVConnectorBase_V1):
    ...

# 2. 实现所有生命周期方法
def get_num_new_matched_tokens(...): ...
def update_state_after_alloc(...): ...
def build_connector_meta(...): ...
def update_connector_output(...): ...
def request_finished(...): ...
# 等等

# 3. Request-scoped 状态管理
self.request_states: Dict[str, RequestTransferState] = {}

# 4. 去掉所有 pass 和占位返回
```

#### Step 2: 增强 vllm_adapter.py

**新增功能**:
- `extract_allocated_block_ids()`
- `extract_slot_mapping()`
- `extract_attention_metadata()`
- `get_layer_kv_cache()`
- 统一导入 vLLM 类型

#### Step 3: 重构 state.py

**新增方法**:
- `create_or_get(request_id)`
- `mark_manifest_hit/miss()`
- `set_plan()`
- `set_allocated_blocks()`
- `mark_load_started/finished/failed()`
- `mark_save_started/finished/failed()`
- `gc_finished()`

#### Step 4: 扩展 metadata.py

**两类 metadata**:
- Scheduler → Worker metadata（下发）
- Worker → Scheduler metadata（回传）

**完整字段**:
- request_id, prefix_key, plan_mode
- object_ids, codecs, nbytes
- matched_tokens/blocks
- load_deadline_ms, need_refinement
- 等等

#### Step 5: 重构 scheduler_side.py

**核心修改**:
- `get_num_matched_tokens()` 返回值存入 state
- 新增 `build_request_metadata()`
- 新增 `on_worker_feedback()`
- Manifest hit 后完整填充 state

#### Step 6: 重构 worker_side.py

**核心修改**:
- 去掉单请求全局状态
- 改为 `request_id -> LoadTask/SaveSession`
- `start_load_kv()` 接收完整 metadata
- `save_kv_layer()` 写入 session，不直接 store

### 预期结果

完成 P1-R 后应该能够：
- ✅ Connector 可以在 vLLM 中被实例化
- ✅ Scheduler metadata 真实传递到 worker
- ✅ Worker feedback 真实回传到 scheduler
- ✅ 支持多请求并发
- ✅ 所有生命周期方法都有真实逻辑

### 验收标准

1. ✅ `isinstance(connector, KVConnectorBase_V1)` 返回 True
2. ✅ `build_connector_meta()` 返回非空 metadata list
3. ✅ `build_connector_worker_meta()` 返回真实 worker feedback
4. ✅ `get_finished()` 返回真实完成的 request_id 列表
5. ✅ 同时处理多个请求时状态不混乱

---

## P2-R ~ P6: 后续任务概览

### P2-R: Prefix 级 Save/Load
- 统一 save 路径为 prefix 级
- Object 格式规范化（header + payload）
- Save/load 闭环验证

### P3-R: Paged KV Apply/Extract
- 真实从 paged KV buffer 提取
- 真实注入到 paged KV buffer
- Roundtrip 测试

### P4-R: Refinement 后台补齐
- 异步 refinement 机制
- Apply 时机控制
- Timeout/drop 逻辑

### P5-R: 论文级 Benchmark
- TTFT/TPOT 测量
- 实验自动化
- 数据导出

### P6: 测试和文档
- 集成测试
- Smoke test
- 最终文档

---

## 当前项目目录结构

```
icnp/
├── src/dakv/
│   ├── common/
│   │   ├── types.py              ✅ 数据结构完整
│   │   ├── hashing.py            ✅ Prefix key 计算
│   │   └── ...
│   ├── codec/                     ✅ 完成
│   ├── store/                     ✅ 基础完成
│   ├── transport/                 ✅ 完成
│   ├── planner/                   ✅ 基础完成
│   ├── tier/                      ✅ 基础完成
│   ├── metrics/                   ✅ 框架完成
│   ├── connector/
│   │   ├── deadline_connector.py 🚧 需重写（P1-R）
│   │   ├── vllm_adapter.py       🚧 需增强（P1-R）
│   │   ├── scheduler_side.py     🚧 需重构（P1-R）
│   │   ├── worker_side.py        🚧 需重构（P1-R）
│   │   ├── state.py              🚧 需增强（P1-R）
│   │   ├── metadata.py           🚧 需扩展（P1-R）
│   │   ├── loader.py             ✅ 已更新
│   │   ├── saver.py              ✅ 已更新
│   │   ├── save_session.py       ✅ 已创建
│   │   ├── paged_kv_ops.py       ✅ 已创建
│   │   └── refine_manager.py     ✅ 已更新
│   ├── bench/                     🚧 30% 完成
│   └── tests/                     🚧 50% 完成
├── configs/                       ✅ 完成
├── scripts/                       ✅ 基础完成
├── docs/
│   ├── ARCH.md                    ✅ 完成
│   ├── PROTOCOL.md                ✅ 完成
│   └── EVAL.md                    ✅ 已更新
├── README.md                      ✅ 已更新
├── QUICKSTART.md                  ✅ 已更新
├── PROJECT_SUMMARY.md             ✅ 已更新
├── UPDATE_PROGRESS.md             ✅ 详细记录
└── requirements.txt               ✅ 完成
```

---

## 开发建议

### 对于 P1-R

1. **分步进行，不要一次性重写所有文件**
   - Step 1: deadline_connector.py 的继承和方法签名
   - Step 2: vllm_adapter.py 的辅助函数
   - Step 3: state.py 的状态机
   - Step 4: metadata.py 的字段扩展
   - Step 5: scheduler_side.py 的 metadata 生成
   - Step 6: worker_side.py 的 request-scoped 重构

2. **每完成一个 step，运行基础测试验证**
   - 确保导入不出错
   - 确保基本初始化成功
   - 确保类型检查通过

3. **保留当前可用的功能**
   - Codec、Transport、Planner 都已可用
   - 不要破坏已有的单元测试

4. **为 P2-R 做准备**
   - P1-R 完成后，worker_side 的 save session 机制应该就绪
   - 为 P2-R 的 prefix 级 flush 做好铺垫

### 关键原则

1. **真实优于完美**：先让系统真实运行，再优化
2. **逐步验证**：每一步都要有验证标准
3. **保持简单**：不要在 P1-R 引入复杂优化
4. **文档同步**：每完成一个阶段更新进度文档

---

## 总结

### P0-HOTFIX 成果
- ✅ 所有过度声明已修正
- ✅ 真实状态已明确标注
- ✅ 用户不会被误导

### 下一步
- 🎯 立即开始 P1-R
- 🎯 按照任务书的 6 个 step 执行
- 🎯 完成后提供核心代码片段和验证日志

---

**文档更新时间**: 2026-03-26  
**当前状态**: P0-HOTFIX ✅ 完成  
**下一步**: P1-R Step 1 - 重写 deadline_connector.py
