import {
  CheckCircleOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Divider,
  Empty,
  Input,
  Result,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Typography,
} from "antd";

import {
  clarifyGovernanceCase,
  createGovernanceCase,
  fetchGovernanceCase,
  fetchGovernanceOperation,
  reviewGovernanceIntent,
  reviewGovernanceRecommendation,
  type GovernanceCase,
  type GovernanceModelMode,
  type GovernanceOperation,
  type TreeViewNode,
  WorkbenchAPIError,
} from "./api";

interface GovernancePanelProps {
  resourceId?: string;
  version?: string;
  selectedNode?: TreeViewNode;
}

const RUNNING_STATUSES = new Set(["PENDING", "RUNNING"]);
const RUNTIME_REF = /^(?:CASE|OP)_[A-Za-z0-9]+$/;

function errorCode(error: unknown): string {
  return error instanceof WorkbenchAPIError
    ? error.code
    : "WORKBENCH_REQUEST_FAILED";
}

function GovernancePanel({
  resourceId,
  version,
  selectedNode,
}: GovernancePanelProps) {
  const [requirementText, setRequirementText] = useState(
    "为虚构博物馆藏品目录记录陈列高度。",
  );
  const [useSelectedParent, setUseSelectedParent] = useState(false);
  const [nodeKind, setNodeKind] = useState<
    "CONCEPT" | "PROPERTY" | "UNKNOWN"
  >("UNKNOWN");
  const [valueType, setValueType] = useState<string>();
  const [cardinality, setCardinality] = useState<
    "SINGLE" | "MULTIPLE" | "UNKNOWN"
  >("UNKNOWN");
  const [modelMode, setModelMode] =
    useState<GovernanceModelMode>("SIMULATOR_LIVE");
  const [externalApproved, setExternalApproved] = useState(false);
  const [caseRef, setCaseRef] = useState<string | undefined>(() =>
    runtimeRefFromQuery("case"),
  );
  const [operationRef, setOperationRef] = useState<string | undefined>(() =>
    runtimeRefFromQuery("operation"),
  );
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [reviewerReasoning, setReviewerReasoning] = useState("");
  const previousSelection = useRef<string | undefined>(undefined);

  const operation = useQuery({
    queryKey: ["governance-operation", operationRef],
    queryFn: () => fetchGovernanceOperation(operationRef!),
    enabled: Boolean(operationRef),
    refetchInterval: (query) =>
      RUNNING_STATUSES.has(query.state.data?.status ?? "") ? 450 : false,
  });
  const governanceCase = useQuery({
    queryKey: ["governance-case", caseRef],
    queryFn: () => fetchGovernanceCase(caseRef!),
    enabled: Boolean(caseRef),
    refetchInterval: () =>
      RUNNING_STATUSES.has(operation.data?.status ?? "") ? 500 : false,
  });

  useEffect(() => {
    if (
      operation.data &&
      !RUNNING_STATUSES.has(operation.data.status)
    ) {
      void governanceCase.refetch();
    }
  }, [governanceCase.refetch, operation.data]);

  useEffect(() => {
    if (!resourceId || !version) {
      return;
    }
    const selection = `${resourceId}\u0000${version}`;
    if (previousSelection.current === undefined) {
      previousSelection.current = selection;
      return;
    }
    if (previousSelection.current !== selection) {
      previousSelection.current = selection;
      setCaseRef(undefined);
      setOperationRef(undefined);
      setClarificationAnswer("");
      setReviewerReasoning("");
      setExternalApproved(false);
    }
  }, [resourceId, version]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (caseRef) {
      url.searchParams.set("case", caseRef);
    } else {
      url.searchParams.delete("case");
    }
    if (operationRef) {
      url.searchParams.set("operation", operationRef);
    } else {
      url.searchParams.delete("operation");
    }
    window.history.replaceState(null, "", url);
  }, [caseRef, operationRef]);

  const acceptOperation = (next: GovernanceOperation) => {
    setCaseRef(next.case_ref);
    setOperationRef(next.operation_ref);
  };

  const createCase = useMutation({
    mutationFn: () =>
      createGovernanceCase({
        resource_id: resourceId!,
        version: version!,
        requirement_text: requirementText.trim(),
        proposed_parent_ref:
          useSelectedParent && selectedNode ? selectedNode.ref : null,
        node_kind_hint: nodeKind,
        value_type_hint: valueType ?? null,
        cardinality_hint: cardinality,
        model_mode: modelMode,
        external_data_approved:
          modelMode === "BAILIAN_LIVE" && externalApproved,
      }),
    onSuccess: acceptOperation,
  });
  const clarify = useMutation({
    mutationFn: () =>
      clarifyGovernanceCase(caseRef!, clarificationAnswer.trim()),
    onSuccess: acceptOperation,
  });
  const reviewIntent = useMutation({
    mutationFn: (decision: "CONFIRM" | "REJECT") =>
      reviewGovernanceIntent(caseRef!, decision),
    onSuccess: acceptOperation,
  });
  const reviewRecommendation = useMutation({
    mutationFn: (decision: "CONFIRM" | "REJECT") =>
      reviewGovernanceRecommendation(
        caseRef!,
        decision,
        reviewerReasoning.trim() || null,
      ),
    onSuccess: acceptOperation,
  });

  const latestError =
    createCase.error ??
    clarify.error ??
    reviewIntent.error ??
    reviewRecommendation.error ??
    operation.error ??
    governanceCase.error;
  const currentCase = governanceCase.data;
  const busy =
    createCase.isPending ||
    clarify.isPending ||
    reviewIntent.isPending ||
    reviewRecommendation.isPending ||
    RUNNING_STATUSES.has(operation.data?.status ?? "");
  const step = currentStep(currentCase);
  const displayedModelMode = currentCase?.model_mode ?? modelMode;

  const reset = () => {
    setCaseRef(undefined);
    setOperationRef(undefined);
    setClarificationAnswer("");
    setReviewerReasoning("");
    setExternalApproved(false);
  };

  return (
    <Card
      className="panel-card governance-card"
      title={
        <Space>
          <RobotOutlined />
          <span>AI 治理闭环</span>
        </Space>
      }
      extra={
        <Tag color={displayedModelMode === "BAILIAN_LIVE" ? "blue" : "green"}>
          {displayedModelMode === "BAILIAN_LIVE"
            ? "百炼真实模型"
            : "本地模型仿真"}
        </Tag>
      }
    >
      <Steps
        size="small"
        current={step}
        items={[
          { title: "描述需求" },
          { title: "确认意图" },
          { title: "比较候选" },
          { title: "专家复核" },
        ]}
      />

      {!caseRef ? (
        <IntakeForm
          requirementText={requirementText}
          setRequirementText={setRequirementText}
          useSelectedParent={useSelectedParent}
          setUseSelectedParent={setUseSelectedParent}
          selectedNode={selectedNode}
          nodeKind={nodeKind}
          setNodeKind={setNodeKind}
          valueType={valueType}
          setValueType={setValueType}
          cardinality={cardinality}
          setCardinality={setCardinality}
          modelMode={modelMode}
          setModelMode={(mode) => {
            setModelMode(mode);
            setExternalApproved(false);
          }}
          externalApproved={externalApproved}
          setExternalApproved={setExternalApproved}
          disabled={!resourceId || !version}
          submitting={createCase.isPending}
          onSubmit={() => createCase.mutate()}
        />
      ) : governanceCase.error && !currentCase ? (
        <Result
          status="warning"
          title="运行时 case 已不可用"
          subTitle="Workbench API 重启后不会从 sidecar 自动恢复内存状态；私有工件仍保留。"
          extra={<Button onClick={reset}>重新发起</Button>}
        />
      ) : (
        <CaseBody
          value={currentCase}
          busy={busy}
          operation={operation.data}
          clarificationAnswer={clarificationAnswer}
          setClarificationAnswer={setClarificationAnswer}
          reviewerReasoning={reviewerReasoning}
          setReviewerReasoning={setReviewerReasoning}
          onClarify={() => clarify.mutate()}
          onReviewIntent={(decision) => reviewIntent.mutate(decision)}
          onReviewRecommendation={(decision) =>
            reviewRecommendation.mutate(decision)
          }
          onReset={reset}
        />
      )}

      {latestError && (
        <Alert
          className="governance-error"
          type="error"
          showIcon
          title="治理请求未能完成"
          description={`错误码：${errorCode(latestError)}`}
        />
      )}
      {operation.data?.status === "FAILED" && (
        <Alert
          className="governance-error"
          type="error"
          showIcon
          title="模型或本地合同校验失败"
          description={`错误码：${operation.data.error_code ?? "WORKBENCH_OPERATION_FAILED"}`}
        />
      )}
    </Card>
  );
}

