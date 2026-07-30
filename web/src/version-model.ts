import type { VersionItem } from "./api";

export function findCurrentVersion(
  items: VersionItem[],
): VersionItem | undefined {
  return items.find((item) => item.is_head);
}

export function buildVersionOptions(items: VersionItem[]) {
  const latestPosition =
    items.length > 0
      ? Math.max(...items.map((item) => item.position))
      : null;

  return items.map((item) => {
    const markers: string[] = [];
    if (item.is_head) {
      markers.push("默认");
    }
    if (item.position === latestPosition) {
      markers.push("最新");
    }
    return {
      value: item.version,
      label:
        markers.length > 0
          ? `${item.version} · ${markers.join(" · ")}`
          : item.version,
    };
  });
}
