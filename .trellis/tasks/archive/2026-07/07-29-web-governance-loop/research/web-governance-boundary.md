# Web 治理边界研究

## 问题

如何把既有文件型治理闭环接入 React + FastAPI，同时保持确定性、隐私、可回放和
Shadow MVP 旁路边界。

## 仓库依据

- `src/treeguard/governance_cli.py` 已按七个命令编排现有 Core/Provider，但参数和
  输出围绕私有文件，不适合作为 Web 内部 API。
- `src/treeguard/change_intent.py`、`retrieval.py` 和
  `semantic_recommendation.py` 已公开所需的内存构造、校验和回放函数。
- `src/treeguard/ai_review.py` 已公开百炼与 loopback 仿真的意图、澄清和语义
  Provider。
- `src/treeguard/private_io.py` 已提供不可覆盖的私有 JSON 发布能力。

## 可选方式

### A. FastAPI 调用治理 CLI subprocess

实现快，但把 CLI 文件路径、退出码和 stdout 协议变成应用层内部接口，也容易复制
临时文件与错误转换。违反现有“HTTP 层不得 subprocess 调 CLI”的规范。

### B. 浏览器保存完整治理工件

无服务端状态，但会把稳定 ID、hash、需求、模型和专家内容扩大到浏览器边界；
刷新、篡改与回放可信来源也更难控制，不可接受。

### C. Web 应用服务编排现有 Core/Provider（采用）

服务端持有可信对象并私有发布正式工件；浏览器只看独立允许列表。模型调用由有界
operation 状态承载，人工动作继续进入既有确定性状态机。

## 结论与限制

采用 C。首版 operation registry 为单进程内存实现，足够支持本地 Shadow MVP 和
浏览器刷新，不宣称支持服务重启恢复、多 worker 或生产级队列。后续若需要生产化，
应保持 operation 合同不变，再替换 registry/storage 实现。
