# awarekv 下一阶段开发任务书

> 目标：把当前 `awarekv` 从“方向正确的原型骨架”推进到“真正接入 vLLM KV Connector V1、能完成真实远端 prefix KV 保存/加载/渐进补齐、并能支撑论文实验”的系统。
>
> 本任务书默认遵循当前路线 A：**面向远端/冷层 prefix KV 的 deadline-aware 分级传输协议**。
>
> 本阶段不追求继续扩展新 idea，优先把主链路做实：
>
> 1. 真正对齐 vLLM connector 生命周期。
> 2. 真正把远端 KV 写回 vLLM paged KV buffer。
> 3. 真正把 prefix 级保存、manifest、复用闭环打通。
> 4. 真正把 refinement 做成“critical 先服务 TTFT、refinement 后台补齐”的机制。
> 5. 真正把评测指标做成论文级而不是 toy 级。

---

## 0. 当前代码状态与本阶段总判断

当前仓库已经有较完整的模块骨架：

- `src/dakv/connector/`：scheduler / worker / saver / adapter
- `src/dakv/planner/`：deadline planner
- `src/dakv/codec/`：fp16 / int8 编解码
- `src/dakv/store/`：manifest / object store
- `src/dakv/transport/`：critical / refine channel
- `src/dakv/tier/`：host cache
- `src/dakv/metrics/`：指标记录
- `scripts/`、`configs/`、`docs/`：运行与实验脚本

但现在缺的不是“模块名”，而是**真实执行闭环**。

当前最关键的问题有四类：

1. **Connector 生命周期没有真正按 vLLM KVConnector V1 接完整。**
2. **Worker 侧没有真正把远端 KV 注入到 vLLM paged KV buffer。**
3. **Save 路径没有统一成 prefix 级 object + manifest 的唯一主路径。**
4. **Refinement 还没有成为真实的后台异步补齐机制。**

因此，本阶段开发严格按“先主链路、后优化”的优先级推进。

---

## 1. 本阶段开发总目标

完成以下最小可用系统：

- vLLM 启动时加载自定义 `DeadlinePrefixKVConnector`
- 对共享 prefix 请求：
  - scheduler 查询 manifest
  - planner 生成 `FULL_FP16 / CRITICAL_INT8_ONLY / CRITICAL_INT8_THEN_FP16 / RECOMPUTE`
  - scheduler 通过 connector metadata 把计划传给 worker
  - worker 异步加载 critical KV
  - critical KV 按 layer / slot mapping 正确写入 paged KV buffer
  - decode 可直接复用这些 KV 开始生成
  - refinement 在后台补齐并 overwrite / upgrade
- 请求结束时：
  - 从 vLLM paged KV 中提取 prefix KV
  - 聚合为 prefix 级 object
  - 写入 critical / refinement object
  - 更新 manifest
  - 下次请求可命中并复用
- bench 能输出：
  - TTFT p50 / p95
  - TPOT / ITL
  - goodput
  - manifest hit ratio
  - critical/refinement bytes
  - planner mode 分布
  - fallback / recompute 原因统计

---

## 2. 优先级排序

按下面顺序开发，不要跳。

### P0：冻结依赖与接口版本
先把环境固定住，避免后面反复适配。

### P1：补齐真正的 vLLM connector 生命周期
这是最高优先级；不完成，后面都是 mock。

### P2：实现真实的 KV save/load 主链路
让 prefix 级 object 与 manifest 闭环跑起来。

### P3：实现真实的 paged KV 注入与提取
让系统不再只是“拉回 blob”，而是“真的恢复 KV”。

### P4：实现后台 refinement
让系统体现 deadline-aware progressive transfer 的核心贡献。

### P5：补论文级评测与指标
让系统可以产生可写 paper 的结果。

### P6：做健壮性、测试、文档收尾
保证 vibe coding 产出的代码后续可维护。

---

## 3. P0：冻结依赖与接口版本

## 3.1 目标

把项目从“宽范围依赖”改成“固定版本 + 固定接口”。