interface IntakeFormProps {
  requirementText: string;
  setRequirementText: (value: string) => void;
  useSelectedParent: boolean;
  setUseSelectedParent: (value: boolean) => void;
  selectedNode?: TreeViewNode;
  nodeKind: "CONCEPT" | "PROPERTY" | "UNKNOWN";
  setNodeKind: (value: "CONCEPT" | "PROPERTY" | "UNKNOWN") => void;
  valueType?: string;
  setValueType: (value?: string) => void;
  cardinality: "SINGLE" | "MULTIPLE" | "UNKNOWN";
  setCardinality: (
    value: "SINGLE" | "MULTIPLE" | "UNKNOWN",
  ) => void;
  modelMode: GovernanceModelMode;
  setModelMode: (value: GovernanceModelMode) => void;
  externalApproved: boolean;
  setExternalApproved: (value: boolean) => void;
  disabled: boolean;
  submitting: boolean;
  onSubmit: () => void;
}

function IntakeForm(props: IntakeFormProps) {
  const canSubmit =
    !props.disabled &&
    props.requirementText.trim().length > 0 &&
    (props.modelMode !== "BAILIAN_LIVE" || props.externalApproved);
  return (
    <div className="governance-stage intake-stage">
      <div>
        <Typography.Title level={4}>描述需要治理的新增信息</Typography.Title>
        <Typography.Paragraph type="secondary">
          只需先写自然语言。拟挂载位置、类型和基数都是可选提示，不确定时保留“未知”。
        </Typography.Paragraph>
      </div>
      <label className="field-stack">
        <span>自然语言需求</span>
        <Input.TextArea
          rows={4}
          maxLength={8_000}
          showCount
          value={props.requirementText}
          onChange={(event) => props.setRequirementText(event.target.value)}
          placeholder="例如：为虚构藏品目录记录陈列高度。"
        />
      </label>
      <Checkbox
        checked={props.useSelectedParent}
        disabled={!props.selectedNode}
        onChange={(event) =>
          props.setUseSelectedParent(event.target.checked)
        }
      >
        将左侧当前节点“{props.selectedNode?.name ?? "尚未选择"}”作为拟挂载位置
      </Checkbox>
      <div className="hint-grid">
        <label className="field-stack">
          <span>节点类型提示</span>
          <Select
            value={props.nodeKind}
            onChange={props.setNodeKind}
            options={[
              { value: "UNKNOWN", label: "未知" },
              { value: "PROPERTY", label: "属性节点" },
              { value: "CONCEPT", label: "概念节点" },
            ]}
          />
        </label>
        <label className="field-stack">
          <span>值类型提示</span>
          <Select
            allowClear
            value={props.valueType}
            onChange={props.setValueType}
            placeholder="未知"
            options={[
              { value: "string", label: "文本 string" },
              { value: "float", label: "数值 float" },
              { value: "date", label: "日期 date" },
              { value: "class", label: "复合 class" },
            ]}
          />
        </label>
        <label className="field-stack">
          <span>基数提示</span>
          <Select
            value={props.cardinality}
            onChange={props.setCardinality}
            options={[
              { value: "UNKNOWN", label: "未知" },
              { value: "SINGLE", label: "单值" },
              { value: "MULTIPLE", label: "多值" },
            ]}
          />
        </label>
      </div>
      <Divider />
      <div className="model-row">
        <label className="field-stack">
          <span>模型模式</span>
          <Select
            value={props.modelMode}
            onChange={props.setModelMode}
            options={[
              {
                value: "SIMULATOR_LIVE",
                label: "本地 OpenAI 格式仿真",
              },
              {
                value: "BAILIAN_LIVE",
                label: "百炼真实模型",
              },
            ]}
          />
        </label>
        {props.modelMode === "BAILIAN_LIVE" && (
          <Checkbox
            checked={props.externalApproved}
            onChange={(event) =>
              props.setExternalApproved(event.target.checked)
            }
          >
            我确认本次内容完全虚构或已获准发送到百炼
          </Checkbox>
        )}
      </div>
      <Button
        type="primary"
        size="large"
        icon={<RobotOutlined />}
        disabled={!canSubmit}
        loading={props.submitting}
        onClick={props.onSubmit}
      >
        生成意图草稿
      </Button>
    </div>
  );
}

