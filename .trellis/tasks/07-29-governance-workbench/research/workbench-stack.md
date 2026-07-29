# 工作台组件与边界研究

日期：2026-07-29

## 问题

为 TreeGuard 的 2,000+ 节点只读治理工作台选择主树组件和最小前后端边界。

## 范围

- 仅比较公开组件能力与本仓库已批准的虚构仿真合同；
- 不使用或记录真实信息树、节点字段、模型流量或内部接口事实；
- 本研究只支持 Shadow MVP 技术选择，不代表生产性能验收。

## 公开依据

- Ant Design Tree：
  <https://ant.design/components/tree/>
- Ant Design 开源仓库：
  <https://github.com/ant-design/ant-design>
- jsMind 文档：
  <https://hizzgdev.github.io/jsmind/docs/en/>
- jsMind 配置：
  <https://hizzgdev.github.io/jsmind/docs/en/options/>
- FastAPI 文档：
  <https://fastapi.tiangolo.com/>
- Vite 后端集成：
  <https://vite.dev/guide/backend-integration>

## 结论

- Ant Design Tree 提供受控展开、搜索高亮所需的自定义标题、虚拟滚动、异步加载和
  指定节点滚动能力，更适合精确路径定位、候选联动和企业审查表单。
- jsMind 强项是画布缩放、拖动和思维导图编辑；官方文档没有提供与 Ant Design
  Tree 对等的 DOM 虚拟滚动合同。把完整 2,000+ 节点作为主导航会增加布局、定位和
  React 状态同步成本。
- MVP 应只使用 Ant Design Tree。未来若面试展示或局部语义关系确有价值，可以将
  jsMind 限制为约 20–50 节点的只读局部投影，不能作为源数据或编辑入口。
- 浏览器不应直接调用仓库或模型；FastAPI 只提供允许列表化界面 DTO，复用既有
  Python Adapter/Core。开发时由 Vite proxy 消除浏览器对后端地址的硬编码。
- 第一纵切先验证目录、版本和 2,001 节点树浏览；AI 长任务、operation polling 和
  私有 sidecar Web 操作留到后续任务，避免同时引入队列和治理状态迁移风险。

## 限制

- 组件最终性能仍需在目标内网浏览器和实际获批准数据规模上验证。
- 真实仓库字段、认证、分页和错误合同尚未提供；当前只能适配
  `PROVISIONAL_SIMULATOR_CONTRACT`。
- 本研究没有批准任何真实数据外发，也没有改变 Shadow 只读边界。