## 3.2 必改文件

- `requirements.txt`
- `pyproject.toml`
- `README.md`
- `QUICKSTART.md`
- `scripts/run_vllm_server.sh`
- `configs/*.yaml`

## 3.3 具体修改

### A. 固定 vLLM 版本

当前 `requirements.txt` 里是宽松范围写法，不利于 connector 开发。

要求：

- 固定一个明确可用的 vLLM 版本，不要再用 `vllm>=...`。
- 在 `README.md` 与 `QUICKSTART.md` 中明确写：
  - Python 版本
  - CUDA 版本
  - PyTorch 版本
  - vLLM 版本
  - 测试通过的 GPU 环境（4×V100）

建议：

- 选定一个你当前机器上能稳定安装并支持 KV Connector V1 / disaggregated prefill 的版本。
- 一旦选定，这一阶段内不要升级。

### B. 固定 block size / cache dtype / kv layout version

在配置里统一固定：

- `block_size`
- `cache_dtype`
- `kv_layout_version`
- `critical_codec`
- `refinement_codec`

要求：

- `prefix_key` 的生成逻辑必须和这些字段严格绑定。
- manifest query / put 必须使用同一套配置值。

### C. 明确运行入口

在 `scripts/run_vllm_server.sh` 中：

- 明确传入自定义 connector 的配置。
- 明确 manifest / data sidecar 地址。
- 明确日志与 metrics 输出目录。

## 3.4 完成标准

完成后应满足：

- 全新机器按文档一步部署后可以稳定启动。
- 同一份配置下，prefix key 与 object id 在多次运行中保持一致。
- 不会因为 vLLM 小版本漂移导致 connector 方法签名失效。

---

## 4. P1：补齐真正的 vLLM connector 生命周期（最高优先级）

## 4.1 目标

让当前 connector 真正成为一个符合 vLLM KV Connector V1 生命周期的实现，而不是“长得像 connector 的自定义逻辑”。

## 4.2 必改文件

- `src/dakv/connector/__init__.py`
- `src/dakv/connector/vllm_adapter.py`
- `src/dakv/connector/scheduler_side.py`
- `src/dakv/connector/worker_side.py`
- `src/dakv/connector/<主connector文件>.py`
  - 如果已有主类文件，直接改它
  - 如果没有，就新建 `src/dakv/connector/deadline_connector.py`
- `src/dakv/common/types.py`

## 4.3 需要新增/整理的数据结构

在 `src/dakv/common/types.py` 中补齐并统一以下 dataclass：

### A. `DeadlineConnectorMetadata`
用于 scheduler -> worker 的单步 metadata，下发给 worker。

至少包含：

- `request_id`
- `prefix_key`
- `plan_mode`
- `matched_tokens`
- `matched_blocks`
- `num_layers`
- `critical_object_id`
- `critical_codec`
- `critical_nbytes`
- `refinement_object_id`
- `refinement_codec`
- `refinement_nbytes`
- `need_refinement`
- `load_deadline_ms`
- `allocated_block_ids`
- `slot_mapping_handle` 或可序列化的 block/slot 视图引用

### B. `RequestTransferState`
用于 connector 内部维护 request 生命周期状态。

至少包含：

- manifest 查询结果
- planner 决策结果
- 分配到的 block 信息
- load future / save future
- critical 是否完成
- refinement 是否完成
- request 是否 finished
- fallback / recompute 原因

### C. `WorkerLoadResult` / `WorkerSaveResult`
用于 worker -> scheduler 的反馈。

至少包含：

- `request_id`
- `success`
- `loaded_tokens`
- `loaded_blocks`
- `critical_done`
- `refinement_done`
- `bytes_transferred`
- `error_code`
- `error_message`

## 4.4 主 connector 必须实现的接口

> 注意：不要再只做“类似名字的方法”。要让主 connector 真正承担 vLLM 生命周期对接职责。

在 `src/dakv/connector/<主connector文件>.py` 中完成：