interface CaseBodyProps {
  value?: GovernanceCase;
  busy: boolean;
  operation?: GovernanceOperation;
  clarificationAnswer: string;
  setClarificationAnswer: (value: string) => void;
  reviewerReasoning: string;
  setReviewerReasoning: (value: string) => void;
  onClarify: () => void;
  onReviewIntent: (decision: "CONFIRM" | "REJECT") => void;
  onReviewRecommendation: (decision: "CONFIRM" | "REJECT") => void;
  onReset: () => void;
}

function CaseBody(props: CaseBodyProps) {
  if (!props.value || props.busy) {
    return (
      <div className="governance-loading">
        <Spin size="large" />
        <Typography.Text>
          {operationLabel(props.operation?.kind)}
        </Typography.Text>
        <Typography.Text type="secondary">
          页面轮询只读取同一个 operation，不会重复调用模型。
        </Typography.Text>
      </div>
    );
  }

  const value = props.value;
  if (value.status === "FAILED") {
    return (
      <Result
        status="error"
        title="本次治理运行已安全停止"
        subTitle="未生成 Gold、Patch 或生产写入。可检查固定错误码后重新发起。"
        extra={<Button onClick={props.onReset}>重新发起</Button>}
      />
    );
  }
  if (value.status === "INTENT_REJECTED") {
    return (
      <Result
        status="info"
        title="意图草稿已被人工拒绝"
        subTitle="该反馈仅保存在旁路工件中，没有进入候选召回。"
        extra={<Button onClick={props.onReset}>发起新需求</Button>}
      />
    );
  }
  if (value.status === "COMPLETED" && value.record) {
    return (
      <Result
        status="success"
        icon={<CheckCircleOutlined />}
        title="旁路治理记录已完成"
        subTitle={`人工结果：${value.record.status}。记录可回放，但不是 Gold，也不能发布 Patch。`}
        extra={<Button onClick={props.onReset}>发起新需求</Button>}
      >
        <Space wrap>
          <Tag color="green">可回放</Tag>
          <Tag>语义批准：否</Tag>
          <Tag>Gold：否</Tag>
          <Tag>Patch：否</Tag>
        </Space>
      </Result>
    );
  }
  if (value.status === "CLARIFICATION_LIMIT_REACHED") {
    return (
      <div className="governance-stage">
        <IntentCard value={value} />
        <Alert
          type="warning"
          showIcon
          title="一次澄清后仍无法形成可确认意图"
          description="系统已停止自动追问。请重新描述需求，或由专家在线下补充判断。"
        />
        <Button onClick={props.onReset}>重新发起</Button>
      </div>
    );
  }
  if (value.status === "NEEDS_CLARIFICATION") {
    return (
      <div className="governance-stage">
        <IntentCard value={value} />
        <Alert
          type="warning"
          showIcon
          title="AI 需要一次澄清"
          description={value.intent?.content.clarification_question}
        />
        <Input.TextArea
          rows={3}
          value={props.clarificationAnswer}
          onChange={(event) =>
            props.setClarificationAnswer(event.target.value)
          }
          placeholder="可以提交你的判断、思路或暂时无法确定的原因。"
        />
        <Button
          type="primary"
          disabled={!props.clarificationAnswer.trim()}
          onClick={props.onClarify}
        >
          提交本轮回答
        </Button>
      </div>
    );
  }
  if (value.status === "INTENT_REVIEW") {
    return (
      <div className="governance-stage">
        <IntentCard value={value} />
        <Alert
          type="info"
          showIcon
          title="这只是 AI 整理出的意图草稿"
          description="确认仅授权全树候选检索，不代表语义批准或允许新增节点。"
        />
        <Space>
          <Button
            type="primary"
            onClick={() => props.onReviewIntent("CONFIRM")}
          >
            确认并检索候选
          </Button>
          <Button danger onClick={() => props.onReviewIntent("REJECT")}>
            拒绝草稿
          </Button>
        </Space>
      </div>
    );
  }
  if (value.status === "RECOMMENDATION_REVIEW") {
    return (
      <div className="governance-stage">
        <RecommendationSection value={value} />
        <label className="field-stack">
          <span>专家思考与审查理由（可选，保存在私有旁路工件）</span>
          <Input.TextArea
            rows={3}
            maxLength={8_000}
            value={props.reviewerReasoning}
            onChange={(event) =>
              props.setReviewerReasoning(event.target.value)
            }
            placeholder="可以记录为什么接受或拒绝，而不必强行选择预设理由。"
          />
        </label>
        <Alert
          type="warning"
          showIcon
          title="AI 只给出初步建议"
          description="人工确认后仍固定为运营反馈，不会成为 Gold、语义审批或 Patch。"
        />
        <Space>
          <Button
            type="primary"
            onClick={() => props.onReviewRecommendation("CONFIRM")}
          >
            接受建议
          </Button>
          <Button
            danger
            onClick={() => props.onReviewRecommendation("REJECT")}
          >
            拒绝建议
          </Button>
        </Space>
      </div>
    );
  }
  return (
    <Empty description={`当前状态：${value.status}`} />
  );
}

