# 消防主题三档虚构验证数据

## 定位

`tests/fixtures/fictional/fire_validation/` 是 TreeGuard 外网开发使用的
Clean-room 数据集。它只模拟消防治理的功能形状，不对应真实消防信息树、真实
单位、真实设施、真实事故、真实字段或工程规范。

公开资料只用于确定预防、告警、引导、器备、训练和初起协同等高层覆盖类别。
节点名称、层级、设施、事件、需求、模型输出和 oracle 均从零虚构；没有复制
其他项目的树、expected、Gold、训练 JSONL、模型缓存或 Git 历史。

## 三档用途

| 档位 | 节点 | 场景 | benchmark role | 主要用途 |
|---|---:|---:|---|---|
| small | 31 | 8 | `precision_contract` | 人工可读、精确合同断言 |
| medium | 401 | 16 | `semantic_interference` | 异构语义、近名干扰、类型/基数冲突 |
| large | 2,001 | 24 | `scale_stability` | 规模、重排确定性、Top-20/Top-8 有界输出 |

大型档不是语义主基准，不能用其分数代表真实效果。所有 oracle 都只是当前
确定性合同的预期结果或可接受集合，不是生产 Gold。

## 文件

```text
tests/fixtures/fictional/fire_validation/
├── manifest.json
├── tree-small.json
├── scenarios-small.json
├── tree-medium.json
├── scenarios-medium.json
├── tree-large.json
└── scenarios-large.json
```

`manifest.json` 固定数据集边界、三档用途和模型故障 oracle。每个
`scenarios-*.json` 包含：

- 完全虚构的需求和可选父节点提示；
- 满足正式 `change-intent-model-output.v1` 的冻结模型输出；
- 可选的一轮澄清回答和澄清模型输出；
- 人工确认或拒绝动作；
- 意图状态、澄清状态、确认状态、候选状态、首候选和 Top-20/Top-8 上限。

覆盖的治理情形包括：

- 清晰意图直接进入人工确认；
- 全局词法匹配压过错误的局部父节点提示；
- 类型冲突仍由强语义匹配决定候选；
- `NO_CANDIDATES` 与 `INSUFFICIENT_SIGNAL`；
- 一轮澄清后解决或达到澄清上限；
- 人工拒绝；
- 中型 hard-negative 与大型远端目标；
- 大树节点重排后的候选结果稳定。

manifest 中的模型故障 oracle 清单声明非法 JSON、多余字段、缺失字段、
HTTP 429/500、超时、响应过大、重试后成功和 trace canary 隔离的预期结果。
清单只固定测试合同，不代表逐项执行了 transport 故障；实际 transport、重试和
错误映射仍由现有 simulator/provider 测试验证。

## 确定性生成

唯一生成实现位于 `treeguard.fictional_fire_data`。需要重建 fixture 时，在仓库
根目录执行：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen python -c \
  "from treeguard.fictional_fire_data import write_fictional_fire_dataset as w; w('tests/fixtures/fictional/fire_validation')"
```

`tests/test_fictional_fire_data.py` 会在临时目录重新生成全部七个文件并逐字节比较，
同时把所有场景送入现有 Intent、Clarification、Retrieval 和 Semantic
Projection Core。生成器或 oracle 发生未审阅漂移时测试会失败。

## 安全边界

- fixture 不含 `VALUE`、真实消防字段、真实参数、专家文本、模型 trace、凭据、
  内部路径或受保护标识；
- `semantic_approval`、`gold_eligible` 和 `patch_eligible` 始终为 `false`；
- 不向真实模型发送本数据，也不因此获得生产写入或 Patch 权限；
- 不能用本数据声明真实消防 schema 兼容性、工程合规性或生产准确率。