### A. 类定义

- 主类正式继承 `KVConnectorBase_V1`
- 明确区分 scheduler role / worker role / both role

### B. 必须实现的方法

至少补齐并真正生效：

- `get_num_new_matched_tokens(...)`
- `update_state_after_alloc(...)`
- `build_connector_meta(...)`
- `build_connector_worker_meta(...)`（如果需要 worker step metadata）
- `update_connector_output(...)`
- `start_load_kv(...)`
- `save_kv_layer(...)`
- `wait_for_save(...)`
- `request_finished(...)`
- `get_finished(...)`

### C. 角色分工

- scheduler 侧：
  - 查询 manifest
  - 调 planner
  - 决定本次是否 external load
  - 在 block allocation 之后把 block/slot 相关信息写入 transfer state
  - 生成 metadata
- worker 侧：
  - 接收 metadata
  - 发起 critical load
  - 在 forward 前/中把 KV 注入 paged buffer
  - 收集 save 数据
  - 回传 load/save 完成结果

## 4.5 各文件精确修改要求

### 4.5.1 `src/dakv/connector/scheduler_side.py`

当前问题：

- 只做 manifest query + planner 决策
- 结果没有形成稳定的 request-scoped state
- 没有把 plan / object_id / refinement 信息真正传给 worker

必须改成：

1. 把 `get_num_matched_tokens(...)` 重命名/对齐为 connector 生命周期里真正使用的方法。
2. 维护 `self.request_states: dict[request_id, RequestTransferState]`
3. manifest 命中后把完整 manifest 与 planner result 存入 state
4. `matched_tokens` 必须是“可被加载的 external tokens 数量”，而不是只打印日志
5. 支持 `None` 返回语义：当 manifest query 或 planner 还没准备好时，可让 scheduler 下一轮再查
6. 当 planner 选择 `RECOMPUTE` 时，state 中记录原因，便于 metrics 输出
7. 为 `build_connector_meta(...)` 提供完整输入

新增函数建议：

- `prepare_request_state(request, num_computed_tokens)`
- `bind_allocated_blocks(request_id, blocks, num_external_tokens)`
- `build_request_metadata(request_id)`

### 4.5.2 `src/dakv/connector/vllm_adapter.py`

目标：把所有 vLLM 版本敏感逻辑集中到这里。

要求：

1. 封装从 `Request` 中提取：
   - `request_id`
   - `prompt_token_ids`
   - `sampling params`
   - `model id`
2. 封装从 `SchedulerOutput` / `KVCacheBlocks` 中提取：
   - allocated block ids
   - block tables
   - slot mapping
   - layer names / num layers
3. 封装 worker forward context 中与 attention metadata 有关的字段读取
4. 不允许这些逻辑散落在 `scheduler_side.py` 与 `worker_side.py`

### 4.5.3 `src/dakv/connector/<主connector文件>.py`

这是本阶段最核心文件。

要求：

1. 统一调度 `scheduler_side` / `worker_side`
2. 在 scheduler role 下：
   - `get_num_new_matched_tokens` 调 scheduler_side
   - `update_state_after_alloc` 记录 block 分配结果
   - `build_connector_meta` 序列化 metadata
   - `update_connector_output` 消费 worker 回传结果
3. 在 worker role 下：
   - `start_load_kv` 调 worker_side
   - `save_kv_layer` 调 worker_side / saver session
   - `wait_for_save` 等待异步保存
   - `get_finished` 上报已结束 request
4. 所有异步 future 必须 request-scoped 管理
5. 所有异常必须转成结构化 error code，不允许只打日志后 silent fail

### 4.5.4 `src/dakv/connector/__init__.py`

要求：

- 正确导出主 connector 类
- 提供清晰的工厂方法或注册入口
- 避免 circular import

## 4.6 完成标准

完成后应满足：

- vLLM 能通过官方 connector 配置方式实例化该 connector
- scheduler 确实会调用 manifest/planner 逻辑
- worker 确实能收到 scheduler 生成的 metadata
- load/save 生命周期事件能被 connector 追踪到 request 级别
- 所有关键接口不再是空实现/伪实现

