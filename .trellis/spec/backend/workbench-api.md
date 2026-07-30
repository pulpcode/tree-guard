# 只读 Workbench API

## Scenario：Clean-room 信息树浏览纵切

### 1. Scope / Trigger

修改 `workbench.py`、`web.py`、`workbench_cli.py`、`web/`，或新增浏览器可见树
字段时适用。本场景允许读取暂定 loopback 仿真仓库，或在受保护环境显式读取真实
四接口只读 Adapter；两者都不获得治理状态迁移、生产写权限或数据库直连。

治理操作属于独立的 [Workbench 治理 API](./workbench-governance-api.md) 场景；
不得为了治理而扩大本文件定义的树读取 DTO。

### 2. Signatures

启动入口：

```text
treeguard-workbench [--port 1..65535]
```

HTTP：

```text
GET /api/v1/health
GET /api/v1/categories
GET /api/v1/resources?category_id=<id>
GET /api/v1/resources/{resource_id}/versions
GET /api/v1/resources/{resource_id}/tree?version=<version>
```

环境：

```text
TREEGUARD_WORKBENCH_REPOSITORY_URL
TREEGUARD_WORKBENCH_REPOSITORY_MODE   # SIMULATOR | INTERNAL
```

两个环境项只在服务端读取。模式默认 `SIMULATOR`，URL 默认
`http://127.0.0.1:8765`，并受 `RepositoryClientConfig` 的显式 loopback HTTP
端口门禁约束。`INTERNAL` 使用 `InternalRepositoryConfig`，只允许受保护环境地址，
四类真实接口的分页、版本排序和 ID 一致性由 `InternalRepositoryClient` 负责。
响应中的历史字段 `head_version/is_head` 表示仓库当前/默认版本指针；该指针可以
指向历史版本。最新版本只能由版本列表最大 `position` 判定，前端必须分别显示
“默认”和“最新”。
前端开发代理可使用
`TREEGUARD_WEB_API_URL` 指向本机 Workbench API；它不是浏览器运行时配置，也不能
控制后端仓库目标。

### 3. Contracts

`WorkbenchService` 是 FastAPI 和仓库客户端之间的应用层。HTTP 层不得通过
subprocess 执行 CLI，也不得复制 Adapter/Core 策略。

树响应固定为：

```text
schema_version = workbench-tree-view.v1
tree_version
node_count
root_refs[]
nodes[]:
  ref
  parent_ref
  child_refs[]
  name
  label
  kind
  value_type
  cardinality
  order
  breadcrumb[]
```

`ref` 是一次响应内按根优先 DFS 生成的 `N000001` 形式引用。禁止返回稳定
`node_id`、tree/resource record ID、VALUE、constraints、remark、extension、
metadata extra、source route、source revision、snapshot/node hash 或文件路径。
不得用 `CanonicalTree.to_dict()` 生成浏览器响应。

所有响应设置：

```text
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

FastAPI docs/OpenAPI 在该本地 Shadow 入口关闭。Uvicorn 固定监听
`127.0.0.1`，关闭 access log，避免 URL 中的分类/资源选择器进入普通日志。

### 4. Validation & Error Matrix

| 条件 | HTTP / error code |
|---|---|
| query 缺失、空值或超长 | 422 / `WORKBENCH_REQUEST_INVALID` |
| 仓库 HTTP、合同、身份或连接失败 | 502 / 原固定 `REPOSITORY_*` 或 `INTERNAL_REPOSITORY_*` code |
| CanonicalTree 为空或不合格 | 409 / `WORKBENCH_TREE_NOT_AVAILABLE` |
| 树存在环、缺失父子引用或不可达节点 | 409 / `WORKBENCH_TREE_RELATION_INVALID` |
| 仓库地址不是显式 loopback HTTP 端口 | 启动失败 / `REPOSITORY_SIMULATOR_BASE_URL_INVALID` |
| 仓库模式未知或 INTERNAL 地址不合格 | 启动失败 / `WORKBENCH_REPOSITORY_MODE_INVALID` 或 `INTERNAL_REPOSITORY_BASE_URL_INVALID` |

错误响应只包含：

```json
{
  "schema_version": "workbench-error.v1",
  "error_code": "FIXED_CODE",
  "message": "Request could not be completed."
}
```

不得返回异常 message、URL、响应 body、路径、节点或 traceback。

### 5. Good/Base/Bad Cases

- Good：2,001 节点虚构树转换为根优先轻量视图；前端搜索只保留命中和祖先，
  实际可见 DOM 行保持有界，右侧详情使用同一临时引用。
- Base：未选择版本时前端不请求树，显示空状态；刷新和选择不产生任何工件。
- Bad：浏览器直接调用仿真仓库/模型，允许页面提交仓库 URL，返回
  `CanonicalTree.to_dict()`，或把只读页面写成生产治理工作台。

### 6. Tests Required

- `build_tree_view()`：2,001 节点计数、根优先引用、允许列表精确字段集；
- canary：稳定 ID、hash、metadata、constraints 和 route 不出现在序列化响应；
- API：五类成功路由、`no-store`、`nosniff` 和固定错误响应；
- Provider/仓库错误：只保留 `.code`，底层 message 不泄漏；
- 前端 `buildTreeData()`：父子关系、不可达节点拒绝；
- 前端 `searchTree()` / `filterTreeData()`：名称/label 匹配、祖先展开、命中路径
  有界；
- 浏览器冒烟：2,001 节点加载，搜索尾部节点后树只显示命中路径，详情同步。

### 7. Wrong vs Correct

Wrong：

```python
@app.get("/tree")
def tree():
    return canonical_tree.to_dict()
```

这会把稳定 ID、哈希、额外字段和内部结构直接扩大到浏览器边界。

Correct：

```python
@app.get("/api/v1/resources/{resource_id}/tree")
def tree_view(resource_id: str, version: str):
    return workbench_service.tree_view(resource_id, version=version)
```

`WorkbenchService` 从 `CanonicalTree` 重新构造独立正向允许列表，FastAPI
`response_model` 再拒绝意外额外字段。
