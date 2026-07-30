import { describe, expect, it } from "vitest";

import type { VersionItem } from "./api";
import {
  buildVersionOptions,
  findCurrentVersion,
} from "./version-model";

function version(
  position: number,
  value: string,
  isHead: boolean,
): VersionItem {
  return {
    position,
    version: value,
    description: null,
    is_head: isHead,
  };
}

describe("version model", () => {
  it("marks current/default independently from the latest version", () => {
    expect(
      buildVersionOptions([
        version(0, "V0.0.0.0J0.1.0", true),
        version(1, "V0.0.0.0J0.2.0", false),
      ]),
    ).toEqual([
      {
        value: "V0.0.0.0J0.1.0",
        label: "V0.0.0.0J0.1.0 · 默认",
      },
      {
        value: "V0.0.0.0J0.2.0",
        label: "V0.0.0.0J0.2.0 · 最新",
      },
    ]);
  });

  it("shows both markers when current/default is also latest", () => {
    expect(
      buildVersionOptions([
        version(0, "V0.0.0.0J0.1.0", false),
        version(1, "V0.0.0.0J0.2.0", true),
      ])[1].label,
    ).toBe("V0.0.0.0J0.2.0 · 默认 · 最新");
  });

  it("returns no options for an empty version list", () => {
    expect(buildVersionOptions([])).toEqual([]);
  });

  it("does not substitute latest when current/default is absent", () => {
    const items = [
      version(0, "V0.0.0.0J0.1.0", false),
      version(1, "V0.0.0.0J0.2.0", false),
    ];

    expect(findCurrentVersion(items)).toBeUndefined();
  });
});
