# awarekv v2.0 再下一阶段开发任务书

> 目标：把当前 `awarekv` 从“模块骨架较完整、文档/配置已收敛”的状态，推进到“**真实接入 vLLM KV Connector V1、真实完成 prefix 级 save/load、真实把远端 KV 注入 paged KV buffer、真实支持 refinement 后台补齐**”的可实验系统。
>
> 本任务书是基于 **v2.0 仓库现状** 重新制定的，不默认接受仓库里“已全部完成”的自述。请严格以本任务书的**完成标准**为准，而不是以 README/PROJECT_SUMMARY 里的口头声明为准。

---

## 0. 先给结论：v2.0 现在进行到哪一步

### 0.1 已完成/基本完成的部分

当前仓库里，下面这些部分可以认为已经有了可继续开发的基础：

- 依赖版本已经固定：`torch==2.1.0`、`vllm==0.6.3.post1` 等。
- 配置、README、QUICKSTART、启动脚本已经补了一版。
- `common/types.py` 比之前更完整，已经有 `TransferPlan / RequestTransferState / DeadlineConnectorMetadata` 等基础 dataclass。
- `planner / codec / transport / store / metrics / tests` 这些目录都已搭好，说明 vibe coding 至少把系统“该有哪些模块”搭出来了。
- `KVSaver`、`RemoteKVLoader`、`RefineManager`、`ManifestService` 等类已经存在，说明“prefix object + manifest + refine”这条设计路线仍然保持正确。

### 0.2 仍然没有完成的关键部分

当前 v2.0 **还不满足**我上一份任务书的核心要求。最关键的问题如下：

1. **主 connector 仍然不是真正的 vLLM KVConnectorBase_V1 实现。**
   - `src/dakv/connector/deadline_connector.py` 里的 `DeadlinePrefixKVConnector` 目前没有显式继承 `KVConnectorBase_V1`。
   - `update_state_after_alloc`、`update_connector_output`、`wait_for_save` 仍是空实现。
   - `build_connector_worker_meta` 返回 `{}`，`get_finished` 返回 `[]`，不构成真实的 scheduler/worker 生命周期。

2. **scheduler 侧只做了 manifest query + matched token 返回，没真正把 request-scoped metadata 下发给 worker。**
   - `scheduler_side.py` 现在主要是查 manifest、跑 planner、返回 `matched_tokens`。
   - 它并没有真正把 `object_id / codec / matched_blocks / need_refinement / mode` 组织成“下一步 engine step 要发给 worker 的 metadata”。

3. **worker 侧仍然没有真实操作 vLLM paged KV buffer。**
   - `worker_side.py` 里 `start_load_kv()` 只是记录 `request_id/object_id`。
   - `wait_for_layer_load()` 是“取回 critical blob → 用硬编码 `shape=(1,16,128)` 解码 → 返回 tensor”。
   - 这不是“写回 vLLM paged KV buffer”，也没有使用 `forward_context`、`attn_metadata`、`slot_mapping`。

4. **save 路径还是“每层直接 store 一个 critical blob”，没有统一成 prefix 级保存主路径。**
   - `worker_side.save_kv_layer()` 仍然是按 layer 直接调用 `critical_channel.store()`。
   - 仓库虽然有 `KVSaver.save_prefix_kv()`，但它还没有成为主 connector 的唯一保存路径。
   - 这样会导致“manifest/object id/prefix 级一致性”没有真正形成闭环。

5. **refinement 还是类存在，但主执行链未打通。**
   - `RefineManager` 和 `RemoteKVLoader.load_refinement()` 存在。
   - 但没有形成“critical 先服务 TTFT → decode 先开始 → refinement 后台补齐 → 超时可 drop”的真实运行机制。

6. **测试和 bench 仍然是 toy 级，不足以证明系统完成。**
   - `test_connector_smoke.py` 只测初始化和短前缀 miss。
   - `test_end_to_end_local.py` 只测 data server 的 put/get。
   - `scripts/run_bench.py` 还是只统计一个 `elapsed_ms`，没拆 TTFT/TPOT/P95，也没证明 prefix 命中后真实 load。

### 0.3 总体判断

