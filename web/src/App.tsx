import {
  ApartmentOutlined,
  FileSearchOutlined,
  LockOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import type { ElementRef, Key } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Layout,
  Select,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Tree,
  Typography,
} from "antd";

import GovernancePanel from "./GovernancePanel";
import {
  fetchCategories,
  fetchResources,
  fetchTree,
  fetchVersions,
  type TreeViewNode,
  WorkbenchAPIError,
} from "./api";
import {
  buildTreeData,
  filterTreeData,
  searchTree,
  type WorkbenchTreeNode,
} from "./tree-model";

const { Header, Content } = Layout;

function apiErrorCode(error: unknown): string {
  return error instanceof WorkbenchAPIError
    ? error.code
    : "WORKBENCH_REQUEST_FAILED";
}

function App() {
  const treeRef = useRef<ElementRef<typeof Tree>>(null);
  const [categoryId, setCategoryId] = useState<string>();
  const [resourceId, setResourceId] = useState<string>();
  const [version, setVersion] = useState<string>();
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedKeys, setExpandedKeys] = useState<Key[]>([]);
  const [selectedRef, setSelectedRef] = useState<string>();

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: fetchCategories,
  });
  const resources = useQuery({
    queryKey: ["resources", categoryId],
    queryFn: () => fetchResources(categoryId!),
    enabled: Boolean(categoryId),
  });
  const versions = useQuery({
    queryKey: ["versions", resourceId],
    queryFn: () => fetchVersions(resourceId!),
    enabled: Boolean(resourceId),
  });
  const tree = useQuery({
    queryKey: ["tree", resourceId, version],
    queryFn: () => fetchTree(resourceId!, version!),
    enabled: Boolean(resourceId && version),
  });

  useEffect(() => {
    if (categoryId || !categories.data?.length) {
      return;
    }
    const parentIds = new Set(
      categories.data
        .map((item) => item.parent_id)
        .filter((item): item is string => item !== null),
    );
    const firstLeaf =
      categories.data.find((item) => !parentIds.has(item.category_id)) ??
      categories.data[0];
    setCategoryId(firstLeaf.category_id);
  }, [categories.data, categoryId]);

  useEffect(() => {
    if (!resourceId && resources.data?.length) {
      setResourceId(resources.data[0].resource_id);
    }
  }, [resourceId, resources.data]);

  useEffect(() => {
    if (!version && versions.data?.length) {
      const head =
        versions.data.find((item) => item.is_head) ??
        versions.data[versions.data.length - 1];
      setVersion(head.version);
    }
  }, [version, versions.data]);

  const treeData = useMemo(
    () =>
      tree.data
        ? buildTreeData(tree.data.nodes, tree.data.root_refs)
        : [],
    [tree.data],
  );
  const nodeByRef = useMemo(
    () =>
      new Map(
        (tree.data?.nodes ?? []).map((node) => [node.ref, node]),
      ),
    [tree.data],
  );
  const searchResult = useMemo(
    () => searchTree(tree.data?.nodes ?? [], searchTerm),
    [searchTerm, tree.data],
  );
  const matchedRefs = useMemo(
    () => new Set(searchResult.matchedRefs),
    [searchResult.matchedRefs],
  );
  const visibleTreeData = useMemo(
    () =>
      searchTerm.trim()
        ? filterTreeData(treeData, matchedRefs)
        : treeData,
    [matchedRefs, searchTerm, treeData],
  );
  const selectedNode = selectedRef
    ? nodeByRef.get(selectedRef)
    : undefined;

  useEffect(() => {
    if (!tree.data) {
      return;
    }
    setExpandedKeys(tree.data.root_refs);
    setSelectedRef(tree.data.root_refs[0]);
  }, [tree.data]);

  useEffect(() => {
    if (!searchTerm.trim()) {
      return;
    }
    setExpandedKeys(searchResult.expandedRefs);
    if (searchResult.matchedRefs[0]) {
      setSelectedRef(searchResult.matchedRefs[0]);
    }
  }, [searchResult, searchTerm]);

  useEffect(() => {
    if (!selectedRef) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      treeRef.current?.scrollTo({ key: selectedRef, align: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [expandedKeys, selectedRef]);

  const resetResource = (nextCategory: string) => {
    setCategoryId(nextCategory);
    setResourceId(undefined);
    setVersion(undefined);
    setSearchTerm("");
    setSelectedRef(undefined);
  };

  const resetVersion = (nextResource: string) => {
    setResourceId(nextResource);
    setVersion(undefined);
    setSearchTerm("");
    setSelectedRef(undefined);
  };

  const firstError =
    categories.error ?? resources.error ?? versions.error ?? tree.error;

  return (
    <Layout className="app-shell">
      <Header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <SafetyCertificateOutlined />
          </div>
          <div>
            <Typography.Title level={4}>TreeGuard</Typography.Title>
            <Typography.Text>信息树语义治理工作台</Typography.Text>
          </div>
        </div>
        <Space>
          <Tag className="shadow-tag" icon={<LockOutlined />}>
            SHADOW · 旁路
          </Tag>
          <Tag color="green">Clean-room Simulator</Tag>
        </Space>
      </Header>

      <Content className="content">
        <Card className="selector-card" variant="borderless">
          <div className="selector-grid">
            <label>
              <span>分类</span>
              <Select
                value={categoryId}
                loading={categories.isLoading}
                options={(categories.data ?? []).map((item) => ({
                  value: item.category_id,
                  label: item.parent_id ? `　${item.name}` : item.name,
                }))}
                onChange={resetResource}
                placeholder="选择分类"
              />
            </label>
            <label>
              <span>信息树</span>
              <Select
                value={resourceId}
                loading={resources.isLoading}
                options={(resources.data ?? []).map((item) => ({
                  value: item.resource_id,
                  label: item.name,
                }))}
                onChange={resetVersion}
                placeholder="选择信息树"
                disabled={!categoryId}
              />
            </label>
            <label>
              <span>业务版本</span>
              <Select
                value={version}
                loading={versions.isLoading}
                options={(versions.data ?? []).map((item) => ({
                  value: item.version,
                  label: `${item.version}${item.is_head ? " · HEAD" : ""}`,
                }))}
                onChange={(nextVersion) => {
                  setVersion(nextVersion);
                  setSearchTerm("");
                  setSelectedRef(undefined);
                }}
                placeholder="选择版本"
                disabled={!resourceId}
              />
            </label>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => void tree.refetch()}
              disabled={!resourceId || !version}
            >
              重新载入
            </Button>
          </div>
        </Card>

        {firstError && (
          <Alert
            className="error-alert"
            type="error"
            showIcon
            title="只读数据载入失败"
            description={`错误码：${apiErrorCode(firstError)}`}
          />
        )}

        <div className="workspace-grid">
          <Card
            className="tree-panel panel-card"
            title={
              <Space>
                <ApartmentOutlined />
                <span>信息树导航</span>
                {tree.data && <Tag>{tree.data.node_count} 节点</Tag>}
              </Space>
            }
            extra={
              searchTerm.trim() && (
                <Typography.Text type="secondary">
                  {searchResult.matchedRefs.length} 个命中
                </Typography.Text>
              )
            }
          >
            <Input.Search
              allowClear
              value={searchTerm}
              placeholder="按节点名称或 label 搜索"
              onChange={(event) => setSearchTerm(event.target.value)}
            />
            <div className="tree-scroll">
              {tree.isLoading ? (
                <Skeleton active paragraph={{ rows: 12 }} />
              ) : visibleTreeData.length > 0 ? (
                <Tree<WorkbenchTreeNode>
                  ref={treeRef}
                  blockNode
                  height={590}
                  treeData={visibleTreeData}
                  expandedKeys={expandedKeys}
                  selectedKeys={selectedRef ? [selectedRef] : []}
                  onExpand={(keys) => setExpandedKeys(keys)}
                  onSelect={(keys) =>
                    setSelectedRef(keys[0]?.toString())
                  }
                  titleRender={(node) => (
                    <NodeTitle
                      node={node.source}
                      searchTerm={searchTerm}
                      matched={matchedRefs.has(node.source.ref)}
                    />
                  )}
                />
              ) : (
                <Empty
                  description={
                    searchTerm.trim()
                      ? "没有匹配的节点"
                      : "选择一个版本以载入信息树"
                  }
                />
              )}
            </div>
          </Card>

          <main className="review-column">
            <Card className="hero-card panel-card" variant="borderless">
              <Typography.Text className="eyebrow">
                GOVERNANCE INTAKE
              </Typography.Text>
              <Typography.Title level={2}>
                从树中定位证据，再进入语义治理
              </Typography.Title>
              <Typography.Paragraph>
                浏览大型信息树、描述治理需求、比较全树候选，并把 AI 建议交给专家
                复核。所有结果只进入可回放旁路，不修改源信息树。
              </Typography.Paragraph>
              <div className="metric-row">
                <Statistic
                  title="当前版本"
                  value={tree.data?.tree_version ?? "—"}
                />
                <Statistic
                  title="规范节点"
                  value={tree.data?.node_count ?? 0}
                />
                <Statistic title="生产写权限" value="0" />
              </div>
            </Card>

            <GovernancePanel
              resourceId={resourceId}
              version={version}
              selectedNode={selectedNode}
            />
          </main>

          <Card
            className="detail-panel panel-card"
            title={
              <Space>
                <FileSearchOutlined />
                <span>节点合同</span>
              </Space>
            }
          >
            {selectedNode ? (
              <NodeDetail node={selectedNode} />
            ) : (
              <Empty description="从左侧选择节点" />
            )}
          </Card>
        </div>
      </Content>
    </Layout>
  );
}

function NodeTitle({
  node,
  searchTerm,
  matched,
}: {
  node: TreeViewNode;
  searchTerm: string;
  matched: boolean;
}) {
  const name = node.name;
  const normalizedTerm = searchTerm.trim().toLocaleLowerCase();
  const start = normalizedTerm
    ? name.toLocaleLowerCase().indexOf(normalizedTerm)
    : -1;
  return (
    <span className="tree-node-title">
      <span>
        {start >= 0 ? (
          <>
            {name.slice(0, start)}
            <mark>{name.slice(start, start + normalizedTerm.length)}</mark>
            {name.slice(start + normalizedTerm.length)}
          </>
        ) : (
          name
        )}
      </span>
      {matched && <span className="match-dot" aria-label="搜索命中" />}
      <Tag variant="filled">{node.kind}</Tag>
    </span>
  );
}

function NodeDetail({ node }: { node: TreeViewNode }) {
  return (
    <div className="node-detail">
      <div className="node-icon">
        <ApartmentOutlined />
      </div>
      <Typography.Title level={3}>{node.name}</Typography.Title>
      <Typography.Text className="node-label">
        {node.label}
      </Typography.Text>
      <Breadcrumb
        className="node-breadcrumb"
        items={node.breadcrumb.map((title) => ({ title }))}
      />
      <Descriptions
        column={1}
        size="small"
        items={[
          { key: "kind", label: "节点类型", children: node.kind },
          {
            key: "value_type",
            label: "值类型",
            children: node.value_type ?? "—",
          },
          {
            key: "cardinality",
            label: "基数",
            children: node.cardinality ?? "—",
          },
          {
            key: "order",
            label: "同级顺序",
            children: node.order ?? "—",
          },
          {
            key: "children",
            label: "直接子节点",
            children: node.child_refs.length,
          },
        ]}
      />
      <Alert
        type="info"
        showIcon
        title="会话级节点引用"
        description={`页面引用 ${node.ref} 只用于本次树视图联动，不是生产 node_id。`}
      />
    </div>
  );
}

export default App;
