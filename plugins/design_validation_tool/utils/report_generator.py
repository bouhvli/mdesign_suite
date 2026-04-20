import csv
import os
from datetime import datetime

from .extract_design_session import extract_design_session_name


# ── helpers ───────────────────────────────────────────────────────────────────

_CATEGORY_MAP = {
    'POC':          {'tag': 'POC',          'label': 'Placement Accuracy',     'color': '#5c6bc0'},
    'TRENCH':       {'tag': 'TRENCH',       'label': 'Trench Integrity',       'color': '#ff7043'},
    'DISTRIBUTION': {'tag': 'DISTRIBUTION', 'label': 'Distribution Integrity', 'color': '#42a5f5'},
    'FEEDER':       {'tag': 'FEEDER',       'label': 'Feeder Integrity',       'color': '#ffca28'},
    'DATA_QUALITY': {'tag': 'DATA_Q',       'label': 'Data Quality',           'color': '#26a69a'},
    'FEATURE_LOCK': {'tag': 'FEAT. LOCK',   'label': 'Feature Lock Status',    'color': '#ab47bc'},
    'OVERLAPPING':  {'tag': 'OVERLAP',      'label': 'Overlap Detection',      'color': '#ef5350'},
    'CROSSINGS':    {'tag': 'CROSSINGS',    'label': 'Crossing Accuracy',      'color': '#8d6e63'},
    'OTHER':        {'tag': 'OTHER',        'label': 'Other',                  'color': '#90a4ae'},
}


def _category(rule_id):
    rid = (rule_id or '').upper()
    if rid.startswith('POC'):           return 'POC'
    if rid.startswith('TRENCH'):        return 'TRENCH'
    if rid.startswith('DIST'):          return 'DISTRIBUTION'
    if rid.startswith('FEEDER'):        return 'FEEDER'
    if rid.startswith('DATA_Q'):        return 'DATA_QUALITY'
    if rid.startswith('FEATURE_LOCK'):  return 'FEATURE_LOCK'
    if rid.startswith('OVERLAP'):       return 'OVERLAPPING'
    if rid.startswith('CROSS'):         return 'CROSSINGS'
    return 'OTHER'


def _chips_html(features_str, total):
    if not features_str:
        return '<span style="color:#bbb;font-size:12px;">No feature details available</span>'
    items = [f.strip() for f in features_str.split(',') if f.strip()]
    MAX = 6
    shown = items[:MAX]
    more  = total - len(shown)
    html  = ''.join(f'<span class="chip">{f}</span>' for f in shown)
    if more > 0:
        html += f'<span class="chip more">+{more} more</span>'
    return html


def _category_score(rules, cat):
    cat_rules = [r for r in rules if _category(r.get('rule_id','')) == cat]
    if not cat_rules:
        return 100.0
    passing = sum(1 for r in cat_rules if r.get('status','FAIL') == 'PASS')
    return round(passing / len(cat_rules) * 100, 1)


# ── section builders ──────────────────────────────────────────────────────────

def _build_category_cards(rules):
    cats_seen = {}
    for r in rules:
        c = _category(r.get('rule_id',''))
        cats_seen.setdefault(c, 0)
        cats_seen[c] += r.get('violation_count', 0)

    top3 = sorted(cats_seen.items(), key=lambda x: x[1], reverse=True)[:3]
    html = ''
    for cat, _ in top3:
        meta  = _CATEGORY_MAP.get(cat, _CATEGORY_MAP['OTHER'])
        score = _category_score(rules, cat)
        html += f'''
        <div class="category-card" style="border-left:4px solid {meta["color"]}">
            <div class="cat-tag" style="color:{meta["color"]}">{meta["tag"]}</div>
            <div class="cat-name">{meta["label"]}</div>
            <div class="cat-score">{score}%</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width:{score}%;background:{meta["color"]}"></div>
            </div>
        </div>'''
    return html


def _build_ruleset_rows(rules):
    rows = ''
    for r in rules:
        status = r.get('status', 'FAIL')
        count  = r.get('violation_count', 0)
        sc     = 'pass' if status == 'PASS' else 'fail'
        rows += f'''
        <tr>
            <td><span class="rule-id">{r.get("rule_id","")}</span></td>
            <td class="desc-cell">{r.get("Description","")}</td>
            <td><span class="badge badge-{sc}"><span class="dot dot-{sc}"></span>{status}</span></td>
            <td class="num-cell">{count}</td>
        </tr>'''
    return rows


