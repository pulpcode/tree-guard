# 一键虚构 E2E 演示

## Goal

为 TreeGuard 增加一个可重复、可展示的一键虚构治理演示，使用仓库内完全虚构数据
贯通“意图草稿 → 人工确认 → 全树召回 → 语义建议 → 人工复核 → 可信回放”，
让当前文件型 Shadow MVP 不再只能通过单元测试或手工拼接多个 JSON 证明闭环。

## What I already know

* `treeguard-governance` 已实现 `draft`、`confirm`、`search`、`recommend`、
  `review-recommendation` 和 `replay-recommendation`。
* `tests/test_governance_cli.py` 已在临时目录贯通离线文件工作流，但仓库没有面向
  使用者的独立 E2E 样例包或一键入口。
* 当前只有完全虚构的信息树 fixture；意图模型输出、语义模型输出和人工 action
  主要由测试代码动态构造。
* 完整中间工件必须写入私有目录，stdout 只能包含固定状态和聚合结果。
* 演示不能声称虚构结果代表真实领域准确率，也不能生成 Overlay、Patch 或生产
  写入资格。

## Assumptions (temporary)

* MVP 先保证 `offline` 模式完全确定、无网络、可在外网直接运行。
* 百炼 live 模式可保留清晰扩展点，但不应阻塞 offline MVP。
* 演示必须调用正式领域/CLI 边界，不能复制另一套治理算法。
* 演示生成的人工决策必须明确标记为虚构演示输入，不能伪装成真实专家审批。

## Open Questions

* 无。

## Requirements (evolving)

* 提供一个稳定的一键入口和完全虚构输入。
* 独立入口固定为 `treeguard-governance-demo`，不把演示逻辑塞入正式治理 CLI。
* 必须显式传入 `--review-decision confirm|reject`；不提供固定自动审批。
* 支持 `--mode offline|bailian-live`。offline 是默认确定性基线；live 必须额外
  提供 `--external-data-approved`。
* 在新建私有运行目录中生成全部中间工件，不覆盖已有文件。
* 复用现有合同、哈希、回放和私有 IO，不在演示层复制领域策略。
* 最终 stdout 只输出步骤状态、固定枚举和聚合计数，不输出虚构节点文本、路径、
  稳定 ID、hash 或中间工件内容。
* 任一步失败时返回稳定错误，不能留下被误认为完成的最终记录。
* 输出明确声明 `fictional_demo=true`、`semantic_approval=false`、
  `patch_eligible=false`、`gold_eligible=false`。

## Acceptance Criteria (evolving)

* [x] 一个命令可在无网络环境贯通六个治理步骤并完成可信回放。
* [x] 连续两次使用不同空目录运行得到相同业务状态和动作。
* [x] 已存在、公开权限、symlink 或不安全输出目录 fail-closed。
* [x] 聚合 stdout 不含 fixture 节点 ID、路径、文本、hash 或凭据。
* [x] 演示复用正式合同；篡改任一冻结模型输出或来源工件时失败。
* [x] 演示结果明确为虚构、非 Gold、非审批、非 Patch。
* [x] `--review-decision` 缺失或非法时拒绝；confirm 与 reject 均可回放。
* [x] live 缺出域批准时在创建目录、读取数据和网络调用前拒绝。

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* `uv sync --frozen`、已配置的 `unittest` 和 `git diff --check` 通过
* 未配置的 lint、typecheck、coverage 和第三方 Schema validator 不宣称已通过
* README/运行文档同步更新
* 明确 rollout、rollback 和内网核验项

## Out of Scope (explicit)

* 真实信息树、真实需求、真实专家或模型响应
* 内网 Qwen HTTP Provider
* embedding、混合召回和效果评测
* Web UI、Spring Boot/MongoDB、Overlay、Patch 和生产写入
* 使用演示结果宣称真实业务准确率或专家效率

## Technical Notes

* 主要入口：`src/treeguard/governance_cli.py`、`src/treeguard/private_io.py`。
* 参考测试：`tests/test_governance_cli.py`。
* 虚构树：`tests/fixtures/fictional/tree_export.json`。
* 运行时保持标准库依赖，不新增 shell-only 或第三方运行时要求。

## Research References

* [`research/demo-entry-and-review.md`](research/demo-entry-and-review.md) — 推荐独立
  console script、全新私有运行目录和显式 reviewer 决策参数。

## Feasible Approaches

### A. 独立 `treeguard-governance-demo`（推荐）

专用演示 CLI 创建虚构输入并编排正式六步命令；安装后可运行，offline 可回归，
live 复用现有 Provider。

### B. `treeguard-governance demo`

入口较少，但把演示数据和策略混入正式治理 CLI。

### C. shell/example 脚本

实现较快，但不可移植、安装后不可用，也容易复制安全 IO。

## Decision (ADR-lite)

**Context**：一键演示既要保留人工门禁的表达，又要适合 CI、回放和面试现场运行。
交互式输入不稳定，固定自动确认又容易被误解为系统审批。

**Decision**：采用独立 `treeguard-governance-demo` console script，并要求显式
`--review-decision confirm|reject`。命令创建全新 `0700` 运行目录，生成完全虚构
输入，以正式治理 CLI 完成六步编排。offline 使用确定性虚构模型输出；
bailian-live 复用正式 Provider 和出域批准门。

**Consequences**：演示可以一条命令自动回归，同时明确“决策由调用参数提供”。
首版不在演示入口支持 revise；正式治理 CLI 仍支持完整修订合同。演示结果始终是
非 Gold、非语义审批、非 Patch。

## Implementation Plan

1. [x] 增加专用 demo fixture builder、运行目录门禁和单 JSON 聚合报告。
2. [x] 编排正式治理 CLI 的 draft、confirm、search、recommend、review 和 replay。
3. [x] 增加 offline、confirm/reject、live approval/Mock、失败清理和泄漏测试。
4. [x] 增加 console script，并更新 README、冒烟文档和适用 Trellis 规范。

## Implementation Outcome

* `treeguard-governance-demo` 默认以 offline 模式运行；`--review-decision` 必填。
* 运行目录只允许全新路径，以 `0700` 创建；全部 JSON 通过公共私有 IO 以 `0600`
  不可覆盖发布。
* 六步全部成功并可信回放后才发布 `12-demo-completion.json`；失败可保留私有前序
  工件，但不会留下完成标志。
* `bailian-live` 复用正式意图和语义 Provider；缺少出域批准时在任何文件或网络
  副作用前拒绝。
* 聚合报告仅含固定状态、布尔门禁和计数，明确标记虚构、非 Gold、非审批、
  非 Patch。

## Verification Evidence

* `UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen`：通过。
* `UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen python -B -m unittest discover -s tests -v`：
  153 项通过。
* `UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen python -B -m unittest tests.test_demo_cli -v`：
  9 项通过。
* `git diff --check`：通过。
* 未配置 formatter、linter、type checker、coverage、CI 和第三方 Schema validator，
  不宣称已验证。

## Rollout / Rollback

* Rollout：先在外网或内网无网络环境运行 offline confirm/reject；需要时再用 Mock
  验证 live，真实百炼冒烟必须单独显式批准。
* Rollback：移除 `treeguard-governance-demo` console script、`demo_cli.py` 及其
  测试/文档即可；正式六步治理 CLI 和领域合同未被修改。

## Protected-environment Verification

* 当前不需要真实信息树、真实字段或内部源码即可验证演示闭环。
* 尚未执行真实百炼网络冒烟；该步骤只允许使用内置虚构输入和显式批准。
* 内网 Qwen Provider、真实领域效果、专家效率和 Gold 评测仍不在本任务结论内。
