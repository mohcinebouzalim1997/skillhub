from __future__ import annotations
import argparse, json
from pathlib import Path

def fmt(v):
    if v is None: return '—'
    if isinstance(v,float): return f'{v:.8g}'
    return str(v)

def build(comp:dict,cands:dict,metric:str)->str:
    rows=[m for m in comp.get('metrics',[]) if m.get('metric','').lower()==metric.lower()]
    target=rows[0] if rows else (comp.get('metrics') or [{}])[0]
    lines=['# Metric jump investigation brief','',f"Target metric: **{metric}**",'', '## Observed signature','']
    if target:
        lines += [f"- Before aggregate: **{fmt(target.get('before_sum'))}**",f"- After aggregate: **{fmt(target.get('after_sum'))}**",f"- Absolute delta: **{fmt(target.get('absolute_delta'))}**",f"- Relative delta: **{'—' if target.get('relative_delta_pct') is None else fmt(target.get('relative_delta_pct')) + '%'}**"]
    ra=comp.get('row_analysis') or {}; movers=[m for m in ra.get('top_movers',[]) if m.get('metric','').lower()==metric.lower()][:8]
    if movers:
        lines += ['', 'Largest affected keys:']
        for m in movers: lines.append(f"- `{m.get('key')}`: {fmt(m.get('before'))} → {fmt(m.get('after'))} (Δ {fmt(m.get('absolute_delta'))})")
    lines += ['', '## Release candidates', '']
    for c in (cands.get('candidates') or [])[:8]:
        lines.append(f"### PR #{c.get('pr')} — {c.get('title')}")
        lines.append(f"Retrieval relevance score: `{c.get('relevance_score')}` — **not a causal probability**.")
        for s in c.get('signals') or []: lines.append(f"- {s}")
        lines.append('')
    lines += ['## Next reasoning step','', 'For each candidate, state a mechanism that could produce the observed signature, list contradicting facts, then design the smallest discriminating experiment. Do not name a culprit from retrieval ranking alone.','']
    return '\n'.join(lines)

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--comparison',type=Path,required=True); p.add_argument('--candidates',type=Path,required=True); p.add_argument('--metric',required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); comp=json.loads(a.comparison.read_text(encoding='utf-8')); cands=json.loads(a.candidates.read_text(encoding='utf-8')); text=build(comp,cands,a.metric); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(text,encoding='utf-8'); print(json.dumps({'success':True,'output':str(a.output)},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
