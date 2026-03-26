# DAKV 快速上手指南

> **⚠️ 重要提示**: 本项目正在积极开发中。核心组件（vLLM connector 生命周期、paged KV apply/extract、prefix 级 save/load）正在实现。以下文档中标记为 (WIP) 的部分表示正在进行中。

## 项目当前状态

### ✅ 已完成

1. ✅ 版本固定 (torch==2.1.0, vLLM==0.6.3.post1)
2. ✅ 模块骨架搭建
3. ✅ Deadline-aware planner 逻辑
4. ✅ 编解码器实现 (fp16, int8)
5. ✅ 传输协议和 channels (critical/refinement)
6. ✅ Manifest service 和对象存储基础

### 🚧 正在实现 (按优先级)

1. 🚧 **P1-R**: vLLM Connector V1 完整生命周期集成
2. 🚧 **P2-R**: Prefix 级 save/load 主路径
3. 🚧 **P3-R**: 真实的 paged KV apply/extract
4. 🚧 **P4-R**: 后台 refinement 补齐机制

### ⏳ 计划中

1. ⏳ **P5-R**: 论文级 benchmark 和指标
2. ⏳ **P6**: 完整的测试和文档

## 项目结构

```
icnp/
├── configs/                       # 配置文件
│   ├── deadline_kv_local.yaml    # 本地测试配置
│   ├── deadline_kv_netem_1g_20ms.yaml
│   └── deadline_kv_netem_100m_50ms_loss.yaml
│
├── scripts/                       # 启动和测试脚本
│   ├── run_kv_store.py           # 启动远端 KV store
│   ├── run_vllm_server.sh        # 启动 vLLM + DAKV (WIP)
│   ├── run_bench.py              # 运行 benchmark (WIP)
│   ├── netns_setup.sh            # 网络命名空间设置
│   ├── tc_profile_*.sh           # 网络条件模拟
│   └── smoke_test.sh             # 冒烟测试
│
├── src/dakv/                      # 核心实现
│   ├── common/                    # 通用工具和类型
│   ├── codec/                     # 编解码器 (fp16, int8)
│   ├── store/                     # Manifest 和对象存储
│   ├── transport/                 # 网络传输层
│   ├── planner/                   # Deadline-aware 规划器
│   ├── tier/                      # 多层缓存管理
│   ├── metrics/                   # 指标收集
│   ├── connector/                 # vLLM connector 实现 (WIP)
│   ├── bench/                     # Benchmark 工具 (WIP)
│   └── tests/                     # 单元和集成测试
│
└── docs/                          # 文档
    ├── ARCH.md                    # 架构说明
    ├── PROTOCOL.md                # 协议规范
    └── EVAL.md                    # 评估指南 (WIP)
```

## 快速开始

### Quickstart-Minimal (当前可用)

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 启动 KV Store

**终端 1 - 启动 KV Store:**
```bash
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml
```

#### 3. 运行基础测试

```bash
# 测试编解码器
pytest src/dakv/tests/test_codec.py -v

# 测试规划器
pytest src/dakv/tests/test_planner.py -v

# 测试传输协议
pytest src/dakv/tests/test_transport.py -v

# 测试 manifest service
pytest src/dakv/tests/test_manifest.py -v
```

#### 4. 测试 Manifest 和 Data Server

```bash
# 检查 manifest service
curl http://127.0.0.1:8081/manifest/stats

# 运行端到端本地测试
pytest src/dakv/tests/test_end_to_end_local.py -v -s
```

### Quickstart-Integration (正在实现)

> ⚠️ 以下部分正在实现中，尚未完全功能化

#### 启动 vLLM Server (WIP)

```bash
export MODEL="meta-llama/Llama-2-7b-hf"
export TP=1
bash scripts/run_vllm_server.sh
```

#### 运行 Benchmark (WIP)

```bash
python scripts/run_bench.py --workload shared_prefix
```

## 核心功能设计

### 1. 四种传输模式

- **FULL_FP16**: 网络条件好，直接传完整 FP16
- **CRITICAL_INT8_THEN_FP16**: 先传 INT8 critical，后补 FP16 refinement
- **CRITICAL_INT8_ONLY**: 网络差，只传 INT8，质量降级
- **RECOMPUTE**: 放弃远端加载，重新计算

### 2. Deadline-aware 规划

系统将根据以下因素自动选择传输模式：
- TTFT SLO 目标 (默认 500ms)
- 当前网络带宽估计 (EWMA)
- RTT 延迟
- Prefix 长度

### 3. 两级传输通道

- **Critical Channel**: 高优先级，严格 deadline，失败则 recompute
- **Refinement Channel**: 低优先级，可取消，超时则丢弃

## 网络模拟

### 设置网络命名空间

