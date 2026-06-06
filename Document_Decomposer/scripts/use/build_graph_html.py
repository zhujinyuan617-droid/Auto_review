"""Render the candidate/relation network as a single self-contained HTML file.

Reads reports/connection/candidate_edges.json (and edges.json if present, for
relation types) plus the literature cards, and writes an interactive force graph
to reports/connection/graph.html. Double-click to open -- no server needed.
vis-network is loaded from a CDN, so an internet connection is needed the first
time the page is opened.

Nodes  = papers (size by degree, colour by a lightweight community label).
Edges  = candidate links (width by IDF score). If edges.json exists, edges are
         coloured by relation type (supports/contradicts/complements).
Click a node -> side panel with its card summary and typed neighbour list.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONN = ROOT / "reports" / "connection"

REL_COLORS = {
    "supports": "#2e7d32",
    "contradicts": "#d32f2f",
    "complements": "#1565c0",
    "candidate": "#b0bec5",
}


def load_cards():
    cards = {}
    for path in (ROOT / "library").glob("S*/literature_card.json"):
        c = json.loads(path.read_text(encoding="utf-8"))
        paper = c.get("paper", {}) or {}
        cl = c.get("classification", {}) or {}
        summary = c.get("summary") if isinstance(c.get("summary"), dict) else {}

        objective = str(summary.get("objective") or "").strip()
        main_findings = [str(x).strip() for x in (summary.get("main_findings") or []) if str(x).strip()]
        methods_systems = str(summary.get("methods_systems") or "").strip()

        # Compatibility for old thick cards that have not been rebuilt to slim schema 0.2.0.
        if not objective:
            objective = (c.get("core_question") or {}).get("claim", "")
        if not main_findings:
            for kf in (c.get("key_findings") or [])[:4]:
                t = kf.get("claim") or kf.get("finding") or kf.get("detail") or ""
                if t:
                    main_findings.append(t)
        cards[path.parent.name] = {
            "title": paper.get("title", "") or path.parent.name,
            "year": paper.get("year", ""),
            "schema_version": c.get("schema_version", ""),
            "objective": objective,
            "main_findings": main_findings,
            "methods_systems": methods_systems,
            "topics": cl.get("domain_tags", []) or [],
            "methods": cl.get("methods", []) or [],
            "objects": cl.get("research_objects", []) or [],
        }
    return cards


def communities(nodes, edges):
    """Deterministic weighted label propagation -> {node: community_id}."""
    adj = defaultdict(list)
    for e in edges:
        adj[e["a"]].append((e["b"], e["candidate_score"]))
        adj[e["b"]].append((e["a"], e["candidate_score"]))
    label = {n: n for n in nodes}
    order = sorted(nodes)
    for _ in range(10):
        changed = False
        for n in order:
            if not adj[n]:
                continue
            weight = defaultdict(float)
            for m, w in adj[n]:
                weight[label[m]] += w
            best = max(sorted(weight), key=lambda k: weight[k])  # tie -> smallest label
            if best != label[n]:
                label[n] = best
                changed = True
        if not changed:
            break
    # renumber to small ints by community size
    sizes = Counter(label.values())
    ranked = [lab for lab, _ in sizes.most_common()]
    remap = {lab: i for i, lab in enumerate(ranked)}
    return {n: remap[label[n]] for n in nodes}


def main() -> int:
    cand = json.loads((CONN / "candidate_edges.json").read_text(encoding="utf-8"))
    edges_raw = cand["edges"]
    edges_path = CONN / "edges.json"
    has_relations = edges_path.exists()
    rel_lookup = {}
    if has_relations:
        ej = json.loads(edges_path.read_text(encoding="utf-8"))
        for e in ej.get("edges", []):
            key = tuple(sorted((e["a"], e["b"])))
            rel_lookup[key] = e
        # only draw typed edges; dropped shared_context edges are noise in the view
        edges_raw = ej.get("edges", [])

    cards = load_cards()
    nodes = sorted({e["a"] for e in edges_raw} | {e["b"] for e in edges_raw})
    deg = Counter()
    for e in edges_raw:
        deg[e["a"]] += 1
        deg[e["b"]] += 1
    comm = communities(nodes, edges_raw)

    palette = ["#5b8ff9", "#61ddaa", "#f6bd16", "#7262fd", "#78d3f8", "#9661bc",
               "#f6903d", "#008685", "#f08bb4", "#6dc8ec", "#d48265", "#91c7ae"]

    vis_nodes = []
    for n in nodes:
        c = cards.get(n, {})
        d = deg[n]
        vis_nodes.append({
            "id": n,
            "label": n,
            "value": d,
            "group": comm[n],
            "color": palette[comm[n] % len(palette)],
            "title": f"{n}: {c.get('title','')[:80]} (deg {d})",
            "card": {
                "title": c.get("title", ""), "year": c.get("year", ""),
                "schema_version": c.get("schema_version", ""),
                "objective": c.get("objective", ""),
                "main_findings": c.get("main_findings", []),
                "methods_systems": c.get("methods_systems", ""),
                "topics": c.get("topics", []), "methods": c.get("methods", []),
                "objects": c.get("objects", []),
            },
        })

    vis_edges = []
    for e in edges_raw:
        key = tuple(sorted((e["a"], e["b"])))
        rel = rel_lookup.get(key, {})
        rtype = rel.get("relation", "candidate")
        shared = "; ".join(f"{f}:{'/'.join(v)}" for f, v in e["shared"].items())
        vis_edges.append({
            "from": e["a"], "to": e["b"],
            "value": e["candidate_score"],
            "color": {"color": REL_COLORS.get(rtype, REL_COLORS["candidate"]), "opacity": 0.5},
            "relation": rtype,
            "rationale": rel.get("rationale", ""),
            "shared": shared,
            "score": e["candidate_score"],
        })

    data = {"nodes": vis_nodes, "edges": vis_edges,
            "has_relations": has_relations, "n_papers": len(nodes), "n_edges": len(vis_edges)}

    html = HTML_TEMPLATE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False))
    out = CONN / "graph.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({len(nodes)} nodes, {len(vis_edges)} edges, "
          f"{'relation-coloured' if has_relations else 'candidate edges only'})")
    print(f"Open it by double-clicking, or: start {out}")
    return 0


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>文献关联网</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,"Segoe UI",sans-serif}
  #app{display:flex;height:100%}
  #net{flex:1;background:#fafafa}
  #side{width:360px;border-left:1px solid #ddd;padding:14px;overflow:auto;box-sizing:border-box;font-size:13px}
  #side h2{font-size:15px;margin:.2em 0}
  #bar{position:absolute;top:8px;left:12px;background:#fff;border:1px solid #ddd;border-radius:6px;padding:6px 10px;font-size:12px;z-index:5}
  .tag{display:inline-block;background:#eef;border-radius:4px;padding:1px 6px;margin:2px;font-size:11px}
  .nbr{border-top:1px solid #eee;padding:6px 0}
  .rel{font-weight:600;text-transform:uppercase;font-size:10px;padding:1px 5px;border-radius:3px;color:#fff}
  .muted{color:#888}
  .legend span{margin-right:10px}
</style>
</head>
<body>
<div id="bar"></div>
<div id="app">
  <div id="net"></div>
  <div id="side"><p class="muted">点击一个节点查看它的卡片摘要和邻居。</p></div>
</div>
<script>
const DATA = /*DATA*/;
const REL_COLORS = {supports:"#2e7d32",contradicts:"#d32f2f",complements:"#1565c0",candidate:"#b0bec5"};
const nodes = new vis.DataSet(DATA.nodes);
const edges = new vis.DataSet(DATA.edges);
const container = document.getElementById('net');
const network = new vis.Network(container, {nodes, edges}, {
  nodes:{shape:'dot', scaling:{min:6,max:40}, font:{size:11}},
  edges:{scaling:{min:0.5,max:6}, smooth:false},
  physics:{barnesHut:{gravitationalConstant:-3000, springLength:120, springConstant:0.02}, stabilization:{iterations:200}},
  interaction:{hover:true, tooltipDelay:120}
});

const bar = document.getElementById('bar');
const legend = DATA.has_relations
  ? '<span class="legend">边颜色: '+Object.entries(REL_COLORS).filter(([k])=>k!=='candidate').map(([k,v])=>`<span style="color:${v}">■ ${k}</span>`).join(' ')+'</span>'
  : '<span class="muted">候选边(关系类型尚未判定)</span>';
bar.innerHTML = `论文 ${DATA.n_papers} · 边 ${DATA.n_edges} &nbsp; ${legend}`;

const byId = {}; DATA.nodes.forEach(n=>byId[n.id]=n);
const adj = {};
DATA.edges.forEach(e=>{ (adj[e.from]=adj[e.from]||[]).push([e.to,e]); (adj[e.to]=adj[e.to]||[]).push([e.from,e]); });

network.on('click', p=>{
  if(!p.nodes.length){return;}
  const id = p.nodes[0]; const c = byId[id].card;
  const tags = a => (a||[]).map(t=>`<span class="tag">${t}</span>`).join('');
  let nbrs = (adj[id]||[]).sort((x,y)=>y[1].score-x[1].score).map(([m,e])=>{
    const rel = e.relation;
    const relbadge = `<span class="rel" style="background:${REL_COLORS[rel]||'#999'}">${rel}</span>`;
    return `<div class="nbr"><b>${m}</b> ${relbadge} <span class="muted">${e.score.toFixed(1)}</span><br>
      <span class="muted">${byId[m].card.title||''}</span><br>
      <span class="muted">共享: ${e.shared}</span>${e.rationale?`<br>${e.rationale}`:''}</div>`;
  }).join('');
  document.getElementById('side').innerHTML = `
    <h2>${id} · ${c.title||''}</h2>
    <p class="muted">${c.year||''}</p>
    <p><b>卡片版本:</b> ${c.schema_version||'<span class=muted>—</span>'}</p>
    <p><b>目标/问题:</b> ${c.objective||'<span class=muted>—</span>'}</p>
    ${c.main_findings.length?`<p><b>方向级发现:</b></p><ul>${c.main_findings.map(k=>`<li>${k}</li>`).join('')}</ul>`:''}
    ${c.methods_systems?`<p><b>方法/系统:</b> ${c.methods_systems}</p>`:''}
    <p><b>主题:</b> ${tags(c.topics)}</p>
    <p><b>方法:</b> ${tags(c.methods)}</p>
    <p><b>对象:</b> ${tags(c.objects)}</p>
    <h2>邻居 (${(adj[id]||[]).length})</h2>${nbrs||'<p class=muted>无</p>'}`;
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