**当前 v2.0 的真实阶段判断如下：**

- **P0：基本完成**（版本、配置、脚本、说明文档）
- **P1：只完成了“接口骨架补全的一部分”，没有完成真实 connector 生命周期**
- **P2：prefix save/load 主链路未完成**
- **P3：paged KV 注入/提取未完成**
- **P4：真实后台 refinement 未完成**
- **P5：论文级实验与指标未完成**

所以，**现在不能直接跳到“继续做实验和文档收尾”**。下一阶段必须先把 **真实 connector + 真实 KV apply/extract + 真实 prefix 级 save/load 闭环** 做完。

---

## 1. 本阶段总目标

本阶段只做一件事：

**把 awarekv v2.0 从“有系统组件的原型仓库”，推进成“真正能在 vLLM 中完成一次 prefix save，再在下一次请求中完成 remote prefix load + critical/refinement 分级传输 + paged KV apply 的工作系统”。**

达到这个目标后，后面的实验和论文图表才有意义。

---

## 2. 开发优先级（必须按顺序执行）

### P0-HOTFIX：先修正文档中的“已完成全部”的错误表述
### P1-R：完成真实的 vLLM connector 生命周期
### P2-R：完成 prefix 级 save/load 主路径
### P3-R：完成真实的 paged KV 提取与注入
### P4-R：完成真实的 refinement 后台补齐机制
### P5-R：完成论文级 benchmark/metrics
### P6：补足测试、脚本和最终文档

**注意：P2/P3 没通过前，不要开始做更复杂 codec，不要开始搞 RL planner，不要做多节点扩展。**

---

## 3. P0-HOTFIX：先修正文档口径，避免误导后续开发

## 3.1 目标

先把仓库内“项目已完整实现”“可直接用于论文实验”等过度声明改掉，避免 vibe coding 在错误前提上继续往后堆代码。

## 3.2 必改文件

- `README.md`
- `QUICKSTART.md`
- `PROJECT_SUMMARY.md`
- `docs/EVAL.md`

## 3.3 修改要求

### A. 把“已经完整实现”的描述改成当前真实状态

统一改为类似口径：

- v2.0 已完成：版本冻结、模块骨架、planner/codec/store/transport 基础实现。
- v2.0 未完成：真实 vLLM paged KV apply/extract、真实 prefix 级 save/load 闭环、真实 refinement 后台补齐、论文级实验。

### B. QUICKSTART 改成两档

- **Quickstart-Minimal**：仅启动 manifest/data server，并跑 codec/planner/transport 的基础测试。
- **Quickstart-Integration（WIP）**：标注为进行中，列出完成真实 connector 后再执行。

### C. EVAL 文档改成“计划中指标”，而不是“已经可用指标”

例如：

- 目前可用：manifest hit、raw transport put/get。
- 待实现：真实 TTFT/TPOT/plan_mode/fallback 统计。

## 3.4 完成标准

- 仓库文档不再宣称“全部完成”。
- 所有人看到 README 后，不会误以为系统已经真实接入 vLLM paged KV。

---

## 4. P1-R：完成真实的 vLLM connector 生命周期（最高优先级）

## 4.1 目标

让 `DeadlinePrefixKVConnector` 成为一个**真正符合 vLLM KV Connector V1 生命周期**的实现，而不是一个“长得像 connector 的自定义类”。

## 4.2 必改文件

- `src/dakv/connector/deadline_connector.py`
- `src/dakv/connector/vllm_adapter.py`
- `src/dakv/connector/state.py`
- `src/dakv/connector/metadata.py`
- `src/dakv/connector/scheduler_side.py`
- `src/dakv/common/types.py`
- `src/dakv/tests/test_connector_smoke.py`
- 如有需要新增：`src/dakv/tests/test_connector_lifecycle.py`

## 4.3 逐文件修改要求

### 4.3.1 `src/dakv/connector/deadline_connector.py`

这是本阶段最重要的文件，必须重写主类，不是只补几个 `pass`。

#### 必须完成

1. **显式继承 `KVConnectorBase_V1`**
   - 不要再只是普通 Python 类。
   - 实际继承路径通过 `vllm_adapter.py` 统一做兼容导入。