```bash
sudo bash scripts/netns_setup.sh
```

### 应用 1Gbps + 20ms RTT 配置

```bash
sudo bash scripts/tc_profile_1g_20ms.sh
```

### 应用 100Mbps + 50ms RTT + 1% 丢包

```bash
sudo bash scripts/tc_profile_100m_50ms_loss1.sh
```

### 清理

```bash
sudo bash scripts/netns_teardown.sh
```

## 运行测试

### 单元测试

```bash
# 测试编解码器
pytest src/dakv/tests/test_codec.py -v

# 测试规划器
pytest src/dakv/tests/test_planner.py -v

# 测试传输协议
pytest src/dakv/tests/test_transport.py -v
```

### 集成测试

```bash
pytest src/dakv/tests/test_end_to_end_local.py -v -s
```

### Connector 测试 (WIP)

```bash
pytest src/dakv/tests/test_connector_smoke.py -v
```

## 配置说明

编辑 `configs/deadline_kv_local.yaml` 调整参数：

```yaml
# TTFT SLO 目标 (毫秒)
ttft_slo_ms: 500

# 是否启用 refinement
enable_refinement: true

# Critical 编码方式
critical_codec: "int8_symm"

# Refinement 编码方式  
refinement_codec: "fp16_raw"

# 网络超时设置
network:
  timeout_ms: 1000
  refine_timeout_ms: 150

# Host cache 大小
host_cache:
  max_bytes: 4294967296  # 4GB

# Planner 参数
planner:
  alpha: 0.8              # TTFT budget 比例
  min_prefix_tokens: 128  # 最小 prefix 长度
```

## 实验场景 (计划中)

### 场景 1: 验证 Prefix 命中加速 (WIP)

```bash
# 运行共享前缀的 workload
python scripts/run_bench.py --workload shared_prefix
```

预期观察第二次请求的 TTFT 明显降低。

### 场景 2: 网络条件对比 (WIP)

```bash
# 1Gbps 网络
sudo bash scripts/tc_profile_1g_20ms.sh
python scripts/run_bench.py

# 100Mbps 网络
sudo bash scripts/tc_profile_100m_50ms_loss1.sh  
python scripts/run_bench.py
```

预期对比不同网络下的 plan_mode 和 TTFT。

### 场景 3: 质量对比 (WIP)

禁用 refinement 对比输出质量：

```yaml
# 修改 config
enable_refinement: false
```

## 故障排查

### KV Store 无法启动

**错误**: `Address already in use`

**解决**: 
```bash
# 查找占用端口的进程
lsof -i :8081
lsof -i :9001

# 杀掉进程或更换端口
```

### vLLM 无法加载 connector (WIP)

**错误**: `Module not found: dakv`

**解决**:
```bash
# 设置 PYTHONPATH
export PYTHONPATH=/Users/hefen/Desktop/husband/icnp/src:$PYTHONPATH
```

### Manifest 查询失败

**检查**:
```bash
# 测试 manifest service
curl http://127.0.0.1:8081/manifest/stats
```

## 开发路线图

### 当前重点 (按顺序)

1. **P1-R**: 完成真实的 vLLM connector 生命周期
   - 继承 KVConnectorBase_V1
   - 实现所有生命周期方法
   - 支持 request-scoped 状态管理

2. **P2-R**: 完成 prefix 级 save/load 主路径
   - Prefix 级 object 格式（header + payload）
   - Manifest 原子更新
   - Save/load 闭环验证

3. **P3-R**: 完成真实的 paged KV 提取与注入
   - 从 vLLM paged KV buffer 提取 prefix KV
   - 将远端 KV 正确写回 paged KV buffer
   - Roundtrip 测试

4. **P4-R**: 完成真实的 refinement 后台补齐
   - Critical 先服务 TTFT
   - Refinement 后台异步补齐
   - 超时可 drop 机制

5. **P5-R**: 完成论文级 benchmark 和指标
   - TTFT/TPOT 测量
   - Plan mode 分布统计
   - Fallback 原因分析

6. **P6**: 补足测试、脚本和文档
   - 完整的单元和集成测试
   - Smoke test 脚本
   - 最终文档

### 未来扩展

1. **集成更强的编码器**: 实现 INT4 或学习型压缩
2. **优化 residual refinement**: 从 overwrite 升级到 residual add
3. **分布式部署**: 支持多节点 KV store
4. **更复杂的 planner**: 基于强化学习的自适应规划
5. **GPU kernel 优化**: 优化 KV apply 的性能

## 联系和贡献

本项目正在积极开发中。如有问题，请查看 `docs/` 目录下的详细文档或查阅任务书。

---

**更新时间**: 2026-03-26  
**状态**: P0-HOTFIX 完成, P1-R ~ P6 进行中
