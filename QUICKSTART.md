# DAKV 快速上手指南

## 项目已完成 ✅

这个项目已经按照 `readme_deadline_prefix_kv_vllm.md` 的要求完整实现了：

1. ✅ 真实接入 vLLM 的自定义 KV connector
2. ✅ 远端 prefix KV 的 save/load 功能
3. ✅ Deadline-aware 的 critical/refinement 分级传输
4. ✅ 三层存储架构 (T0: GPU, T1: Host Cache, T2: Remote)
5. ✅ 完整的网络模拟工具 (netns/veth/tc)
6. ✅ 测试框架和 benchmark 工具

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
│   ├── run_vllm_server.sh        # 启动 vLLM + DAKV
│   ├── run_bench.py              # 运行 benchmark
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
│   ├── connector/                 # vLLM connector 实现
│   ├── bench/                     # Benchmark 工具
│   └── tests/                     # 单元和集成测试
│
└── docs/                          # 文档
    ├── ARCH.md                    # 架构说明
    ├── PROTOCOL.md                # 协议规范
    └── EVAL.md                    # 评估指南
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行冒烟测试

```bash
bash scripts/smoke_test.sh
```

这会启动 KV store 并验证基本功能。

### 3. 启动完整系统

**终端 1 - 启动 KV Store:**
```bash
python scripts/run_kv_store.py --config configs/deadline_kv_local.yaml
```

**终端 2 - 启动 vLLM Server:**
```bash
export MODEL="meta-llama/Llama-2-7b-hf"
export TP=1
bash scripts/run_vllm_server.sh
```

**终端 3 - 运行 Benchmark:**
```bash
python scripts/run_bench.py --workload shared_prefix
```

## 核心功能

### 1. 三种传输模式

- **FULL_FP16**: 网络条件好，直接传完整 FP16
- **CRITICAL_INT8_THEN_FP16**: 先传 INT8 critical，后补 FP16 refinement
- **CRITICAL_INT8_ONLY**: 网络差，只传 INT8，质量降级
- **RECOMPUTE**: 放弃远端加载，重新计算

### 2. Deadline-aware 规划

系统根据以下因素自动选择传输模式：
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

### Connector 测试

```bash
pytest src/dakv/tests/test_connector_smoke.py -v
```

## 指标和监控

### Prometheus 指标

访问 `http://localhost:9090/metrics` 查看实时指标：

- `dakv_manifest_queries_total` - Manifest 查询总数
- `dakv_manifest_hit_total` - Manifest 命中数
- `dakv_remote_critical_bytes_total` - Critical 传输字节数
- `dakv_ttft_ms_bucket` - TTFT 延迟分布
- `dakv_recompute_fallback_total` - Recompute 回退次数

### 请求级日志

每个请求的详细指标会记录到日志：

```json
{
  "request_id": "req_123",
  "prefix_hit": true,
  "matched_tokens": 256,
  "plan_mode": "CRITICAL_INT8_THEN_FP16",
  "critical_bytes": 1048576,
  "refine_bytes": 2097152,
  "critical_load_ms": 41.2,
  "refine_load_ms": 72.8,
  "ttft_ms": 188.7,
  "fallback": false
}
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

## 实验场景

### 场景 1: 验证 Prefix 命中加速

```bash
# 运行共享前缀的 workload
python scripts/run_bench.py --workload shared_prefix
```

观察第二次请求的 TTFT 明显降低。

### 场景 2: 网络条件对比

```bash
# 1Gbps 网络
sudo bash scripts/tc_profile_1g_20ms.sh
python scripts/run_bench.py

# 100Mbps 网络
sudo bash scripts/tc_profile_100m_50ms_loss1.sh  
python scripts/run_bench.py
```

对比不同网络下的 plan_mode 和 TTFT。

### 场景 3: 质量对比

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

### vLLM 无法加载 connector

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

## 下一步

1. **集成更强的编码器**: 实现 INT4 或学习型压缩
2. **优化 residual refinement**: 从 overwrite 升级到 residual add
3. **分布式部署**: 支持多节点 KV store
4. **更复杂的 planner**: 基于强化学习的自适应规划
5. **GPU kernel 优化**: 优化 KV apply 的性能

## 项目成果

✅ **已完成所有核心目标**:

1. ✅ 真实接入 vLLM，通过自定义 KVConnectorBase_V1
2. ✅ 完整的 remote prefix KV save/load 闭环
3. ✅ Deadline-aware 分级传输 (critical + refinement)
4. ✅ 三层存储架构 (GPU / Host / Remote)
5. ✅ 网络条件注入和模拟
6. ✅ 完整的测试和 benchmark 框架
7. ✅ 详细的文档和指标收集

这个系统已经是一个**可运行的原型**，可以直接用于论文实验和进一步开发！

## 联系和贡献

如有问题，请查看 `docs/` 目录下的详细文档。

Happy Hacking! 🚀