2. **实现完整的 scheduler-side 方法**
   - `get_num_new_matched_tokens`
   - `update_state_after_alloc`
   - `build_connector_meta`
   - `update_connector_output`
   - `request_finished`
   - `take_events`

3. **实现完整的 worker-side 方法**
   - `start_load_kv`
   - `wait_for_layer_load`
   - `save_kv_layer`
   - `wait_for_save`
   - `get_finished`
   - `build_connector_worker_meta`

4. **去掉所有空实现/占位返回值**
   - 不允许再有 `pass`
   - 不允许 `build_connector_worker_meta` 只返回 `{}`
   - 不允许 `get_finished` 恒返回空列表

5. **按 request 维护状态，不允许只存 `current_request_id/current_object_id` 这种单请求全局变量**
   - 要支持多请求并发。

#### 结构建议

主类内部显式持有：

- `StateManager`
- `SchedulerSide`
- `WorkerSide`
- `pending_events`
- `completed_request_ids`
- `save_futures / load_futures` 的 request 索引

### 4.3.2 `src/dakv/connector/vllm_adapter.py`

当前这个文件太薄，只做了 request_id 和 prompt_token_ids 提取，不够。

#### 必须补齐的内容

1. 统一导入/封装这些 vLLM 类型
   - `KVConnectorBase_V1`
   - `KVConnectorMetadata`
   - `KVConnectorWorkerMetadata`
   - `ForwardContext`
   - 常用 `AttentionMetadata` 类型

2. 提供兼容 helper
   - `extract_request_id(request)`
   - `extract_prompt_tokens(request)`
   - `extract_allocated_block_ids(blocks)`
   - `extract_attn_metadata(forward_context, layer_name)`
   - `extract_slot_mapping(attn_metadata)`
   - `get_layer_kv_cache(forward_context, layer_name)`
   - `is_store_request(...) / is_load_request(...)`

3. 不要在主 connector 文件里直接 scattered import vLLM 内部类
   - 统一在 adapter 层做版本隔离。

### 4.3.3 `src/dakv/connector/state.py`

把当前简单的 `request_id -> RequestTransferState` 字典，升级成真正的生命周期状态管理器。

#### 必须新增/补齐

- `create_or_get(request_id)`
- `mark_manifest_hit/miss`
- `set_plan(...)`
- `set_allocated_blocks(...)`
- `set_connector_metadata(...)`
- `set_load_task(...)`
- `set_save_task(...)`
- `mark_load_started / mark_load_finished / mark_load_failed`
- `mark_save_started / mark_save_finished / mark_save_failed`
- `mark_refine_started / mark_refine_finished / mark_refine_dropped`
- `mark_done / mark_recompute`
- `gc_finished()`

### 4.3.4 `src/dakv/connector/metadata.py`

当前 `ConnectorMetadata` 只有几个字段，不够 worker 真实 load/save 用。

#### 必须扩展成两类 metadata

1. **scheduler -> worker metadata**
   - `request_id`
   - `prefix_key`
   - `matched_tokens`
   - `matched_blocks`
   - `plan_mode`
   - `critical_object_id`
   - `critical_codec`
   - `critical_nbytes`
   - `refinement_object_id`
   - `refinement_codec`
   - `refinement_nbytes`
   - `need_remote_load`
   - `need_refinement`
   - `load_deadline_ms`
   - `num_layers`
   - `block_size`
   - `cache_dtype`

2. **worker -> scheduler metadata**
   - `request_id`
   - `critical_load_started`
   - `critical_load_done`
   - `critical_load_failed`
   - `save_started`
   - `save_done`
   - `save_failed`
   - `refine_started`
   - `refine_done`
   - `refine_dropped`
   - `error_message`
   - `critical_bytes`
   - `refine_bytes`
   - `critical_load_ms`
   - `refine_load_ms`

### 4.3.5 `src/dakv/connector/scheduler_side.py`

当前这个文件只做“查 manifest → planner → 返回 matched_tokens”，不够。

#### 必须修改成

