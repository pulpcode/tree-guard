# 内网仓库与 Qwen 适配

这组适配用于在受保护环境中把 TreeGuard 工作台连接到真实信息树仓库和内网
OpenAI-compatible Qwen。它仍是只读旁路：只读取信息树并写 TreeGuard 私有
sidecar，不调用生产写接口，也不修改生产信息树。

## 运行配置

仓库与 Qwen 地址只能由服务端配置提供，浏览器不能提交。仓库模式/地址使用进程
环境；Qwen 配置可使用进程环境或私有 `.env`。`.env` 必须保持 Git ignore、
当前用户所有且权限为 `0600`。

```bash
export TREEGUARD_WORKBENCH_REPOSITORY_MODE=INTERNAL
export TREEGUARD_WORKBENCH_REPOSITORY_URL=http://10.0.0.8:8080
```

私有 `.env`：

```dotenv
TREEGUARD_QWEN_BASE_URL=http://10.0.0.9:8000/v1
TREEGUARD_QWEN_MODEL=qwen3.6
```

上面的地址完全虚构，仅说明格式。HTTP 地址必须显式带端口；允许私有/loopback
IP、单标签内网主机名以及 `.internal`、`.local`、`.lan` 名称。客户端忽略系统
代理并拒绝重定向。Qwen 不使用 API Key，也不发送 `Authorization`。

启动工作台：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache \
  uv run --frozen treeguard-workbench --port 8000
```

页面的模型模式选择“内网 Qwen 真实模型”。该模式属于受保护环境，不复用百炼的
出域批准勾选，也不会在配置缺失或调用失败时自动回退到百炼或 Mock。

## 仓库接口映射

真实只读 Adapter 使用以下精确路径：

| 能力 | 路径 | 关键输入 |
|---|---|---|
| 分类平铺树 | `/api/v1/category/query-list` | `leaf_only=false` |
| 分类下资源当前/默认版本 | `/api/v1/resource/list` | `category_id`、`page_no`、`page_size` |
| 业务版本列表 | `/api/v1/resource/version-info` | `resource_id` |
| 完整信息树 | `/api/v1/resource/tree` | `resource_id + version`，或 `id` |

资源列表固定从 `page_no=1` 开始，首版使用 `page_size=50`，依据
`metadata.total` 逐页读取。空页、重复页、总数漂移、重复 `resource_id/id` 或
超过有界上限都会失败关闭。`latest`、`name`、`tag` 不参与首版请求。

Adapter 只读取业务所需字段，忽略审计字段和其他无关字段，不把上游完整 DTO
带入模型。完整树仍交给 `adapt_tree_document()`；模型接收的是现有临时引用和
有界候选投影，不接收全量原始响应。

## ID 与版本规则

- `resource_id`（完整树中的 `map_id`）跨业务版本稳定。
- `id` 唯一标识一个业务版本的信息树。
- 对同一当前/默认版本，`resource/list.id`、`version-info.id` 与完整树
  `metadata.id` 必须一致。
- 版本接口返回顺序不可信。Adapter 对类似 `V0.0.0.0J0.1.0` 的版本先比较
  中间字母前的数字段，再比较字母后的数字段；前缀和中间字母不参与大小比较。
- 数字排序键相同但字符串不同的版本被视为歧义并拒绝，排序后的最后一个版本才是
  最新版本。
- `resource/list` 中的版本是当前/默认版本，可以指向排序后的任一历史版本。
  Workbench 为兼容现有合同继续使用 `head_version/is_head` 字段名，但其含义是
  当前/默认指针，不是最新版本。

直接版本记录选择器已确认为 `/api/v1/resource/tree?id=...`；
`resource_id + version` 与 `id` 都是受支持的只读查询方式。

## Qwen 请求合同

Qwen 调用固定使用：

```json
{
  "stream": false,
  "temperature": 0,
  "response_format": {"type": "json_object"},
  "chat_template_kwargs": {"enable_thinking": false}
}
```

意图整理、一次澄清、候选语义比较、版本 AI 初审和专家思考整理继续使用现有本地
严格输出合同。模型响应始终是不可信输入，最多顺序尝试两次；合同失败不会产生审批、
Gold、Patch 或生产写入资格。

若启用工作台模型诊断，页面可显示实际 system/user 消息和
`message.content`，但不会显示或推测隐藏思考链。诊断内容可能包含真实业务语义，
只能在受保护环境查看，不能复制到外网。

## 外网测试能证明什么

仓库测试使用完全虚构的四接口响应，Qwen 测试使用进程内虚构 transport，不访问
真实内网。它们可以证明：

- 查询参数、分页、版本排序、ID 绑定和树适配逻辑符合当前合同；
- Qwen 请求没有认证头，并使用正确的嵌套关闭思考字段；
- 工作台能显式区分 simulator、百炼和 Qwen。

它们不能证明真实主机可达、错误信封完全兼容、模型一定遵守 JSON Mode，也不能
证明领域语义效果。最终仍需在内网用非敏感测试树完成一次只读冒烟。
