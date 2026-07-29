# TreeGuard Python 核心规范

这些规范描述当前真实存在的 Python 核心和六个 CLI。本文中的
“backend”不表示已经存在 Web 服务、数据库连接器、worker 或生产写入路径。

## 规则分类

### 永久安全与可信边界

- 确定性代码负责结构校验、版本检查、哈希、回放、安全门禁和状态迁移；
  模型输出始终是不可信输入。
- 历史变更只能作为证据，不能自动代表专家意图或 Gold 标签。
- 真实树、节点字段名、`VALUE`、专家文本、模型 trace、内部标识和凭据必须
  留在获批准的信任边界内。
- 删除 `VALUE`、替换 ID 或稳定化名不等于充分脱敏；外传前必须正向允许列表、
  严格脱敏和逐字节人工批准。
- 匹配的哈希或成功回放只证明给定来源下的一致性，不证明身份、签名、权威
  HEAD、发布批准或 Gold 资格。
- AI 只生成待审建议，最终裁决属于人工。

### Shadow MVP 临时限制

- 治理运行当前只接受 `resource` 树；`instance` 投影暂不生成 Patch。
- 产品运行只写 sidecar/overlay，不连接生产 Spring Boot/MongoDB，也不修改
  生产信息树。
- 上述限制在最小可行性验证后，按准确性、专家采纳率、误报、审查成本和
  可回放性复审。

### 当前仓库事实

- 当前确定性核心主要使用标准库；应用边界另外使用 FastAPI/Uvicorn 提供
  loopback 只读 Workbench API，通过文件、百炼 Provider 和暂定开发仿真集成；
- 当前没有数据库层、生产 Patch writer、日志框架或完整工程质量工具链；
- “当前事实”随源码演进重新核对，不能自动升级为永久产品政策。

## 规范索引

| 规范 | 何时阅读 |
|---|---|
| [目录结构](./directory-structure.md) | 新增模块、命令、合同或移动职责 |
| [开发数据边界](./development-data-boundary.md) | 写任务、research、fixture、诊断或跨环境工件 |
| [合同与确定性](./contracts-and-determinism.md) | 修改序列化、哈希、排序、回放或模型投影 |
| [持久化与集成](./persistence-and-integration.md) | 增加文件、HTTP、数据库或环境访问 |
| [错误处理](./error-handling.md) | 增加校验、错误码、异常转换或退出行为 |
| [CLI 输出与诊断](./cli-output-and-diagnostics.md) | 修改 stdout、报告、敏感输出或模型执行 |
| [新增需求意图、候选召回与语义推荐](./governance-intake-and-retrieval.md) | 修改 ChangeIntent、人工确认、全树召回、语义建议或治理 CLI |
| [只读 Workbench API](./workbench-api.md) | 修改 FastAPI、树视图 DTO、前端代理或工作台启动入口 |
| [质量规范](./quality-guidelines.md) | 每次实施与审查 |

## 开发前检查

1. 每次改动都读[质量规范](./quality-guidelines.md)。
2. 持久化任何上下文前读[开发数据边界](./development-data-boundary.md)。
3. 新建模块前读[目录结构](./directory-structure.md)。
4. 改 dataclass、Schema、`to_dict()`、字段集、枚举、排序、哈希或回放时读
   [合同与确定性](./contracts-and-determinism.md)。
5. 增加 IO 或配置时读[持久化与集成](./persistence-and-integration.md)。
6. 修改边界/CLI 时同时读[错误处理](./error-handling.md)和
   [CLI 输出与诊断](./cli-output-and-diagnostics.md)。
7. 编辑前搜索相关值、错误码、Schema 版本和 helper；多个合同同时存在于
   JSON Schema 与 Python。
8. `docs/architecture.md` 同时包含现状与目标架构。只有在 `src/treeguard/`
   找到实现后，才能写成已实现能力。

## 当前可靠验证

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -v
git diff --check
```

当前未配置 formatter、linter、type checker、coverage 门禁或第三方 JSON
Schema validator，不得声称它们已运行或通过。项目规范、任务和工作日志使用
中文；命令、协议字段和代码标识保持原样。