---

## 5. P2：实现真实的 prefix 级保存主链路

## 5.1 目标

把“保存 KV”从“每层随手 store 一下”改成**prefix 级对象聚合 + manifest 原子更新**的唯一主路径。

## 5.2 必改文件

- `src/dakv/connector/worker_side.py`
- `src/dakv/connector/saver.py`
- `src/dakv/common/types.py`
- `src/dakv/common/hashing.py`
- `src/dakv/store/*`
- `src/dakv/transport/critical_channel.py`
- `src/dakv/transport/refine_channel.py`

建议新增：

- `src/dakv/connector/save_session.py`

## 5.3 保存路径必须改成什么样

### 正确的保存主链路

1. request 结束前，connector 得到该 request 对应的 prefix block ids
2. 按 layer 从 paged KV buffer 中抽取 prefix 范围 KV
3. 聚合为 request-scoped save session
4. 所有层收齐后，交给 `KVSaver.save_prefix_kv(...)`
5. `KVSaver` 负责：
   - critical encode
   - refinement encode
   - 生成 object id
   - 调 transport store
   - 更新 manifest
6. manifest 更新成功后，才算该 prefix 可复用

### 错误做法（必须删掉）

- `save_kv_layer(...)` 每来一层就直接调用 `critical_channel.store(...)`
- 不聚合层数据就写 object store
- 不更新 manifest 就视为保存完成

## 5.4 各文件精确修改要求

### 5.4.1 `src/dakv/connector/worker_side.py`

要求：

1. `save_kv_layer(...)` 不再直接持久化远端对象
2. 改成把当前 layer 提取出来的 prefix KV 放入 `SaveSession`
3. `request_finished(...)` 或 `wait_for_save(...)` 时触发统一 flush
4. 每个 request 对应一个 save session
5. save session 至少记录：
   - request_id
   - prefix_key
   - matched_tokens
   - matched_blocks
   - num_layers
   - 已收到哪些 layer
   - 各 layer KV tensor / CPU buffer

### 5.4.2 `src/dakv/connector/save_session.py`（新建）

职责：

- 管理一个 request 的 layer 聚合
- 判断何时“层收齐可以 flush”
- 避免层顺序乱序、重复写、提前 flush

建议接口：

- `add_layer(layer_name, kv_tensor, attn_metadata, slot_mapping)`
- `is_complete()`
- `flush_to_saver()`
- `abort(reason)`

### 5.4.3 `src/dakv/connector/saver.py`

当前优点：已经有 prefix 级 object + manifest 更新雏形。

本阶段要求：

1. `save_prefix_kv(...)` 成为唯一保存主路径
2. critical/refinement 不再只是简单 `b"".join`，需要同时记录：
   - layer 顺序
   - 每层 shape
   - dtype
   - token/block 范围
   - offset table
3. object 格式改成：
   - object header
   - per-layer offset table
   - payload
4. manifest 中记录：
   - object format version
   - layer order
   - block size
   - token count
   - checksum
5. manifest 更新需要失败回滚/失败告警
6. refinement 关闭时，也要形成合法 manifest

### 5.4.4 `src/dakv/common/hashing.py`

要求：

- `prefix_key` 只取决于 prefix 语义 + KV layout 相关元信息
- `object_id` 取决于 `prefix_key + quality tier + codec + object format version`
- 不允许 object id 里混入本次 request 的随机因素

## 5.5 完成标准

完成后应满足：

- 一个请求结束后，会生成可复用的 manifest 记录
- 下一个共享 prefix 请求能通过 manifest hit 找到完整 object
- 保存逻辑不再依赖单层直写
- object 可被 loader 按层解析出来

---

## 6. P3：实现真实的 paged KV 注入与提取

## 6.1 目标

把系统从“下载一个 blob 然后 decode 成固定 shape tensor”升级为“真正按 vLLM 的 paged KV 布局恢复/提取 KV”。