1. `get_num_matched_tokens()` 保持 side-effect minimal，但要返回足够信息供 connector 建立 request state。
   - 不能只把 plan 丢掉。

2. 新增方法：
   - `probe_prefix(request, num_computed_tokens)`
   - `build_request_metadata(request_id, state)`
   - `on_worker_feedback(worker_meta)`

3. 进入 manifest hit 后，要把这些内容塞进 state
   - `prefix_key`
   - `manifest`
   - `plan`
   - `matched_blocks`
   - `critical/refinement object ids`
   - `need_refinement`

4. `build_connector_meta()` 需要能够遍历本 step 的 scheduled requests，把命中的请求组装成 metadata 列表
   - 不允许只在 `get_num_new_matched_tokens()` 里临时返回一个数字然后结束。

### 4.3.6 `src/dakv/common/types.py`

保留现有 dataclass，但必须进一步对齐真实使用路径。

#### 必须新增/扩展字段

1. `RequestTransferState`
   - `manifest`
   - `allocated_block_ids`
   - `connector_metadata`
   - `worker_feedback`
   - `load_task`
   - `save_task`
   - `save_session`
   - `finished_sent_to_scheduler`

2. `WorkerLoadTask`
   - 当前只有 layer_name / futures，不够。
   - 扩展为：
     - `object_id`
     - `codec_name`
     - `matched_blocks`
     - `layer_futures`
     - `refine_futures`
     - `critical_apply_done`
     - `refine_apply_done`
     - `error`

3. 新增 `SaveSession`
   - `request_id`
   - `prefix_key`
   - `matched_tokens`
   - `matched_blocks`
   - `num_layers`
   - `layer_buffers`
   - `critical_object_id`
   - `refinement_object_id`
   - `manifest_put_done`

## 4.4 完成标准

满足以下任一项之前，不算完成 P1-R：

- `DeadlinePrefixKVConnector` 能在真实 `vllm==0.6.3.post1` 环境下被成功实例化，并且不是“普通类伪装 connector”。
- 所有 connector 生命周期方法都存在真实逻辑，不再有占位实现。
- `build_connector_meta()` 能为 scheduler step 生成真实 metadata。
- `build_connector_worker_meta()` 能把 worker 侧状态回传给 scheduler。

---

## 5. P2-R：完成 prefix 级 save/load 主路径

## 5.1 目标

把当前“layer 级零散 store / fake load”改成：

**prefix_key -> critical_object(+refine_object) -> manifest -> 下次请求命中并复用**

这是系统的真正主闭环。

## 5.2 必改文件

- `src/dakv/connector/worker_side.py`
- `src/dakv/connector/saver.py`
- `src/dakv/connector/loader.py`
- `src/dakv/store/manifest_service.py`
- `src/dakv/store/local_disk_backend.py`
- `src/dakv/store/object_store.py`
- `src/dakv/common/types.py`
- `src/dakv/tests/test_end_to_end_local.py`
- 新增建议：`src/dakv/tests/test_prefix_save_load_cycle.py`

## 5.3 逐文件修改要求

### 5.3.1 `src/dakv/connector/worker_side.py`

#### 必须修改

1. 去掉单请求全局状态
   - 删掉或废弃 `current_request_id/current_object_id` 作为主状态。
   - 换成 `request_id -> LoadTask/SaveSession`。

2. `start_load_kv()` 改成真正启动异步 load
   - 输入来自 metadata，而不是只靠 kwargs 随便传。
   - 读取 `critical_object_id / refinement_object_id / codec / matched_blocks / num_layers`。
   - 为每一层创建 load future，而不是只记一个 object_id。

3. `save_kv_layer()` 改成“写入 save session”，不要再每层直接 `critical_channel.store()`。
   - 当前层从 paged KV 中提取出的 KV 先写入内存 session。
   - 所有层都收齐后，由 `wait_for_save()` 统一触发 prefix 级持久化。

### 5.3.2 `src/dakv/connector/saver.py`

#### 必须重构

1. 把 `KVSaver.save_prefix_kv()` 变成主路径，不是备用工具类。
2. 支持 **prefix 级对象格式**，不要只把各层 `blob.data` 生拼接。

#### 对象格式要求