function IntentCard({ value }: { value: GovernanceCase }) {
  const intent = value.intent?.content;
  if (!intent) {
    return <Empty description="尚未形成意图" />;
  }
  return (
    <Card size="small" className="intent-card" title="AI 意图草稿">
      <Descriptions column={2} size="small">
        <Descriptions.Item label="信息主体">
          {intent.subject ?? "未确定"}
        </Descriptions.Item>
        <Descriptions.Item label="节点类型">
          {intent.node_kind}
        </Descriptions.Item>
        <Descriptions.Item label="业务角色">
          {intent.role ?? "未确定"}
        </Descriptions.Item>
        <Descriptions.Item label="值类型">
          {intent.value_type ?? "未确定"}
        </Descriptions.Item>
        <Descriptions.Item label="场景">
          {intent.scenario ?? "未确定"}
        </Descriptions.Item>
        <Descriptions.Item label="基数">
          {intent.cardinality}
        </Descriptions.Item>
      </Descriptions>
      <FactList title="已确认事实" values={intent.confirmed_facts} />
      <FactList title="假设" values={intent.assumptions} />
      <FactList title="证据缺口" values={intent.evidence_gaps} />
    </Card>
  );
}

function RecommendationSection({ value }: { value: GovernanceCase }) {
  const assessmentByRef = useMemo(
    () =>
      new Map(
        (value.recommendation?.candidate_assessments ?? []).map(
          (item) => [item.candidate_ref, item],
        ),
      ),
    [value.recommendation],
  );
  return (
    <>
      <div>
        <Typography.Title level={4}>候选节点比较</Typography.Title>
        <Typography.Paragraph type="secondary">
          确定性全树召回 Top-20；模型只看到其中前 8 个临时候选。
        </Typography.Paragraph>
      </div>
      <div className="candidate-list">
        {(value.candidates?.items ?? []).map((candidate) => {
          const assessment = assessmentByRef.get(candidate.candidate_ref);
          const selected =
            candidate.candidate_ref ===
            value.recommendation?.selected_candidate_ref;
          return (
            <Card
              key={candidate.candidate_ref}
              size="small"
              className={selected ? "candidate selected-candidate" : "candidate"}
            >
              <div className="candidate-title">
                <Space>
                  <Tag>{candidate.candidate_ref}</Tag>
                  <Typography.Text strong>{candidate.name}</Typography.Text>
                </Space>
                {selected && <Tag color="green">AI 选中</Tag>}
              </div>
              <Typography.Text type="secondary">
                {(candidate.path_names?.length
                  ? candidate.path_names
                  : candidate.path_labels
                ).join(" / ")}
              </Typography.Text>
              <div className="candidate-tags">
                <Tag>{candidate.kind}</Tag>
                <Tag>{candidate.value_type ?? "无值类型"}</Tag>
                <Tag>{candidate.cardinality ?? "无基数"}</Tag>
                {assessment && <Tag color="blue">{assessment.relation}</Tag>}
              </div>
              {assessment && (
                <Typography.Paragraph className="candidate-reason">
                  {assessment.reason}
                </Typography.Paragraph>
              )}
            </Card>
          );
        })}
      </div>
      {value.recommendation && (
        <Card
          size="small"
          className="recommendation-card"
          title={
            <Space>
              <SafetyCertificateOutlined />
              <span>AI 初步建议</span>
            </Space>
          }
        >
          <Space wrap>
            <Tag color="gold">
              {value.recommendation.recommended_action}
            </Tag>
            {value.recommendation.selected_candidate_ref && (
              <Tag>{value.recommendation.selected_candidate_ref}</Tag>
            )}
          </Space>
          <Typography.Paragraph>
            {value.recommendation.rationale}
          </Typography.Paragraph>
          <FactList
            title="不确定性"
            values={value.recommendation.uncertainties}
          />
          <FactList
            title="证据缺口"
            values={value.recommendation.evidence_gaps}
          />
        </Card>
      )}
    </>
  );
}