def _build_hotspots(rules):
    failing = [r for r in rules if r.get('status','FAIL') != 'PASS' and r.get('violation_count',0) > 0]
    top3    = sorted(failing, key=lambda x: x.get('violation_count',0), reverse=True)[:3]
    html    = ''
    for r in top3:
        rid   = r.get('rule_id','')
        short = (r.get('message','') or r.get('Description',''))[:42]
        count = r.get('violation_count', 0)
        html += f'''
        <div class="hotspot-item">
            <div class="hotspot-count">{count}</div>
            <div class="hotspot-info">
                <div class="hotspot-rule">{rid}</div>
                <div class="hotspot-desc">{short}</div>
            </div>
            <div class="hotspot-arrow">&#8250;</div>
        </div>'''
    return html


def _build_filter_tabs(rules):
    cats = {}
    for r in rules:
        if r.get('status','FAIL') == 'PASS':
            continue
        c = _category(r.get('rule_id',''))
        cats[c] = cats.get(c, 0) + r.get('violation_count', 0)
    html = ''
    for cat, count in cats.items():
        meta  = _CATEGORY_MAP.get(cat, _CATEGORY_MAP['OTHER'])
        label = meta['label']
        html += f'<button class="tab-btn" onclick="filterViolations(\'{cat}\',this)">{label} ({count})</button>'
    return html


def _build_violation_cards(rules):
    html = ''
    for r in rules:
        if r.get('status','FAIL') == 'PASS':
            continue
        cat      = _category(r.get('rule_id',''))
        count    = r.get('violation_count', 0)
        rule_id  = r.get('rule_id','')
        desc     = r.get('Description','')
        features = r.get('failed_features','')

        if cat == 'FEATURE_LOCK':
            html += f'''
            <div class="vcard vcard-dark vcard-full" data-cat="{cat}">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-size:22px;margin-bottom:8px;">&#128274;</div>
                        <div class="vcard-rule">{rule_id}</div>
                        <div class="vcard-desc" style="color:rgba(255,255,255,0.55)">{desc}</div>
                    </div>
                    <div style="text-align:right">
                        <div class="dark-count">{count}</div>
                        <div class="dark-label">Unlocked Features</div>
                    </div>
                </div>
            </div>'''
        else:
            chips = _chips_html(features, count)
            unit  = 'FAILURES'
            html += f'''
            <div class="vcard" data-cat="{cat}">
                <div class="vcard-header">
                    <div>
                        <div class="vcard-rule">{rule_id}</div>
                        <div class="vcard-desc">{desc}</div>
                    </div>
                    <span class="failure-badge">{count} {unit}</span>
                </div>
                <div class="features-label">Failed Features</div>
                <div class="chip-row">{chips}</div>
            </div>'''
    return html


# ── CSS & JS ──────────────────────────────────────────────────────────────────

_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:#eef0f8;color:#1a1f3c}
a{text-decoration:none;color:inherit}

/* layout */
.app{display:flex;min-height:100vh}
.sidebar{width:230px;background:#1a1f3c;color:#fff;padding:24px 0;position:fixed;
    height:100vh;overflow-y:auto;z-index:100}
.main{margin-left:230px;flex:1}

/* sidebar */
.sb-logo{display:flex;align-items:center;gap:10px;padding:0 20px 24px;
    border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:12px}
.sb-icon{width:36px;height:36px;background:#5c6bc0;border-radius:8px;
    display:flex;align-items:center;justify-content:center;font-size:18px}
.sb-name{font-size:14px;font-weight:700}
.nav-item{display:flex;align-items:center;gap:10px;padding:13px 20px;
    font-size:13px;color:rgba(255,255,255,.55);cursor:pointer;border-left:3px solid transparent}