至少包含：

- object header（建议 JSON/MsgPack）
  - `version`
  - `prefix_key`
  - `matched_tokens`
  - `matched_blocks`
  - `num_layers`
  - `codec_name`
  - 每层 shape / dtype / offset / nbytes
- payload
  - 按层顺序拼接的编码后字节流

#### manifest 写入要求

manifest put 必须发生在：

- critical object 成功写入之后
- refinement object（若启用）也处理完成之后

manifest 中的 object id / codec / nbytes 必须与真正写入对象一致。

### 5.3.3 `src/dakv/connector/loader.py`

#### 必须重构

1. 读取 prefix 级对象，而不是假设单层固定 shape。
2. 能解析 object header，恢复：
   - 每层 shape
   - 每层 offset
   - 每层 dtype
   - `matched_blocks`
   - `num_layers`
3. 提供接口：
   - `load_critical_object(...) -> PerLayerDecodedKV`
   - `load_refinement_object(...) -> PerLayerDecodedKV`

### 5.3.4 `src/dakv/store/manifest_service.py`

#### 必须补齐

1. 明确 manifest 的“覆盖写”语义。
2. 增加最小一致性检查：
   - `critical_object_id` 不能为空
   - `matched_tokens > 0`
   - `num_layers > 0`
3. manifest query 返回必须包含 worker 真正需要的字段，不要只返回 hit/miss。

### 5.3.5 `src/dakv/store/local_disk_backend.py`

#### 必须补齐

1. 支持 tier 目录清晰分离
   - `critical/`
   - `refinement/`
2. `put/get/delete/exists/size` 的 tier 语义必须一致。
3. 增加对象 header 读写 helper，方便 debug。

## 5.4 完成标准

满足以下条件才算 P2-R 完成：

- 第一次请求结束后，磁盘上可看到 prefix 级 critical object。
- manifest 中可查到该 prefix 的 object id 和元数据。
- 第二次共享同 prefix 的请求能命中 manifest 并拿到同一个 object id。
- load 路径能解析 object header，不再使用硬编码 shape。

---

## 6. P3-R：完成真实的 paged KV 提取与注入

## 6.1 目标

这是整个系统里最关键、最不能再“假装完成”的部分。

必须做到：

- 从 vLLM paged KV buffer 中，按请求实际 `slot_mapping` 提取 prefix KV。
- 再把远端取回的 KV，按 `slot_mapping` 正确写回 paged KV buffer。

**没有这一层，就不能说“真实接入 vLLM”。**

## 6.2 必改文件

- `src/dakv/connector/worker_side.py`
- `src/dakv/connector/vllm_adapter.py`
- `src/dakv/connector/loader.py`
- `src/dakv/connector/saver.py`
- 新增建议：
  - `src/dakv/connector/kv_apply.py`
  - `src/dakv/connector/kv_extract.py`
- 测试文件：
  - 新增 `src/dakv/tests/test_kv_apply_extract_roundtrip.py`
  - 新增 `src/dakv/tests/test_vllm_paged_kv_mock.py`

## 6.3 逐文件修改要求

### 6.3.1 `src/dakv/connector/vllm_adapter.py`

#### 必须新增

- `extract_slot_mapping(attn_metadata)`
- `extract_block_size(attn_metadata, default_block_size)`
- `extract_layer_kv_tensor(layer)`
- `is_triton_attention_metadata(...)`
- `is_mla_metadata(...)`
- `normalize_layer_name(layer_name)`

### 6.3.2 新增 `src/dakv/connector/kv_extract.py`

#### 功能

给定：

- `kv_layer`
- `attn_metadata`
- `slot_mapping`
- `matched_tokens / matched_blocks`

从 paged KV buffer 中提取本请求 prefix 对应的 KV 切片。

#### 要求

参考 vLLM example connector 的处理方式，至少支持：

- Triton attention metadata 路径
- 通用 paged layout 路径

### 6.3.3 新增 `src/dakv/connector/kv_apply.py`

#### 功能

给定：

- 目标 paged KV layer
- 从远端加载回来的 source KV
- 当前请求的 slot_mapping
- attn_metadata

