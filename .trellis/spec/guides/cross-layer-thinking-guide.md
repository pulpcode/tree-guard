# 跨层思考指南

## 当前真实流程

```text
tree export / decoded API envelope
  → adapter
  → immutable canonical tree
  → diff / history / business-version review
  → bounded evidence projection
  → optional model Provider
  → locally validated AI draft
  → expert-review state and replay
  → aggregate CLI report or approved private sidecar
```

未来 Spring Boot、MongoDB、search 和 Patch publication 还不是当前层，不能假装
它们已经存在。

## 每个边界要回答的问题

| 边界 | 必答问题 |
|---|---|
| Source → adapter | 接受什么 envelope/profile？未知字段、深度、身份、父子关系、基数如何处理？ |
| Adapter → canonical domain | 是否与调用者可变 JSON 脱离？node 身份和顺序是否确定？ |
| Canonical artifact → diff/review | 范围、版本序列、hash domain 和可信回放是否明确？ |
| Internal review → model | 是否为有界正向允许列表？真实字段名是否严格脱敏？引用是否临时？ |
| Provider → local draft | 是否本地校验精确字段、枚举、引用、大小、跨字段策略和来源绑定？ |
| AI draft → expert state | AI 是否只能建议？状态迁移和最终决定是否仍由专家控制？ |
| Domain → CLI/file | stdout 是否仅聚合？敏感输出是否显式、私有、原子且不覆盖？ |
| Review → product | 是否只写 sidecar/overlay？失败是否与生产状态隔离？ |

每条箭头都写清 input、output、owner、validation、error code 和禁止跨越字段。

## 双环境也是边界

```text
受保护材料
  → 最小正向允许列表
  → 严格脱敏（包括节点字段名）
  → 获授权人工审阅最终字节
  → 获批准外网合同/诊断
```

反向路径只允许外网开发代码和公开合同材料。外部工具不得接收真实树、真实字段
名、受保护源码、专家文本、原始日志、Prompt、trace 或稳定伪名。

在受保护环境调用 Web/MCP/插件前，先审查将发送的准确查询，删除内部事实并
改写为公开概念或完全虚构问题。不能安全改写时，只记录“需要内网核验”。
详见 `../backend/development-data-boundary.md`。

## 避免策略散落

- 源格式差异归 `adapter.py`；
- 确定性策略归 core，不归 CLI branch；
- 网络行为归 Provider；
- 模型数据由专用允许列表 projection 构造；
- 公开聚合与私有完整工件是不同产品；
- persistence/transport 不获得发布 Patch 的权限；
- 开发 check 代理可修外网仓库代码，不代表产品可修改生产信息树。

## 验证清单

- 追踪一个成功路径和每类失败跨越的全部边界；
- 确认合同/版本字段和错误分类 round trip 后仍一致；
- 重排无关源对象，输出仍确定；
- 篡改存储/模型工件，本地或可信来源回放必须拒绝；
- 使用 canary 证明真实字段名、路径、ID、文本、hash 和 credential 不进入
  聚合、模型或外网输出；
- 网络/文件部分失败不留下已发布部分状态；
- Shadow MVP 产品输出只进入 sidecar/overlay，未改变生产数据。
