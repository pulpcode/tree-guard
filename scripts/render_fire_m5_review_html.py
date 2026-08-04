#!/usr/bin/env python3
"""Render a dependency-free private HTML review interface for M5 candidates."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

from fire_m5_data_common import M5DataError, build_review_rows


def _render(dataset_dir: Path) -> str:
    preflight, rows = build_review_rows(dataset_dir)
    cards: list[str] = []
    for row in rows:
        request = row["request"]
        targets = "、".join(row["target_names"]) or "（无目标）"
        safe_actions = "、".join(row["safe_alternative"]["allowed_actions"])
        tags = "、".join(row["analysis_tags"])
        cards.append(
            f"""
            <article class="card" data-selection="{html.escape(row['selection_status'])}"
                     data-route="{html.escape(row['expected_route'])}">
              <header><h2>{html.escape(row['scenario_ref'])}</h2>
                <span>{html.escape(row['selection_status'])}</span>
                <span>{html.escape(row['coverage_cell'])}</span>
                <span>{html.escape(row['expected_route'])}</span></header>
              <dl>
                <dt>一级分支</dt><dd>{html.escape(row['primary_branch_name'])}</dd>
                <dt>主风险</dt><dd>{html.escape(row['primary_risk'])}</dd>
                <dt>分析标签</dt><dd>{html.escape(tags)}</dd>
                <dt>自然语言需求</dt><dd>{html.escape(request['requirement_text'])}</dd>
                <dt>结构提示</dt><dd>{html.escape(json.dumps({k: request[k] for k in ('node_kind_hint', 'value_type_hint', 'cardinality_hint')}, ensure_ascii=False))}</dd>
                <dt>候选父级</dt><dd>{'已提供' if request['proposed_parent_node_id'] else '未提供'}</dd>
                <dt>期望目标</dt><dd>{html.escape(targets)}</dd>
                <dt>安全退让</dt><dd>{html.escape(safe_actions)} / {html.escape(row['safe_alternative']['rationale_code'])}</dd>
              </dl>
              <fieldset data-ref="{html.escape(row['scenario_ref'])}">
                <legend>人工结论</legend>
                <label><input type="radio" name="{html.escape(row['scenario_ref'])}" value="ACCEPT">接受</label>
                <label><input type="radio" name="{html.escape(row['scenario_ref'])}" value="REVISE">需修订</label>
                <label><input type="radio" name="{html.escape(row['scenario_ref'])}" value="REJECT">拒绝</label>
                <textarea placeholder="可选审核说明"></textarea>
              </fieldset>
            </article>
            """
        )
    rows_json = json.dumps(
        [row["scenario_ref"] for row in rows], ensure_ascii=False
    ).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>M5 人工审核</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f5f7fa;color:#172033}}
main{{max-width:1120px;margin:auto;padding:24px}} .toolbar{{position:sticky;top:0;background:#fff;padding:16px;border-radius:12px;box-shadow:0 2px 12px #0001;z-index:2}}
.summary{{display:flex;gap:16px;flex-wrap:wrap}} .card{{background:#fff;margin:18px 0;padding:20px;border-radius:12px;border:1px solid #dce3ec}}
header{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}} header h2{{margin-right:auto}} header span{{background:#eaf1ff;padding:4px 8px;border-radius:999px;font-size:12px}}
dl{{display:grid;grid-template-columns:120px 1fr;gap:8px 16px}} dt{{font-weight:700}} dd{{margin:0;white-space:pre-wrap}} fieldset{{margin-top:16px;border:1px solid #ccd6e3;border-radius:8px}}
label{{margin-right:18px}} textarea{{display:block;width:100%;box-sizing:border-box;margin-top:12px;min-height:64px}} button,select{{padding:8px 12px;margin-right:8px}}
</style></head><body><main>
<section class="toolbar"><h1>M5 未见资格候选人工审核</h1>
<p>确定性 preflight：{html.escape(preflight['status'])}；节点 {preflight['node_count']}；正式 24（18 PROCEED + 6 CLARIFY）；余量 6。Codex 预检不是人工批准。</p>
<div class="summary"><span id="progress">已审核 0 / {len(rows)}</span>
<select id="filter"><option value="ALL">全部</option><option value="EXECUTION">正式</option><option value="RESERVE">余量</option><option value="PROCEED">PROCEED</option><option value="CLARIFY">CLARIFY</option></select>
<button id="export">导出审核 JSON</button></div></section>
{''.join(cards)}
</main><script>
const refs={rows_json}; const filter=document.getElementById('filter');
function update(){{const reviewed=refs.filter(r=>document.querySelector(`input[name="${{r}}"]:checked`)).length;document.getElementById('progress').textContent=`已审核 ${{reviewed}} / ${{refs.length}}`;}}
document.addEventListener('change',e=>{{if(e.target.matches('input[type=radio]'))update();}});
filter.addEventListener('change',()=>{{document.querySelectorAll('.card').forEach(card=>{{const v=filter.value;card.hidden=!(v==='ALL'||card.dataset.selection===v||card.dataset.route===v);}});}});
document.getElementById('export').addEventListener('click',()=>{{const items=refs.map(ref=>{{const field=document.querySelector(`fieldset[data-ref="${{ref}}"]`);const chosen=field.querySelector('input:checked');return {{scenario_ref:ref,decision:chosen?chosen.value:'NOT_REVIEWED',note:field.querySelector('textarea').value}};}});const payload={{schema_version:'m5-assisted-shadow-human-review-input.v1',review_authority:'HUMAN_AUTHORIZED',items}};const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='m5-human-review.json';a.click();URL.revokeObjectURL(a.href);}});
</script></body></html>"""


def _write_private_html(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        data = content.encode("utf-8")
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError("private HTML write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        _write_private_html(args.output, _render(args.dataset_dir))
    except (M5DataError, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, M5DataError) else "M5_REVIEW_HTML_WRITE_FAILED"
        print(json.dumps({"status": "FAIL", "error_code": code}, sort_keys=True))
        return 2
    print(json.dumps({"status": "PASS", "private_html": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
