import { AimOutlined, SendOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Checkbox, Input, Select, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import {
  clarifyNavigationCopilotCase,
  completeNavigationCopilotCase,
  createNavigationCopilotCase,
  fetchNavigationCopilotCapability,
  fetchNavigationCopilotCase,
  fetchNavigationCopilotOperation,
  type GovernanceModelMode,
  type NavigationCopilotCandidate,
  type NavigationCopilotCase,
  type TreeViewNode,
  WorkbenchAPIError,
} from "./api";
import { canUseOutsideCandidate, copilotStatusMessage } from "./navigation-copilot";

interface Props {
  resourceId?: string;
  version?: string;
  selectedNode?: TreeViewNode;
  onNavigate: (nodeRef: string) => void;
}

function errorCode(error: unknown): string {
  return error instanceof WorkbenchAPIError
    ? error.code
    : "COPILOT_REQUEST_FAILED";
}

export default function NavigationCopilotPanel({
  resourceId,
  version,
  selectedNode,
  onNavigate,
}: Props) {
  const capability = useQuery({
    queryKey: ["navigation-copilot-capability"],
    queryFn: fetchNavigationCopilotCapability,
  });
  const [requirement, setRequirement] = useState("");
  const [answer, setAnswer] = useState("");
  const [modelMode, setModelMode] = useState<GovernanceModelMode>("SIMULATOR_LIVE");
  const [externalApproved, setExternalApproved] = useState(false);
  const [operationRef, setOperationRef] = useState<string>();
  const [caseRef, setCaseRef] = useState<string>();
  const [caseValue, setCaseValue] = useState<NavigationCopilotCase>();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();

  useEffect(() => {
    if (!operationRef) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const operation = await fetchNavigationCopilotOperation(operationRef);
        if (cancelled) return;
        if (operation.status === "FAILED") {
          setFailure(operation.error_code ?? "COPILOT_OPERATION_FAILED");
          setBusy(false);
          setOperationRef(undefined);
          return;
        }
        if (operation.status === "SUCCEEDED") {
          const value = await fetchNavigationCopilotCase(operation.case_ref);
          if (!cancelled) {
            setCaseRef(operation.case_ref);
            setCaseValue(value);
            setBusy(false);
            setOperationRef(undefined);
          }
          return;
        }
        window.setTimeout(poll, 500);
      } catch (error) {
        if (!cancelled) {
          setFailure(errorCode(error));
          setBusy(false);
          setOperationRef(undefined);
        }
      }
    };
    void poll();
    return () => { cancelled = true; };
  }, [operationRef]);

  useEffect(() => {
    setExternalApproved(false);
  }, [resourceId, version]);

  if (!capability.data?.enabled) return null;
  const selectedCandidate = caseValue?.candidates.find(
    (candidate) => candidate.node_ref === selectedNode?.ref,
  );

  const start = async () => {
    if (!resourceId || !version || !requirement.trim()) return;
    setBusy(true);
    setFailure(undefined);
    setCaseValue(undefined);
    try {
      const operation = await createNavigationCopilotCase({
        resource_id: resourceId,
        version,
        requirement_text: requirement.trim(),
        proposed_parent_ref: selectedNode?.ref ?? null,
        node_kind_hint: "UNKNOWN",
        value_type_hint: null,
        cardinality_hint: "UNKNOWN",
        model_mode: modelMode,
        external_data_approved: modelMode === "BAILIAN_LIVE" && externalApproved,
      });
      setCaseRef(operation.case_ref);
      setOperationRef(operation.operation_ref);
      setExternalApproved(false);
    } catch (error) {
      setFailure(errorCode(error));
      setBusy(false);
    }
  };

  const clarify = async () => {
    if (!caseRef || !answer.trim()) return;
    setBusy(true);
    setFailure(undefined);
    try {
      const operation = await clarifyNavigationCopilotCase(caseRef, answer.trim());
      setOperationRef(operation.operation_ref);
      setAnswer("");
    } catch (error) {
      setFailure(errorCode(error));
      setBusy(false);
    }
  };

  const choose = async (candidate: NavigationCopilotCandidate) => {
    if (!caseRef) return;
    setBusy(true);
    try {
      const value = await completeNavigationCopilotCase(caseRef, {
        action: "SELECT_CANDIDATE",
        selected_candidate_ref: candidate.candidate_ref,
        selected_node_ref: candidate.node_ref,
      });
      setCaseValue(value);
      onNavigate(candidate.node_ref);
    } catch (error) {
      setFailure(errorCode(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      className="panel-card copilot-card"
      title={<Space><AimOutlined /><span>信息树导航助手（影子验证）</span></Space>}
    >
      <Alert
        type="info"
        showIcon
        title="只帮助定位和高亮，不修改信息树"
      />
      <div className="copilot-compose">
        <Input.TextArea
          value={requirement}
          onChange={(event) => setRequirement(event.target.value)}
          placeholder="用一句话描述你想在树中找到什么"
          autoSize={{ minRows: 2, maxRows: 5 }}
          maxLength={8000}
          disabled={busy}
        />
        <Space wrap>
          <Select<GovernanceModelMode>
            value={modelMode}
            onChange={setModelMode}
            options={[
              { value: "SIMULATOR_LIVE", label: "本地模拟" },
              { value: "QWEN_LIVE", label: "内网 Qwen" },
              { value: "BAILIAN_LIVE", label: "百炼" },
            ]}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={busy}
            disabled={
              !resourceId ||
              !version ||
              !requirement.trim() ||
              (modelMode === "BAILIAN_LIVE" && !externalApproved)
            }
            onClick={() => void start()}
          >
            帮我定位
          </Button>
          {selectedNode ? <Tag>当前节点仅作软参考：{selectedNode.name}</Tag> : null}
        </Space>
        {modelMode === "BAILIAN_LIVE" ? (
          <Checkbox
            checked={externalApproved}
            onChange={(event) => setExternalApproved(event.target.checked)}
          >
            确认本次需求及候选语义允许发送至百炼（仅绑定当前新 case）
          </Checkbox>
        ) : null}
      </div>

      {failure ? <Alert type="warning" showIcon title={`本次未完成：${failure}`} /> : null}
      {caseValue?.degradation_codes.length ? (
        <Alert
          type="warning"
          showIcon
          title="模型能力已降级，候选仍由原始需求保底召回"
          description={caseValue.degradation_codes.join("、")}
        />
      ) : null}

      {caseValue?.status === "CLARIFICATION_LIMIT_REACHED" ? (
        <Alert
          type="warning"
          showIcon
          title="一次澄清后仍不明确，本次已安全停止"
        />
      ) : null}

      {caseValue?.outcome ? (
        <Alert
          type="success"
          showIcon
          title={
            caseValue.outcome.candidate_miss
              ? "已按你的纠正定位，并记录为候选未命中"
              : "本次导航反馈已记录"
          }
        />
      ) : null}

      {caseValue?.status === "NEEDS_CLARIFICATION" ? (
        <div className="copilot-clarification">
          <Typography.Text strong>
            {caseValue.interpretation?.clarification_question}
          </Typography.Text>
          <Space.Compact block>
            <Input value={answer} onChange={(event) => setAnswer(event.target.value)} />
            <Button loading={busy} disabled={!answer.trim()} onClick={() => void clarify()}>
              回答
            </Button>
          </Space.Compact>
        </div>
      ) : null}

      {caseValue?.candidate_status ? (
        <Typography.Paragraph type="secondary">
          状态：{caseValue.candidate_status}；模型调用 {caseValue.model_call_count}/2。
          {` ${copilotStatusMessage(caseValue)}`}
        </Typography.Paragraph>
      ) : null}

      {caseValue?.candidates.length ? (
        <div className="copilot-candidates">
          {caseValue.candidates.map((item) => (
            <div className="copilot-candidate" key={item.candidate_ref}>
              <div>
                <Space>
                  <Typography.Text strong>{item.rank}. {item.name}</Typography.Text>
                  {item.candidate_ref === caseValue.highlighted_candidate_ref ? <Tag color="green">AI 高亮</Tag> : null}
                </Space>
                <Typography.Paragraph type="secondary">
                  {item.path_names.join(" / ")}{item.reason ? ` · ${item.reason}` : ""}
                </Typography.Paragraph>
              </div>
              <Button type="link" onClick={() => onNavigate(item.node_ref)}>
                在树中查看
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {caseValue?.status === "AWAITING_OUTCOME" && !caseValue.outcome ? (
        <Space wrap>
          <Button
            type="primary"
            disabled={busy || !selectedCandidate}
            onClick={() => selectedCandidate && void choose(selectedCandidate)}
          >
            确认左侧当前候选
          </Button>
          <Button
            disabled={busy || !canUseOutsideCandidate(selectedNode?.ref, caseValue.candidates)}
            onClick={async () => {
              if (!caseRef || !selectedNode) return;
              setBusy(true);
              try {
                const value = await completeNavigationCopilotCase(caseRef, {
                  action: "SELECT_OUTSIDE_CANDIDATE",
                  selected_candidate_ref: null,
                  selected_node_ref: selectedNode.ref,
                });
                setCaseValue(value);
                onNavigate(selectedNode.ref);
              } catch (error) {
                setFailure(errorCode(error));
              } finally {
                setBusy(false);
              }
            }}
          >
            候选都不对，采用左侧当前节点
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              if (!caseRef) return;
              setBusy(true);
              try {
                setCaseValue(await completeNavigationCopilotCase(caseRef, {
                  action: "REJECT_ALL",
                  selected_candidate_ref: null,
                  selected_node_ref: null,
                }));
              } catch (error) {
                setFailure(errorCode(error));
              } finally {
                setBusy(false);
              }
            }}
          >
            暂无合适节点
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              if (!caseRef) return;
              setBusy(true);
              try {
                setCaseValue(await completeNavigationCopilotCase(caseRef, {
                  action: "EXIT",
                  selected_candidate_ref: null,
                  selected_node_ref: null,
                }));
              } catch (error) {
                setFailure(errorCode(error));
              } finally {
                setBusy(false);
              }
            }}
          >
            退出本次
          </Button>
        </Space>
      ) : null}
    </Card>
  );
}