把 source KV 正确注入目标 paged KV buffer。

#### 要求

- 不允许返回一个 tensor 交给外部“自己处理”。
- 必须在这里完成真正的内存写入。
- 支持 inplace apply。

### 6.3.4 `src/dakv/connector/worker_side.py`

#### 必须重构

1. `start_load_kv()`
   - 利用 `forward_context.no_compile_layers` 或等价接口，拿到每层 paged KV layer。
   - 创建 per-layer 异步 load + apply future。

2. `wait_for_layer_load(layer_name)`
   - 等待该层 apply future 完成。
   - 成功后不一定需要返回 tensor，但必须保证该层 paged KV 已可被 attention 层使用。

3. `save_kv_layer(layer_name, kv_layer, attn_metadata, **kwargs)`
   - 用 `kv_extract.py` 从 paged layer 中提取本请求 prefix 对应的 KV。
   - 把结果写入 save session。

### 6.3.5 测试要求

新增 roundtrip 测试：

- 构造假的 paged KV layer。
- 用 `kv_extract` 提取一段 prefix KV。
- 清空目标位置。
- 用 `kv_apply` 写回。
- 比较前后是否一致。

## 6.4 完成标准

以下全部满足才算 P3-R 完成：

- load 路径不再使用硬编码 `shape=(1,16,128)`。
- `wait_for_layer_load()` 的完成意味着 paged KV 已被真实写入。
- `save_kv_layer()` 的提取数据确实来自当前 request 的 slot mapping，而不是整层盲存。
- roundtrip 测试通过。

---

## 7. P4-R：完成真实的 refinement 后台补齐机制

## 7.1 目标

让“critical 先服务 TTFT、refinement 后台补齐”的机制成为真实运行链，而不是类和函数名存在。

## 7.2 必改文件

- `src/dakv/connector/refine_manager.py`
- `src/dakv/connector/worker_side.py`
- `src/dakv/connector/loader.py`
- `src/dakv/connector/deadline_connector.py`
- `src/dakv/common/types.py`
- `src/dakv/metrics/__init__.py`
- 新增建议：`src/dakv/tests/test_refinement_flow.py`

## 7.3 逐文件修改要求

### 7.3.1 `src/dakv/connector/refine_manager.py`

从简单 `pending_refinements` 字典升级成 request-scoped manager。

#### 必须支持

- `start_refine(request_id, metadata)`
- `register_refine_future(request_id, layer_name, future)`
- `is_refine_ready(request_id, layer_name)`
- `pop_ready_refine(request_id, layer_name)`
- `drop_refine(request_id, reason)`
- `mark_timeout(request_id)`
- `clear_request(request_id)`

### 7.3.2 `src/dakv/connector/worker_side.py`

#### 必须实现真正模式分流

根据 `plan.mode`：

- `FULL_FP16`
  - 直接完整加载 FP16 critical（若你定义 FULL_FP16 为只传完整对象）。
- `CRITICAL_INT8_ONLY`
  - 只加载 int8 critical，不创建 refinement future。
- `CRITICAL_INT8_THEN_FP16`
  - critical 先 load/apply。
  - refinement 在后台异步 fetch + decode + apply。
- `RECOMPUTE`
  - 不触发远端加载，直接 fallback。

#### refinement apply 要求

- 可在 layer safe point apply。
- 若 refinement 超时，则 drop，但 critical 结果继续服务。
- 所有 drop/timeout 都必须打指标。

### 7.3.3 `src/dakv/metrics/__init__.py`

新增/补齐这些统计：

- `dakv_refine_started_total`
- `dakv_refine_done_total`
- `dakv_refine_drop_total`
- `dakv_refine_timeout_total`
- `dakv_plan_mode_total{mode=...}`
- request 级：
  - `critical_apply_ms`
  - `refine_apply_ms`
  - `degraded`
  - `fallback_reason`

## 7.4 完成标准

- 日志中能看到 `plan_mode=CRITICAL_INT8_THEN_FP16` 的请求先完成 critical，再异步完成 refinement。
- 超时场景下，refinement 可 drop，但请求仍完成。
- request metrics 中能区分：critical-only、critical+refine、recompute。