## 6.2 必改文件

- `src/dakv/connector/worker_side.py`
- `src/dakv/connector/loader.py`
- `src/dakv/connector/vllm_adapter.py`
- `src/dakv/codec/*`

建议新增：

- `src/dakv/connector/paged_kv_ops.py`

## 6.3 必须实现的核心能力

### A. 从 paged KV layer 提取 prefix 范围 KV

在保存路径上，需要一个统一函数：

- 输入：
  - `kv_layer`
  - `slot_mapping`
  - `attn_metadata`
  - `matched_blocks / matched_tokens`
- 输出：
  - 当前层该 prefix 对应的连续 KV tensor

建议放到 `paged_kv_ops.py`：

- `extract_prefix_kv_from_layer(...)`

### B. 把外部 KV 注入 paged KV layer

在加载路径上，需要一个统一函数：

- 输入：
  - `dst_kv_cache_layer`
  - `src_kv_tensor`
  - `slot_mapping`
  - `attn_metadata`
- 输出：
  - 将外部 KV 正确拷贝到 paged KV cache 中

建议接口：

- `inject_prefix_kv_into_layer(...)`

### C. 去掉所有硬编码 shape

必须删除类似：

- 固定 `shape=(1, 16, 128)`
- 固定 `num_layers`
- 假设所有层大小完全相同且无需 header 解析

真实 shape 应来自：

- object header / offset table
- model 层数与 hidden layout
- vLLM attention metadata

## 6.4 各文件精确修改要求

### 6.4.1 `src/dakv/connector/worker_side.py`

加载路径要求：

1. `start_load_kv(...)` 接收的是 connector metadata，而不是裸 `object_id`
2. 启动异步 critical load future
3. 先把 critical object 拉回 host / pinned memory
4. 解析 object header，按层建立 layer future 或 layer view
5. 在 `start_load_kv` 或接近 forward 的阶段，把 layer 数据注入 paged KV buffer
6. 如果 refinement 启用，则同时挂起 refinement future

保存路径要求：

1. `save_kv_layer(...)` 通过 `extract_prefix_kv_from_layer(...)` 抽取真实 prefix KV
2. 只把抽取结果放入 save session
3. 不直接发送到远端

### 6.4.2 `src/dakv/connector/loader.py`

要求：

1. 实现 object parse 逻辑：
   - 读取 header
   - 建立 per-layer offset table
   - 提供 `get_layer_tensor(layer_idx)` / `iter_layers()`
2. critical 和 refinement 的 object parse 逻辑统一
3. 支持 lazy per-layer decode，而不是一次性把所有层全 decode 到 GPU
4. 支持 host cache 命中
5. 支持 load timeout / partial load / checksum fail

### 6.4.3 `src/dakv/connector/paged_kv_ops.py`（新建）

职责：

- 统一封装 paged KV 提取/注入操作
- 屏蔽 vLLM 内部布局差异
- 后续版本变更时尽量只改这里和 adapter

## 6.5 完成标准

完成后应满足：

- 远端保存的 KV 能按层正确恢复到 paged KV buffer
- 在共享 prefix 下，decode 输出可直接复用外部 KV，而不是重新 prefill 整段 prefix
- 保存与加载两侧使用一致的 object header / layer order / shape 解析

---

## 7. P4：实现后台 refinement

## 7.1 目标

让系统真正体现“deadline-aware progressive transfer”而不是只存在两个 codec 名字。

## 7.2 必改文件

- `src/dakv/connector/loader.py`
- `src/dakv/connector/worker_side.py`
- `src/dakv/planner/deadline_planner.py`
- `src/dakv/transport/refine_channel.py`
- `src/dakv/metrics/*`

建议新增：

- `src/dakv/connector/refine_session.py`

## 7.3 要实现的机制

### A. Planner 输出真正驱动数据面

planner 的四个模式必须分别有真实行为：

#### 1. `FULL_FP16`