.nav-item.active,.nav-item:hover{color:#fff;background:rgba(92,107,192,.25);border-left-color:#5c6bc0}

/* topbar */
.topbar{background:#fff;padding:15px 32px;display:flex;align-items:center;
    justify-content:space-between;border-bottom:1px solid #e0e0e0;
    position:sticky;top:0;z-index:50}
.project-name{font-size:18px;font-weight:800;color:#1a1f3c}
.last-run{font-size:12px;color:#888;margin-left:16px}
.search-box{display:flex;align-items:center;gap:8px;background:#f5f5f5;
    border-radius:8px;padding:8px 14px;width:240px}
.search-box input{border:none;background:none;outline:none;font-size:13px;width:100%}

/* pages */
.page{display:none;padding:28px 32px}
.page.active{display:block}

/* dashboard – metrics row */
.metrics-row{display:flex;gap:18px;margin-bottom:22px;flex-wrap:wrap}
.score-card{background:#fff;border-radius:14px;padding:28px;min-width:210px;
    box-shadow:0 2px 10px rgba(0,0,0,.06);display:flex;flex-direction:column}
.score-label{font-size:11px;font-weight:600;text-transform:uppercase;
    color:#999;letter-spacing:1px;margin-bottom:10px}
.score-value{font-size:54px;font-weight:900;color:#1a1f3c;line-height:1}
.score-suffix{font-size:24px;font-weight:400}
.viol-label{font-size:10px;text-transform:uppercase;color:#bbb;letter-spacing:1px;margin-top:14px}
.viol-count{font-size:30px;font-weight:700;color:#ef5350;display:inline}
.viol-delta{display:inline-block;background:#fce4ec;color:#ef5350;
    font-size:11px;padding:3px 8px;border-radius:10px;margin-left:8px}

.category-card{background:#fff;border-radius:14px;padding:20px 22px;flex:1;min-width:150px;
    box-shadow:0 2px 10px rgba(0,0,0,.06)}
.cat-tag{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.cat-name{font-size:13px;color:#666;margin-bottom:6px}
.cat-score{font-size:28px;font-weight:800;color:#1a1f3c;margin-bottom:10px}
.progress-bar{height:4px;background:#e0e0e0;border-radius:2px;overflow:hidden}
.progress-fill{height:100%;border-radius:2px}

/* dashboard – bottom row */
.bottom-row{display:flex;gap:18px}
.ruleset-panel{background:#fff;border-radius:14px;padding:24px;flex:1;
    box-shadow:0 2px 10px rgba(0,0,0,.06);overflow:hidden}
.panel-title{font-size:16px;font-weight:700;margin-bottom:4px}
.panel-sub{font-size:12px;color:#999;margin-bottom:18px}
table{width:100%;border-collapse:collapse}
th{font-size:10px;text-transform:uppercase;color:#bbb;letter-spacing:1px;
    padding:8px 12px;text-align:left;border-bottom:1px solid #f0f0f0}
td{padding:11px 12px;font-size:13px;border-bottom:1px solid #f8f8f8;color:#444}
tr:last-child td{border-bottom:none}
.rule-id{font-family:monospace;font-weight:700;color:#3f51b5;font-size:12px}
.desc-cell{color:#555;max-width:280px}
.num-cell{font-weight:700;color:#1a1f3c}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
    border-radius:10px;font-size:11px;font-weight:600}
.badge-fail{background:#fdecea;color:#ef5350}
.badge-pass{background:#e8f5e9;color:#4caf50}
.badge-error{background:#fff3e0;color:#ff9800}
.dot{width:6px;height:6px;border-radius:50%}
.dot-fail{background:#ef5350}
.dot-pass{background:#4caf50}
.dot-error{background:#ff9800}

/* hotspots */
.hotspots-panel{background:#fff;border-radius:14px;padding:24px;width:300px;
    box-shadow:0 2px 10px rgba(0,0,0,.06);flex-shrink:0}
.hs-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.hs-title{font-size:16px;font-weight:700}
.hs-warn{color:#ff9800;font-size:20px}
.hotspot-item{display:flex;align-items:center;gap:12px;padding:12px 0;
    border-bottom:1px solid #f5f5f5;cursor:pointer}
.hotspot-item:last-of-type{border-bottom:none}
.hotspot-count{background:#fdecea;color:#ef5350;font-size:16px;font-weight:800;
    min-width:52px;height:52px;border-radius:10px;
    display:flex;align-items:center;justify-content:center}
.hotspot-info{flex:1;overflow:hidden}
.hotspot-rule{font-size:13px;font-weight:700;color:#1a1f3c}
.hotspot-desc{font-size:11px;color:#888;margin-top:2px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hotspot-arrow{color:#ccc;font-size:18px}
.view-all{display:block;text-align:center;font-size:12px;color:#5c6bc0;margin-top:14px;cursor:pointer}

/* violations explorer */
.exp-title{font-size:28px;font-weight:800;margin-bottom:6px}
.exp-desc{font-size:13px;color:#666;max-width:500px}
.exp-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:22px;flex-wrap:wrap;gap:12px}
.stat-boxes{display:flex;gap:12px}
.stat-box{background:#fff;border-radius:10px;padding:14px 22px;min-width:150px;
    box-shadow:0 2px 10px rgba(0,0,0,.06)}
.stat-box.crit{background:#fdecea}
.sb-lbl{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#bbb;margin-bottom:4px}
.stat-box.crit .sb-lbl{color:#ef9a9a}
.sb-val{font-size:32px;font-weight:900;color:#1a1f3c}
.stat-box.crit .sb-val{color:#ef5350}

.tabs{display:flex;gap:8px;margin-bottom:22px;flex-wrap:wrap;align-items:center}
.tab-btn{padding:8px 18px;border-radius:8px;font-size:13px;font-weight:500;
    border:none;cursor:pointer;background:#fff;color:#555}
.tab-btn.active{background:#1a1f3c;color:#fff}
.tab-btn:hover:not(.active){background:#dde1f7}
.export-btn{margin-left:auto;padding:8px 18px;border-radius:8px;border:1px solid #ddd;
    background:#fff;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:6px}

.vgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.vcard{background:#fff;border-radius:14px;padding:22px;box-shadow:0 2px 10px rgba(0,0,0,.06)}
.vcard-dark{background:#1a1f3c;color:#fff}
.vcard-full{grid-column:1/-1}
.vcard-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;gap:8px}
.vcard-rule{font-size:15px;font-weight:700;margin-bottom:5px}
.vcard-desc{font-size:12px;color:#888;line-height:1.5;margin-bottom:14px}
.failure-badge{background:#fdecea;color:#ef5350;font-size:10px;font-weight:700;
    padding:4px 10px;border-radius:10px;white-space:nowrap;flex-shrink:0}
.features-label{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#bbb;margin-bottom:8px}
.chip-row{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:#f0f0f0;color:#555;font-size:11px;padding:4px 10px;border-radius:6px}
.chip.more{background:#e8eaf6;color:#5c6bc0;font-weight:700;cursor:pointer}
.dark-count{font-size:52px;font-weight:900;color:#fff;line-height:1}
.dark-label{font-size:11px;text-transform:uppercase;letter-spacing:1px;
    color:rgba(255,255,255,.45);margin-top:4px}

/* footer */
.exp-footer{background:#fff;border-radius:14px;padding:18px 26px;margin-top:18px;
    display:flex;justify-content:space-between;align-items:center;
    box-shadow:0 2px 10px rgba(0,0,0,.06);font-size:12px;color:#888;flex-wrap:wrap;gap:10px}
.footer-meta{display:flex;gap:28px;flex-wrap:wrap}
.meta-item label{display:block;text-transform:uppercase;letter-spacing:1px;
    font-size:10px;color:#bbb;margin-bottom:2px}
.meta-item span{font-weight:700;color:#333}

/* print */
@media print{
    .sidebar{display:none}
    .main{margin-left:0}
    .topbar{position:static}
    .page{display:block !important}
    #page-explorer{page-break-before:always}
    .tabs,.export-btn{display:none !important}
    .vgrid{grid-template-columns:1fr 1fr}
    .bottom-row{flex-wrap:wrap}
    .hotspots-panel{width:100%}
    @page{margin:1.2cm}
}

@media(max-width:860px){
    .vgrid{grid-template-columns:1fr}
    .metrics-row{flex-direction:column}
    .bottom-row{flex-direction:column}
    .hotspots-panel{width:100%}
}
"""

_JS = """
function showPage(name) {
    document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active');});
    document.querySelectorAll('.nav-item').forEach(function(n){n.classList.remove('active');});
    document.getElementById('page-' + name).classList.add('active');
    var idx = name === 'dashboard' ? 0 : 1;
    document.querySelectorAll('.nav-item')[idx].classList.add('active');
}
function filterViolations(cat, btn) {
    document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
    btn.classList.add('active');
    document.querySelectorAll('.vcard').forEach(function(card){
        card.style.display = (cat === 'all' || card.dataset.cat === cat) ? '' : 'none';
    });
}
"""


# ── public API ────────────────────────────────────────────────────────────────

def generate_csv_report(path, output_directory, validation_results):
    report_path = f"validation_report_{extract_design_session_name(path)}.csv"
    output_path = os.path.join(output_directory, report_path)
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['rule_id', 'Description', 'status', 'violation_count', 'failed_features', 'message']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for result in validation_results:
            writer.writerow(result)
    return output_path


def generate_html_report(path, output_directory, validation_results):
    timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project     = extract_design_session_name(path)
    rules       = validation_results or []

    total_v     = sum(r.get('violation_count', 0) for r in rules)
    n_rules     = len(rules)
    n_pass      = sum(1 for r in rules if r.get('status','') == 'PASS')
    score       = round(n_pass / n_rules * 100, 1) if n_rules else 0.0

    cat_cards   = _build_category_cards(rules)
    ruleset     = _build_ruleset_rows(rules)
    hotspots    = _build_hotspots(rules)
    filter_tabs = _build_filter_tabs(rules)
    vcards      = _build_violation_cards(rules)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Validation Report – {project}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="app">

  <!-- SIDEBAR -->
  <nav class="sidebar">
    <div class="sb-logo">
      <div class="sb-icon">&#9873;</div>
      <span class="sb-name">Validation Engine</span>
    </div>
    <a class="nav-item active" href="#" onclick="showPage('dashboard');return false;">
      &#9632;&nbsp; Dashboard
    </a>
    <a class="nav-item" href="#" onclick="showPage('explorer');return false;">
      &#9783;&nbsp; Violations Explorer
    </a>
  </nav>

  <!-- MAIN -->
  <div class="main">

    <!-- TOPBAR -->
    <div class="topbar">
      <div style="display:flex;align-items:center">
        <span class="project-name">{project}</span>
        <span class="last-run">&#128197; Generated: {timestamp}</span>
      </div>
      <div class="search-box">
        <span>&#128269;</span>
        <input type="text" placeholder="Search violation rules&hellip;"
               oninput="searchRules(this.value)">
      </div>
    </div>

    <!-- ═══════════════════════════════════════ DASHBOARD PAGE -->
    <div class="page active" id="page-dashboard">

      <!-- metrics row -->
      <div class="metrics-row">

        <!-- score card -->
        <div class="score-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <div class="score-label">Overall Integrity Score</div>
              <div class="score-value">{score}<span class="score-suffix">%</span></div>
            </div>
            <div style="font-size:64px;color:#e8eaf6;line-height:1">&#10003;</div>
          </div>
          <div class="viol-label">Violations Detected</div>
          <div>
            <span class="viol-count">{total_v}</span>
          </div>
        </div>

        <!-- category cards -->
        {cat_cards}
      </div>

      <!-- bottom row -->
      <div class="bottom-row">

        <!-- ruleset table -->
        <div class="ruleset-panel">
          <div class="panel-title">Validation Ruleset</div>
          <div class="panel-sub">Compliance monitoring for {project} dataset</div>
          <table>
            <thead>
              <tr>
                <th>Rule ID</th>
                <th>Description</th>
                <th>Status</th>
                <th>Violations</th>
              </tr>
            </thead>
            <tbody id="ruleset-body">
              {ruleset}
            </tbody>
          </table>
        </div>

        <!-- hotspots -->
        <div class="hotspots-panel">
          <div class="hs-header">
            <span class="hs-title">Critical Hotspots</span>
            <span class="hs-warn">&#9888;</span>
          </div>
          {hotspots}
          <a class="view-all" href="#"
             onclick="showPage('explorer');return false;">View All Critical Failure Logs</a>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════ VIOLATIONS EXPLORER PAGE -->
    <div class="page" id="page-explorer">

      <div class="exp-top">
        <div>
          <div class="exp-title">Violations Explorer</div>
          <div class="exp-desc">
            Technical audit focusing on schema non-compliance and topological
            inconsistencies for the {project} network segment.
          </div>
        </div>
        <div class="stat-boxes">
          <div class="stat-box crit">
            <div class="sb-lbl">Critical Failures</div>
            <div class="sb-val">{total_v}</div>
          </div>
          <div class="stat-box">
            <div class="sb-lbl">Rules Evaluated</div>
            <div class="sb-val">{n_rules}</div>
          </div>
        </div>
      </div>

      <!-- filter tabs -->
      <div class="tabs">
        <button class="tab-btn active"
                onclick="filterViolations('all',this)">All Violations</button>
        {filter_tabs}
        <button class="export-btn" onclick="window.print()">
          &#8595; Export Log
        </button>
      </div>

      <!-- violation cards -->
      <div class="vgrid" id="vgrid">
        {vcards}
      </div>

      <!-- footer -->
      <div class="exp-footer">
        <div class="footer-meta">
          <div class="meta-item">
            <label>Data Source</label>
            <span>{project}</span>
          </div>
          <div class="meta-item">
            <label>Evaluation Logic</label>
            <span>Design validation plugin</span>
          </div>
          <div class="meta-item">
            <label>Generated</label>
            <span>{timestamp}</span>
          </div>
        </div>
        <div style="color:#bbb;font-size:12px">
          All technical data is subject to auditor verification. &#9432;
        </div>
      </div>
    </div>

  </div><!-- /main -->
</div><!-- /app -->

<script>
{_JS}
function searchRules(q) {{
    q = q.toLowerCase();
    document.querySelectorAll('#ruleset-body tr').forEach(function(tr) {{
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
    }});
}}
</script>
</body>
</html>"""

    report_name = f"validation_report_{project}.html"
    output_path = os.path.join(output_directory, report_name)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path
