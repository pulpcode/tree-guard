# 协议级仿真架构研究

## 问题

在真实内网接口样例暂缺时，如何为 TreeGuard 提供可替换、可测试且不污染生产依赖的
OpenAI-compatible 与信息树仓库仿真环境。

## 范围与日期

- 日期：2026-07-29
- 范围：只研究本外网仓库已有实现和 Python 标准库可行方案。
- 不包含真实接口、真实数据、内部地址、凭据或受保护源码。

## 仓库依据

- `pyproject.toml`：当前运行时依赖为空。
- `src/treeguard/ai_review.py`：HTTP 客户端基于 `urllib`，模型能力通过严格合同校验。
- `src/treeguard/adapter.py`：已能适配直接树导出和 `data` 信封。
- `src/treeguard/demo_cli.py`：已有完全虚构治理场景和确定性模型输出。
- `tests/`：主要用注入 transport 和标准库 `unittest`，没有现成 HTTP 测试服务。

## 可行方案

### A：标准库协议路由器 + loopback Server + 最小客户端（推荐）

以纯函数处理请求并返回状态、头和 JSON/字节响应；`ThreadingHTTPServer` 只负责
loopback HTTP 壳，测试可直接调用路由器，也可启动随机端口做集成验证。

优点：零运行时依赖、确定性、网络测试可选、真实 Adapter 易替换。缺点：需要手工
实现少量路径和请求限制，不适合发展为通用 Mock 平台。

### B：独立 FastAPI 仿真服务

优点：OpenAPI、路由和交互文档成熟。缺点：给当前零依赖核心增加新依赖和第二套
应用框架；在真实合同尚未到达前容易过度固化暂定 API。

### C：只提供静态 JSON fixture

优点：最小。缺点：不能验证路径、查询、HTTP 状态、认证头、超时、响应信封和批量
编排，无法承担 Provider/Adapter 开发环境。

## 结论

采用 A。把纯函数场景和合同作为唯一事实来源，HTTP Server 只是可删除的开发壳。
第一版只做支撑当前治理纵切的能力，不实现通用代理、录制回放、管理 UI 或生产部署。
所有模拟响应标记为 `PROVISIONAL_SIMULATOR_CONTRACT`，真实样例到达后由薄 Adapter
吸收差异。

## 限制

仿真只能验证协议、确定性、安全门禁和工程编排，不能证明内网模型质量、网络环境、
真实召回率或生产兼容性。