- 如果带宽/预算允许，直接加载完整高质量对象
- 可等价为 critical=fp16、无 refinement

#### 2. `CRITICAL_INT8_ONLY`

- 只加载 int8 critical
- 不发起 refinement
- decode 全程使用 int8 恢复的 KV

#### 3. `CRITICAL_INT8_THEN_FP16`

- 先加载 int8 critical
- TTFT 后异步加载 refinement
- refinement 到达后对已加载 prefix KV 进行 upgrade / overwrite

#### 4. `RECOMPUTE`

- 不走外部加载
- 本地正常 prefill
- metrics 记录 recompute 原因

### B. refinement 必须是 request-scoped 后台任务

实现要求：

- 每个 request 一个 refinement session
- critical 完成后可立即开始 decode
- refinement future 独立存在
- refinement 完成时更新 request state 与 metrics
- refinement 超时、失败、取消都必须有明确状态

### C. refinement apply 语义

第一版只做最稳方案：

- critical = int8 近似 KV
- refinement = fp16 完整覆盖同一 prefix KV
- apply 方式 = overwrite，不做残差合成

不要在这一阶段引入复杂 residual codec。

## 7.4 各文件精确修改要求

### 7.4.1 `src/dakv/planner/deadline_planner.py`

要求：

1. planner 输出必须包含：
   - `plan_mode`
   - `load_deadline_ms`
   - `need_refinement`
   - `expected_critical_bytes`
   - `expected_refinement_bytes`
   - `fallback_reason`
2. 规则先保持简单可解释：
   - 带宽足够：`FULL_FP16`
   - 带宽一般：`CRITICAL_INT8_THEN_FP16`
   - 带宽差：`CRITICAL_INT8_ONLY`
   - 预算不足/manifest 不可信：`RECOMPUTE`
3. 所有 planner 决策都要可打点输出

### 7.4.2 `src/dakv/connector/loader.py`

要求：

1. 增加：
   - `start_critical_load(...)`
   - `start_refinement_load(...)`
   - `apply_refinement_if_ready(...)`
2. critical 先服务首 token
3. refinement 只在不影响当前 decode 的时机 apply
4. refinement apply 失败不能破坏已有 critical 状态

### 7.4.3 `src/dakv/connector/worker_side.py`

要求：

1. request state 中加入 refinement session
2. 在合适时机轮询或回调 `apply_refinement_if_ready(...)`
3. 把 refinement 完成时间、bytes、是否命中 deadline 记入 metrics

## 7.5 完成标准

完成后应满足：

- `CRITICAL_INT8_THEN_FP16` 模式下，TTFT 主要受 critical 影响而不是被 refinement 阻塞
- refinement 能独立完成并成功覆盖 prefix KV
- `INT8_ONLY` / `INT8_THEN_FP16` / `RECOMPUTE` 结果可区分、可测量

---

## 8. P5：补论文级评测与指标

## 8.1 目标

让项目输出能直接服务论文，而不是只证明“代码能跑”。

## 8.2 必改文件

- `scripts/run_bench.py`
- `scripts/run_vllm_server.sh`
- `docs/EVAL.md`
- `docs/ARCH.md`
- `src/dakv/metrics/*`
- `configs/*.yaml`

建议新增：

- `scripts/bench_shared_prefix.py`
- `scripts/bench_network_sweep.py`
- `scripts/bench_mode_ablation.py`
- `scripts/parse_metrics.py`

## 8.3 必须支持的指标

### A. 时延指标

- TTFT p50 / p95
- TPOT / ITL
- 请求完成时间

### B. 传输指标

- critical bytes
- refinement bytes
- total bytes
- 远端 load 时间
- refinement 完成时间

### C. 命中与调度指标

- manifest hit ratio
- plan mode 分布
- recompute ratio
- refinement success ratio
- fallback 原因统计

### D. 系统稳定性指标

- timeout 次数
- checksum fail 次数
- manifest miss 次数
- object missing 次数

## 8.4 需要实现的实验脚本