---

## 8. P5-R：完成论文级 benchmark 和指标采集

## 8.1 目标

把现在的 toy bench 升级成能支持论文实验的测量框架。

## 8.2 必改文件

- `scripts/run_bench.py`
- `src/dakv/bench/client.py`（若不存在就新建）
- `src/dakv/bench/longbench_runner.py`
- `src/dakv/bench/mmlu_runner.py`
- `src/dakv/metrics/__init__.py`
- `docs/EVAL.md`
- 新增建议：
  - `src/dakv/bench/report.py`
  - `src/dakv/bench/workloads.py`

## 8.3 逐文件修改要求

### 8.3.1 `scripts/run_bench.py`

当前只能测整个请求 `elapsed_ms`，远远不够。

#### 必须升级为

输出每条请求的：

- `ttft_ms`
- `tpot_ms` 或 `itl_ms`
- `total_latency_ms`
- `prefix_hit`
- `matched_tokens`
- `plan_mode`
- `critical_bytes`
- `refine_bytes`
- `fallback`
- `fallback_reason`

#### 建议实现方式

- 优先使用 streaming 接口测 first token 时间。
- 若 vLLM OpenAI 兼容接口不方便，至少在服务端日志/metrics 中补 request id 级时间戳，并由 bench parser 汇总。

### 8.3.2 `src/dakv/bench/longbench_runner.py`

当前只是 shared-prefix toy workload 的循环包装。

#### 必须修改

- 把“共享长前缀” workload 保留，但显式命名为 `shared_prefix_synthetic`。
- 新增至少一个“真实长上下文样本集加载器”接口。
- 允许外部提供 JSONL/文本文件作为 workload。

### 8.3.3 `src/dakv/bench/mmlu_runner.py`

当前是 10 条硬编码题目，不是真实 benchmark。

#### 必须修改

- 改成从本地数据文件加载。
- 支持 `--dataset-path`。
- 输出 accuracy 和 latency 两类指标。

### 8.3.4 `docs/EVAL.md`

改成真正的实验计划文档，至少包含：

1. **网络 sweep**
   - 1Gbps/20ms
   - 100Mbps/50ms/1% loss
   - 可扩展更多 profile

2. **模式对比**
   - `FULL_FP16`
   - `CRITICAL_INT8_ONLY`
   - `CRITICAL_INT8_THEN_FP16`
   - `RECOMPUTE`

3. **主指标**
   - TTFT p50/p95
   - TPOT/ITL
   - bytes transferred
   - fallback rate
   - manifest hit rate
   - plan mode distribution

4. **质量实验**
   - full fp16 vs int8-only vs int8+fp16

## 8.4 完成标准

- `run_bench.py` 输出 CSV/JSON，字段完整。
- 能跑一组共享前缀 workload，并得到 second request 与 first request 的 TTFT 差异。
- 能统计不同 `plan_mode` 的比例和效果。

---

## 9. P6：补足测试、脚本和最终文档

## 9.1 必改文件

- `src/dakv/tests/test_connector_smoke.py`
- `src/dakv/tests/test_end_to_end_local.py`
- 新增：
  - `src/dakv/tests/test_connector_lifecycle.py`
  - `src/dakv/tests/test_prefix_save_load_cycle.py`
  - `src/dakv/tests/test_kv_apply_extract_roundtrip.py`
  - `src/dakv/tests/test_refinement_flow.py`
- `scripts/smoke_test.sh`
- `QUICKSTART.md`
- `README.md`

## 9.2 测试要求

### A. `test_connector_smoke.py`

不再只测初始化。

至少测：

- connector 能构建 metadata
- state manager 能记录 request state
- worker metadata 能回传

### B. `test_end_to_end_local.py`

升级成真正的 prefix save/load 周期测试：

1. 模拟第一次请求触发 save
2. manifest put 成功
3. 第二次相同 prefix 请求 query hit
4. load path 拿到 object id
5. loader 成功解析 prefix object

### C. `scripts/smoke_test.sh`

升级为两段式：

