# 虚构 E2E 演示入口与复核方式

## 问题

如何在不复制治理算法、不伪造真实人工审批、并保持可自动回归的前提下，为当前六步
文件工作流提供一键演示？

## 范围

* 日期：2026-07-29
* 只依据当前外网仓库的 CLI、私有 IO、虚构 fixture、测试和项目规范。
* 不使用外部查询、真实信息树、真实字段名、专家文本或模型响应。

## 仓库依据

* `pyproject.toml` 使用 Python console script 暴露四个现有入口。
* `src/treeguard/governance_cli.py` 是六个治理命令的正式应用边界。
* `src/treeguard/private_io.py` 提供不可覆盖的 `0600` JSON 发布。
* `tests/test_governance_cli.py` 已使用 `redirect_stdout` 在进程内调用正式 CLI，
  并从前序输出生成哈希绑定 action。
* 当前没有 `scripts/`、`examples/` 或安装后可用的演示入口。

## 入口方案

### A. 独立 Python console script（推荐）

增加 `treeguard-governance-demo`，由专用 `demo_cli.py` 创建虚构输入并按顺序调用
正式治理 CLI。它可以在安装后运行、使用标准库、集中控制安全 stdout，并避免把
演示策略塞入正式治理命令。

代价是需要一个很薄的编排层，并为运行目录、步骤失败和最终报告增加测试。

### B. `treeguard-governance demo` 子命令

入口较少，但会把虚构数据生成、演示 reviewer 和六步编排混入正式治理 CLI，扩大
已有大文件和错误分支，不符合当前模块所有权规范。

### C. 仓库 shell/example 脚本

实现快，但安装后不可用、跨平台较差，并容易复制 JSON 写入和错误处理。它更适合
文档片段，不适合作为稳定展示入口。

## 人工复核方案

### 1. 显式命令参数（推荐）

要求调用者传入 `--review-decision confirm|reject`，由演示层生成
`UNVERIFIED_FILE_ASSERTION` 的虚构 action。它非交互、可测试、可回放，并能明确
证明决策来自本次命令，而不是系统自动审批。

`revise` 需要额外结构化内容，首版不在一键入口中自动编造；正式六步 CLI 仍完整
支持修订。

### 2. 交互式选择

现场体验更直观，但不利于 CI、重放和失败测试，还需要定义 stdin/TTY/取消行为。

### 3. 固定自动确认

最短，但最容易让演示被误解为 AI 自动批准，违背 TreeGuard 的人工门禁表达。

## 运行模式

* `offline`：使用代码中完全虚构、确定性的模型输出，必须作为默认与回归基线。
* `bailian-live`：复用正式百炼 Provider，只允许在显式
  `--external-data-approved` 下发送同一虚构投影；网络失败不得留下最终记录。
* 内网 Qwen Provider 仍是独立任务，不能借演示入口臆造内部 URL 或认证。

## 结论

采用独立 console script、全新 `0700` 运行目录、正式治理 CLI 编排和显式
`--review-decision`。MVP 同时定义 offline 与 bailian-live 的接口，但验收基线以
offline 确定性运行为主；live 通过 Mock 验证调用与失败边界，真实网络冒烟单独执行。

## 限制

* 演示只能证明工程合同和工作流可运行，不能证明真实领域质量。
* 命令参数表达的是虚构 reviewer 输入，不是身份认证或专家语义审批。
* 一键入口不取代正式逐步 CLI，后者仍用于真实受保护环境的人工审查。