### 8.4.1 `scripts/bench_shared_prefix.py`

目标：

- 产生一组高共享 prefix workload
- 验证 prefix 复用是否真实生效

输出：

- RECOMPUTE vs INT8_ONLY vs INT8_THEN_FP16
- TTFT / goodput / bytes

### 8.4.2 `scripts/bench_network_sweep.py`

目标：

- 配合 `tc/netns/veth` 改变：
  - 带宽
  - RTT
  - 丢包
- 观察 planner mode 如何变化

输出：

- 不同网络条件下 TTFT p95
- planner mode 分布
- refinement 完成率

### 8.4.3 `scripts/bench_mode_ablation.py`

目标：

- 固定 workload，对比：
  - no external KV / recompute
  - full fp16 load
  - int8 only
  - int8 then fp16

输出：

- latency / bandwidth / quality tradeoff

## 8.5 `scripts/run_bench.py` 的具体重构要求

当前要求：

1. 支持 streaming 请求，准确测 TTFT
2. 支持逐 token 时间记录，得到 TPOT / ITL
3. 支持从 response / side metrics 中抓取：
   - plan mode
   - hit/miss
   - critical/refinement bytes
4. 输出 JSONL 原始结果文件
5. 输出聚合 CSV 结果文件

## 8.6 `src/dakv/metrics/*` 的具体要求

最少新增以下 metric：

- `dakv_manifest_query_total{hit=...}`
- `dakv_plan_mode_total{mode=...}`
- `dakv_recompute_total{reason=...}`
- `dakv_critical_bytes_total`
- `dakv_refinement_bytes_total`
- `dakv_critical_load_latency_ms`
- `dakv_refinement_load_latency_ms`
- `dakv_refinement_apply_latency_ms`
- `dakv_external_load_success_total`
- `dakv_external_load_fail_total{reason=...}`
- `dakv_save_success_total`
- `dakv_save_fail_total{reason=...}`

## 8.7 完成标准

完成后应满足：

- 一键跑完 shared-prefix 与 network-sweep 实验
- 自动导出论文可画图数据
- 不需要手工翻日志统计结果

---

## 9. P6：健壮性、回退逻辑、测试与文档

## 9.1 必改文件

- `src/dakv/tests/*`
- `docs/ARCH.md`
- `docs/EVAL.md`
- `README.md`
- `QUICKSTART.md`

## 9.2 必须补的测试

### 单元测试

- prefix key / object id 稳定性
- object header encode/decode
- per-layer offset table parse
- int8/fp16 codec encode/decode
- planner mode 决策

### 集成测试

- manifest miss -> recompute
- manifest hit -> critical load -> decode
- request finished -> save -> manifest put -> 下次命中
- refinement timeout -> 保持 critical 结果不崩

### 端到端测试

- 单机本地 sidecar
- 低带宽高 RTT 场景
- `INT8_ONLY`
- `INT8_THEN_FP16`

## 9.3 文档要求

在 `docs/ARCH.md` 中重画并重写：

- scheduler control path
- worker data path
- save path
- refinement path
- metrics path

在 `docs/EVAL.md` 中明确：

- baseline
- workload
- network settings
- metrics definitions
- figure plan

---

## 10. 精确到文件的开发清单

下面给出一份可以直接照着改的清单。

## 10.1 第一批必须改（本周先做）

### 1. `requirements.txt`

- 固定版本号
- 去掉宽松 `>=`

### 2. `src/dakv/connector/<主connector文件>.py`

- 让主类正式继承 `KVConnectorBase_V1`
- 补齐 connector 生命周期方法
- 建立 request-scoped state machine

### 3. `src/dakv/connector/scheduler_side.py`

- 维护 `request_states`
- 输出完整 metadata 所需状态
- 支持 `RECOMPUTE` / `INT8_ONLY` / `INT8_THEN_FP16`

### 4. `src/dakv/connector/vllm_adapter.py`

- 集中实现 request / block / slot mapping / forward context 解析