- phase 1：只测 manifest/data server 和基础 transport
- phase 2：在真实 vLLM 下跑两次共享 prefix 请求，并检查日志中：
  - 第二次请求 hit manifest
  - plan_mode 不是纯 miss
  - 触发 remote critical load

## 9.3 完成标准

- 本地跑测试时，不再只是 codec/transport 单元测试通过。
- 至少有一条“真实 prefix 命中 → load → apply”的 automated smoke path。

---

## 10. 开发顺序建议（给 vibe coding 的执行顺序）

下面是最推荐的实际执行顺序，不要乱改：

### Step 1：先做 P0-HOTFIX

先把文档里“已完成全部”的说法改掉。

### Step 2：重写 `deadline_connector.py`

目标：让它成为真的 connector 主类。

本步只先完成：

- 继承 `KVConnectorBase_V1`
- 所有生命周期方法都有真实逻辑框架
- state manager 接进去
- metadata builder 接进去

### Step 3：补 `vllm_adapter.py + scheduler_side.py + metadata.py + state.py`

目标：把 scheduler request state / metadata 链路打通。

### Step 4：重构 `worker_side.py`

目标：去掉单请求全局状态，改成 request-scoped load/save task。

### Step 5：重构 `saver.py + loader.py`

目标：建立 prefix 级 object 格式和 manifest 闭环。

### Step 6：新增 `kv_extract.py + kv_apply.py`

目标：完成真实 paged KV 提取与写回。

### Step 7：接入 refinement manager

目标：把 `CRITICAL_INT8_THEN_FP16` 从概念变成真实后台机制。

### Step 8：升级 bench 和 metrics

目标：得到真实 TTFT/TPOT/plan_mode/fallback 数据。

### Step 9：补齐 tests / smoke / docs

目标：让系统进入“可以继续做论文实验”的状态。

---

## 11. 本阶段严格禁止做的事

为了避免再次跑偏，下面这些在本阶段都不要做：

- 不要先做 INT4 / 学习型压缩。
- 不要先做 RL planner。
- 不要先做多节点 KV store。
- 不要先做复杂 GPU kernel 优化。
- 不要先做漂亮 dashboard。

**先把真实 connector 闭环做通，再谈优化。**

---

## 12. 本阶段最终验收标准

只有下面 6 条都满足，才算本阶段完成：

1. `DeadlinePrefixKVConnector` 是真实的 `KVConnectorBase_V1` 子类。
2. 第二次共享前缀请求能命中 manifest，并通过 metadata 把 object 信息传到 worker。
3. worker 能把 remote critical KV 真实写回 paged KV buffer，而不是返回一个临时 tensor 了事。
4. 第一次请求结束后能通过 prefix 级 object + manifest 完成保存；第二次请求能真正复用。
5. `CRITICAL_INT8_THEN_FP16` 模式下，refinement 能后台补齐或超时 drop。
6. bench 能输出 TTFT/TPOT/plan_mode/fallback/bytes 等核心指标。

---

## 13. 交付给我的中期检查材料（vibe coding 完成后必须一起给）

下一个版本交付时，不要只给一句“已完成 P2/P3”。

必须同时给：

1. **修改文件清单**
   - 哪些文件改了
   - 哪些文件新增了
   - 每个文件改了什么

2. **核心代码片段**
   - `deadline_connector.py`
   - `worker_side.py`
   - `saver.py`
   - `loader.py`
   - `kv_apply.py`
   - `kv_extract.py`

3. **一条真实运行日志**
   至少要能看出：
   - request 1 save 成功
   - manifest put 成功
   - request 2 manifest hit
   - worker start load
   - per-layer apply 完成
   - 若启用 refinement，则 refine start/done 或 drop

4. **一份 bench 输出样例**
   至少包含：
   - `ttft_ms`
   - `plan_mode`
   - `prefix_hit`
   - `critical_bytes`
   - `fallback`

这样我才能继续帮你做下一轮验收和再下一阶段任务规划。

---

## 14. 一句话总结

**awarekv v2.0 现在还没有进入“可以直接做论文实验”的阶段；下一阶段必须先把“真实 vLLM connector 生命周期 + 真实 paged KV apply/extract + 真实 prefix 级 save/load 闭环”做成。**

