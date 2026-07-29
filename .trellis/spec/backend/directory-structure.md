# 目录与职责

## 仓库结构

TreeGuard 是采用 `src` 布局的单一 Python 包：

```text
.
├── contracts/               # 版本化 JSON Schema 边界合同
├── docs/                    # 产品、架构、安全和运行手册
├── src/treeguard/           # Python 核心与 CLI 应用边界
├── tests/
│   └── fixtures/fictional/  # 完全虚构的源格式样例
├── pyproject.toml           # 包元数据和四个 CLI 入口
└── uv.lock                  # 可复现开发环境
```

`pyproject.toml` 声明 Python 3.10+、当前无运行时依赖，以及：

- `treeguard` → `treeguard.cli:main`
- `treeguard-ai-review` → `treeguard.ai_cli:main`
- `treeguard-expert-review` → `treeguard.expert_cli:main`
- `treeguard-governance` → `treeguard.governance_cli:main`

当前没有 Web 应用、入站 HTTP API、数据库驱动、ORM、repository、migration、
worker、queue、vector index 或生产 Patch publisher。

## 模块所有权

### 规范基础

- `models.py`：不可变规范树类型，`freeze_json()` / `thaw_json()`；
- `hashing.py`：唯一的规范 JSON SHA-256 实现和审计字段过滤；
- `json_utils.py`：安全敏感输入的严格 JSON 解析；
- `private_io.py`：有界私有 JSON 读取、输出 preflight 和不可覆盖原子发布；
- `lexical.py`：历史 Evidence 与在线召回共享的确定性词法切分；
- `validation.py`：适配非完美源树时收集 issue；
- `adapter.py`：唯一已实现的源树归一化边界，把直接导出或已解码 API envelope
  转换为 `CanonicalTree`。

### 确定性领域流水线

- `diff.py`：按稳定 `node_id` 做字段级快照比较；
- `history.py`：保存修订证据挖掘和可信来源回放；
- `business_review.py`：使用显式顺序的业务版本端点审查；
- `evidence.py`：允许列表化、有界、带临时引用的模型投影；
- `expert_review.py`：纯内存专家审查状态机与事件回放。
- `change_intent.py`：新增需求、模型草稿、人工确认与可信来源回放；
- `retrieval.py`：确认意图上的确定性全树候选评分、截断和回放。
- `semantic_recommendation.py`：有界候选投影、关系—动作政策、人工建议复核和可信
  记录回放。

这些模块必须保持确定性，不得自行发起网络或文件系统副作用。

### 不可信模型边界

- `ai_review.py`：AI 审查合同、本地校验、百炼配置与 OpenAI-compatible 传输；
- `expert_synthesis.py`：受约束的专家思路综合和精确外部请求计划绑定。

Provider 可以执行网络 IO；返回 JSON 必须通过本地字段、枚举、引用、来源、
大小和跨字段校验后才能进入可信工件。

### 应用边界

- `cli.py`：聚合一致性命令；
- `ai_cli.py`：单个业务版本审查案例、可选 AI 调用和私有 bundle 输出；
- `expert_cli.py`：`apply`、`prepare-approval`、`replay` 私有文件工作流；
- `governance_cli.py`：意图、召回、语义建议、人工复核和回放的私有旁路工作流；
- `__main__.py`：分派基础一致性 CLI。

CLI 只负责参数、编排、预期异常转换和获批准 IO。新的领域策略必须进入所属
核心模块，不能塞进 CLI 分支。

## 依赖方向

```text
models / hashing / json_utils
        ↓
validation → adapter → diff → history → business_review → evidence
                                                        ↓
                                         ai_review / expert_synthesis
                                                        ↓
                                                expert_review
                                                        ↓
                                              CLI entry modules

models / hashing ─────────────→ change_intent ──→ retrieval
models / lexical ───────────────────────────────→ retrieval
change_intent / retrieval / models ──────→ semantic_recommendation
evidence / change_intent / semantic_recommendation / models
                                           └────→ ai_review
adapter / ai_review / change_intent / retrieval /
semantic_recommendation / private_io ──────────→ governance_cli
```

核心模块不得反向导入 CLI。以下跨模块私有导入是当前技术债，不得继续扩散：

- `business_review.py` 使用 `history.py` 私有证据 helper；
- `expert_synthesis.py` 使用 `ai_review.py` 私有响应 helper；

下一次有真实复用需求时，提取命名明确的公共模块/API，并保留原安全测试；不在
没有需求时做全量重构。

## 放置规则

- 持久化合同放入聚焦的核心模块，并在 `contracts/` 增加匹配的版本化 Schema；
- 源格式差异集中在 `adapter.py`，不在领域模块散布原始 `metadata`/`subnodes`
  遍历；
- 确定性策略靠近它所约束的工件；
- 模型传输/配置放在 Provider 后；外发投影由 `evidence.py` 或所属综合边界负责；
- 文件系统和命令编排只放 Adapter/CLI 边界；
- 可复用输入只放 `tests/fixtures/fictional/`，不得使用真实或一致伪名化业务树；
- 用户可见命令或安全边界变化时同步更新 `README.md` 和聚焦的 `docs/`；
- 产品 AI 输出采用 sidecar/overlay；生产连接器或写入器需要独立任务和明确
  审批。

## 命名

- 模块、函数、参数和局部变量：`snake_case`；
- 公共合同类：`PascalCase`；
- 稳定常量和顺序表：`UPPER_SNAKE_CASE`；
- 私有 helper 和精确字段集：`_` 前缀；
- 稳定诊断码：大写领域前缀，例如 `BUSINESS_REVIEW_SOURCE_NOT_RESOURCE`；
- 版本标识同时说明工件与修订，例如 `tree-diff.v1`、
  `treeguard.snapshot-diff.v1`。

参考实现：`src/treeguard/models.py`、`diff.py`、`evidence.py`、
`semantic_recommendation.py`、`ai_cli.py`、`expert_review.py`。