### 5. `src/dakv/common/types.py`

- 补齐 metadata / state / result dataclass

### 6. `src/dakv/connector/worker_side.py`

- 改掉硬编码 shape
- `start_load_kv` 改为接 metadata
- `save_kv_layer` 改为写入 session，而不是直接 store

## 10.2 第二批必须改（第一批完成后马上做）

### 7. `src/dakv/connector/save_session.py`（新建）

- 管理按 request 聚合 layer 的保存 session

### 8. `src/dakv/connector/saver.py`

- 成为唯一保存主路径
- 加 object header + per-layer offsets
- manifest 更新带版本与校验信息

### 9. `src/dakv/connector/loader.py`

- 支持 object parse
- 支持 per-layer lazy decode
- 支持 critical/refinement 双对象

### 10. `src/dakv/connector/paged_kv_ops.py`（新建）

- 提供 paged KV 提取/注入统一函数

## 10.3 第三批必须改（进入实验前做完）

### 11. `src/dakv/planner/deadline_planner.py`

- 补齐可解释 plan 输出
- 决策结果可打点

### 12. `src/dakv/metrics/*`

- 增加完整实验指标

### 13. `scripts/run_bench.py`

- 支持 streaming TTFT/TPOT
- 输出 JSONL + CSV

### 14. `scripts/bench_shared_prefix.py`（新建）

- 构造共享 prefix workload

### 15. `scripts/bench_network_sweep.py`（新建）

- 自动切换 tc 网络条件并收集结果

---

## 11. 推荐的实际开发顺序（不要乱序）

### Step 1
先只做 **P0 + P1**，不碰 refinement。

目标：

- vLLM 能正确实例化 connector
- scheduler metadata 能到 worker
- worker 能知道该去加载哪个 object

### Step 2
做 **P2**，把 save path 统一成 prefix object + manifest。

目标：

- 请求结束后真的能写出可复用 prefix object
- 下次请求 manifest hit 后能找到 object

### Step 3
做 **P3**，实现真实 paged KV 注入与提取。

目标：

- 不再依赖固定 shape tensor
- 真正把外部 KV 恢复进 paged KV buffer

### Step 4
做 **P4**，只实现最简单 refinement：`int8 critical + fp16 overwrite`。

目标：

- TTFT 不被 refinement 阻塞
- refinement 能后台补齐

### Step 5
做 **P5 + P6**，补实验和图表数据输出。

目标：

- 产出 paper-ready 指标

---

## 12. 本阶段不做的内容

为了避免系统失控，本阶段明确不做下面这些：

- 不做复杂 residual codec
- 不做跨多机真实 RDMA/NIXL 集成
- 不做多租户公平调度
- 不做多 prefix 拼接/分裂对象格式
- 不做过于复杂的学习型 planner
- 不做质量自适应的 layer importance model

本阶段只做：

**最小但真实的 deadline-aware prefix KV 传输闭环。**

---

## 13. 最终验收标准

vibe coding 完成本任务书后，系统至少要满足下面 8 条：

1. 能在固定版本 vLLM 上稳定加载自定义 connector
2. scheduler 能根据 manifest/planner 决定 external load 或 recompute
3. scheduler metadata 能正确传到 worker
4. worker 能把 critical KV 真正注入 paged KV buffer
5. 请求结束后能把 prefix KV 真正保存成 object 并更新 manifest
6. 下次共享 prefix 请求能够真实命中并复用
7. `CRITICAL_INT8_ONLY` 与 `CRITICAL_INT8_THEN_FP16` 都能跑通
8. bench 能自动导出 TTFT / TPOT / bytes / plan mode / hit ratio 等核心指标

---

## 14. 给 vibe coding 的一句话执行摘要

请不要继续扩展新模块名，而是以“**补齐真实 vLLM connector 生命周期 + 真实 paged KV save/load + 真实后台 refinement**”为唯一主线，按本任务书的优先级逐文件修改代码，把 `awarekv` 从 scaffold 改造成能跑论文实验的系统。
