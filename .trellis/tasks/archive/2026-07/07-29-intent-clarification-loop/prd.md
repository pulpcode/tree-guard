# 实现单轮意图澄清闭环

## Goal

在现有文件型新增需求治理纵切中补齐一次受约束的澄清回合：当 AI 意图草稿返回
`NEEDS_CLARIFICATION` 时，禁止直接进入检索；用户可提交一次自由文本回答，AI
基于原需求、原草稿和回答生成一份新的可审查意图，之后才能由人工确认或安全停止。

## What I already know

* 当前 `ChangeIntentDraft v1` 每份草稿最多包含一个
  `clarification_question`。
* 当前一键演示会为 `NEEDS_CLARIFICATION` 草稿自动生成
  `CONFIRM_FOR_RETRIEVAL`，这不符合产品门禁。
* MVP 每轮只提出一个问题，最多允许一轮澄清；一轮后仍需澄清时停止，不继续检索。
* MVP 不依赖现有信息树维护前端。初始需求允许父节点为空、节点类型和基数为
  `UNKNOWN`、值类型为空。
* 产品结果继续只写私有 sidecar，不修改生产信息树、MongoDB 或其他生产数据。

## Assumptions

* 澄清后的模型调用属于第二次意图编译；进入语义建议时，澄清路径最多发生三次
  顺序模型调用。
* 为保持现有 `ChangeIntentDraft v1` 兼容，新增澄清回答和澄清轮次合同，不修改
  已有合同字段。
* 澄清轮次制品内嵌并绑定初始草稿和回答，使后续确认、检索和回放仍可只读取一个
  “当前意图草稿”文件。

## Requirements

* 新增 `IntentClarificationAnswer v1`，保存被回答草稿哈希、回答原文、非认证回答者
  引用和记录时间。
* 新增 `IntentClarificationRound v1`，绑定原需求、快照、初始草稿、回答、模型来源、
  修订意图和确定性哈希。
* 只有 `NEEDS_CLARIFICATION` 的初始 `ChangeIntentDraft` 可以发起澄清。
* 澄清轮次固定为第一轮；修订意图不得再次进入第二轮澄清。
* 修订意图不再需要澄清时，可复用现有人工 action、确认、检索、建议、复核与回放。
* 修订意图仍需澄清时，状态保持安全停止，不能确认或检索。
* 未澄清的 `NEEDS_CLARIFICATION` 草稿不能直接
  `CONFIRM_FOR_RETRIEVAL`。
* 新增 CLI 澄清步骤，支持冻结模型输出文件和百炼 live 两种来源；live 必须在读取
  私有输入和联网前检查显式出域批准。
* 一键演示不得再静默越过澄清状态；离线固定案例继续保持无需澄清，live 或测试中的
  澄清案例必须显式经过澄清步骤或安全停止。
* 新增最小输入测试：父节点为空、节点类型和基数为 `UNKNOWN`、值类型为空。
* 所有新增完整制品使用现有私有文件读写规则，聚合 stdout 不输出需求、问题、回答、
  节点、路径、ID 或哈希。

## Acceptance Criteria

* [x] `READY_FOR_HUMAN_REVIEW` 初始草稿仍可按原流程确认。
* [x] `NEEDS_CLARIFICATION` 初始草稿直接确认返回固定错误且无输出文件。
* [x] 回答绑定错误草稿、回答为空、未知字段或非法时间时失败关闭。
* [x] 合法回答与冻结模型输出生成可确定性回放的澄清轮次。
* [x] 百炼澄清调用使用 JSON object 模式、有界输入、现有受控重试和安全错误语义。
* [x] 澄清后的完整意图可确认并进入全树候选检索。
* [x] 澄清后仍有问题时不能确认、不能进入检索。
* [x] 篡改内嵌初始草稿、回答、修订意图或来源哈希时回放失败。
* [x] 一键演示和既有完整测试套件无回归。
* [x] 新增离线、mock-live、权限、无覆盖和聚合输出测试。

## Definition of Done

* 相关单元、CLI 和演示测试已增加或更新。
* `uv sync --frozen` 通过。
* 已配置的完整 `unittest` 套件通过。
* `git diff --check` 通过。
* 未配置的 lint、typecheck、coverage 和 CI 不报告为已通过。
* README、架构或合同导航按实际行为更新。

## Decision (ADR-lite)

**Context**：现有意图草稿和确认合同已稳定使用，直接增加字段会破坏 v1 文件兼容；
同时下游需要从可信来源重放澄清过程。

**Decision**：保留 `ChangeIntentDraft v1`，新增一个内嵌初始草稿和回答的
`IntentClarificationRound v1`。确认阶段把初始草稿或已验证澄清轮次统一视为
“可审查意图来源”，但门禁禁止任何仍带追问的来源进入检索。

**Consequences**：澄清路径新增一次模型调用和一个私有制品；已有无澄清路径及其文件
保持兼容。若未来支持多轮，应新增后继合同版本，不在本任务提前实现通用会话框架。

## Out of Scope

* 第二轮及更多轮澄清。
* 现有信息树维护页面改造或新的 Web 页面。
* Spring Boot、MongoDB、版本接口或生产写入。
* 内网 Qwen 专用 HTTP Provider。
* embedding、混合召回、正式 Gold、效果指标和 Patch。
* 认证用户身份和权威 HEAD/分支选择。

## Technical Notes

* 主要涉及 `change_intent.py`、`ai_review.py`、`governance_cli.py`、`demo_cli.py`、
  `contracts/`、`tests/` 和行为文档。
* 复用现有严格 JSON、临时模型视图、模型输出禁止内部 ID、私有 `0600` 文件、
  不可覆盖发布、固定错误码和聚合 stdout 约定。
* 所有测试材料必须为外网独立构造的完全虚构内容。