function FactList({
  title,
  values,
}: {
  title: string;
  values: string[];
}) {
  if (!values.length) {
    return null;
  }
  return (
    <div className="fact-list">
      <Typography.Text type="secondary">{title}</Typography.Text>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function currentStep(value?: GovernanceCase): number {
  if (!value) {
    return 0;
  }
  if (
    value.status === "DRAFT_RUNNING" ||
    value.status === "NEEDS_CLARIFICATION" ||
    value.status === "CLARIFICATION_RUNNING" ||
    value.status === "CLARIFICATION_LIMIT_REACHED"
  ) {
    return 0;
  }
  if (
    value.status === "INTENT_REVIEW" ||
    value.status === "INTENT_REVIEW_RUNNING" ||
    value.status === "INTENT_REJECTED"
  ) {
    return 1;
  }
  if (value.status === "RECOMMENDATION_REVIEW") {
    return 2;
  }
  return 3;
}

function operationLabel(kind?: string): string {
  if (kind === "DRAFT_INTENT") {
    return "AI 正在整理需求意图…";
  }
  if (kind === "CLARIFY_INTENT") {
    return "AI 正在根据本轮回答重新整理意图…";
  }
  if (kind === "REVIEW_INTENT") {
    return "正在召回全树候选并生成受约束建议…";
  }
  if (kind === "REVIEW_RECOMMENDATION") {
    return "正在校验人工动作并生成可回放旁路记录…";
  }
  return "正在准备治理运行…";
}

function runtimeRefFromQuery(name: string): string | undefined {
  const value = new URL(window.location.href).searchParams.get(name);
  return value && RUNTIME_REF.test(value) ? value : undefined;
}

export default GovernancePanel;
