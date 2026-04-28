import csv
import os
from datetime import datetime

from .extract_design_session import extract_design_session_name


_CAT = {
    'POC':          {'tag': 'POC',          'label': 'Placement Accuracy',     'color': '#3b82f6'},
    'TRENCH':       {'tag': 'TRENCH',       'label': 'Trench Integrity',       'color': '#ef4444'},
    'DISTRIBUTION': {'tag': 'DIST',         'label': 'Distribution Integrity', 'color': '#10b981'},
    'FEEDER':       {'tag': 'FEEDER',       'label': 'Feeder Integrity',       'color': '#f59e0b'},
    'DATA_QUALITY': {'tag': 'DATA Q',       'label': 'Data Quality',           'color': '#8b5cf6'},
    'FEATURE_LOCK': {'tag': 'FEAT LOCK',    'label': 'Feature Lock',           'color': '#ec4899'},
    'OVERLAPPING':  {'tag': 'OVERLAP',      'label': 'Overlap Detection',      'color': '#f97316'},
    'CROSSINGS':    {'tag': 'CROSSINGS',    'label': 'Crossing Accuracy',      'color': '#64748b'},
    'OTHER':        {'tag': 'OTHER',        'label': 'Other',                  'color': '#94a3b8'},
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


def _split_features(s):
    if not s:
        return []
    return [f.strip() for f in str(s).split(',') if f.strip()]


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
    background: #f8fafc;
    color: #0f172a;
    font-size: 14px;
    line-height: 1.5;
}

.page { max-width: 1280px; margin: 0 auto; padding: 32px 24px; }

/* ── Header ── */
.header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 28px;
    gap: 16px;
    flex-wrap: wrap;
}
.header-title {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 10px;
}
.header-badge {
    background: #e2e8f0;
    color: #475569;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 40px;
}
.header-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; }

/* ── Toolbar (search + filters) ── */
.toolbar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 16px 20px;
    margin-bottom: 20px;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
}
.search-box {
    display: flex;
    align-items: center;
    gap: 8px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 14px;
    min-width: 260px;
    flex: 1;
}
.search-box:focus-within { border-color: #3b82f6; background: #fff; }
.search-box input {
    border: none; outline: none;
    background: transparent;
    font-size: 13px; width: 100%;
}
.search-icon { color: #94a3b8; font-size: 14px; }

.divider { width: 1px; height: 32px; background: #e2e8f0; }

.filter-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.pill-btn {
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    border-radius: 40px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 500;
    color: #475569;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.1s;
}
.pill-btn:hover { background: #f1f5f9; border-color: #cbd5e1; }
.pill-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; }
.pill-count {
    background: rgba(255,255,255,0.15);
    padding: 1px 7px;
    border-radius: 40px;
    font-size: 10px;
    margin-left: 3px;
}
.pill-btn:not(.active) .pill-count { background: #e2e8f0; color: #475569; }

/* ── Summary bar ── */
.summary-bar {
    display: flex;
    gap: 20px;
    margin-bottom: 16px;
    font-size: 13px;
    color: #64748b;
    flex-wrap: wrap;
}
.summary-bar strong { color: #0f172a; }
.summary-bar .fail-count { color: #dc2626; font-weight: 700; }
.summary-bar .pass-count { color: #16a34a; font-weight: 700; }

/* ── Table ── */
.table-wrap {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    overflow: hidden;
}
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
thead th {
    text-align: left;
    padding: 12px 14px;
    background: #f8fafc;
    color: #64748b;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    border-bottom: 1px solid #e2e8f0;
    white-space: nowrap;
}
thead th.sortable { cursor: pointer; user-select: none; }
thead th.sortable:hover { color: #0f172a; }
tbody tr { border-bottom: 1px solid #f1f5f9; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: #fafbfc; }
tbody tr.row-pass { opacity: 0.55; }
tbody tr.row-pass:hover { opacity: 1; }
td { padding: 14px 14px; vertical-align: top; }

.rule-code {
    font-family: 'Consolas', 'Fira Code', monospace;
    font-size: 11px;
    font-weight: 700;
    background: #eef2ff;
    color: #2563eb;
    padding: 3px 8px;
    border-radius: 6px;
    white-space: nowrap;
}
.cat-tag {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 40px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
}
.status-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 40px;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
}
.status-pass  { background: #dcfce7; color: #15803d; }
.status-fail  { background: #fef2f2; color: #dc2626; }
.status-error { background: #fffbeb; color: #d97706; }

.vcount { font-weight: 700; color: #0f172a; }
.vcount-zero { color: #94a3b8; }

.desc-text { color: #334155; max-width: 380px; }
.desc-msg   { color: #64748b; font-size: 12px; margin-top: 3px; }

.chips { display: flex; flex-wrap: wrap; gap: 5px; max-width: 260px; }
.chip {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 11px;
    font-family: monospace;
}
.chip-more {
    background: #e2e8f0;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 500;
    color: #475569;
    cursor: pointer;
}
.hidden-chips { display: none; flex-wrap: wrap; gap: 5px; margin-top: 5px; }

.copy-btn {
    border: 1px solid #e2e8f0;
    background: none;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 10px;
    font-weight: 600;
    color: #64748b;
    cursor: pointer;
    white-space: nowrap;
}
.copy-btn:hover { background: #f1f5f9; color: #0f172a; }
.copy-btn.done  { color: #16a34a; border-color: #bbf7d0; }

.empty-state {
    text-align: center;
    padding: 56px 24px;
    color: #94a3b8;
    font-size: 14px;
}
"""

# ── JS ────────────────────────────────────────────────────────────────────────
_JS = """
let _cat = 'all';
let _status = 'all';
let _q = '';

function setFilter(type, value, btn) {
    if (type === 'cat')    { _cat    = value; }
    if (type === 'status') { _status = value; }
    const group = btn.closest('.filter-pills');
    group.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    applyFilters();
}

function onSearch(input) {
    _q = input.value.trim().toLowerCase();
    applyFilters();
}

function applyFilters() {
    const rows = document.querySelectorAll('tbody tr.data-row');
    let vis = 0;
    rows.forEach(row => {
        const catOk    = _cat    === 'all' || row.dataset.cat    === _cat;
        const statusOk = _status === 'all' || row.dataset.status === _status;
        const searchOk = !_q || row.dataset.search.includes(_q);
        const show = catOk && statusOk && searchOk;
        row.style.display = show ? '' : 'none';
        if (show) vis++;
    });
    document.getElementById('vis-count').textContent = vis;
    document.getElementById('empty-state').style.display = vis ? 'none' : '';
}

function expandRow(el) {
    const container = el.closest('.chips');
    const hidden = container.nextElementSibling;
    if (hidden && hidden.classList.contains('hidden-chips')) {
        const open = hidden.style.display === 'flex';
        hidden.style.display = open ? 'none' : 'flex';
        el.textContent = open ? '+' + hidden.querySelectorAll('.chip').length + ' more' : 'show less';
    }
}

function copyIds(btn) {
    const text = btn.dataset.copy || '';
    navigator.clipboard?.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('done');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('done'); }, 1400);
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1400);
    });
}
"""


# ── helpers ───────────────────────────────────────────────────────────────────

def _filter_pills_cat(rules):
    counts = {}
    for r in rules:
        c = _category(r.get('rule_id', ''))
        counts[c] = counts.get(c, 0) + 1

    html = '<button class="pill-btn active" onclick="setFilter(\'cat\',\'all\',this)">All categories</button>'
    for cat, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        m = _CAT.get(cat, _CAT['OTHER'])
        html += (
            f'<button class="pill-btn" onclick="setFilter(\'cat\',\'{cat}\',this)">'
            f'{m["label"]} <span class="pill-count">{cnt}</span></button>'
        )
    return html


def _filter_pills_status(rules):
    n_fail = sum(1 for r in rules if r.get('status', '') != 'PASS')
    n_pass = sum(1 for r in rules if r.get('status', '') == 'PASS')
    return (
        '<button class="pill-btn active" onclick="setFilter(\'status\',\'all\',this)">All statuses</button>'
        f'<button class="pill-btn" onclick="setFilter(\'status\',\'fail\',this)">Fail <span class="pill-count">{n_fail}</span></button>'
        f'<button class="pill-btn" onclick="setFilter(\'status\',\'pass\',this)">Pass <span class="pill-count">{n_pass}</span></button>'
    )


def _table_rows(rules):
    rows = []
    for r in rules:
        rule_id = r.get('rule_id', '')
        status  = r.get('status', 'FAIL').upper()
        cat     = _category(rule_id)
        m       = _CAT.get(cat, _CAT['OTHER'])
        count   = r.get('violation_count', 0)
        desc    = r.get('Description', '') or ''
        msg     = r.get('message', '') or ''
        feats   = _split_features(r.get('failed_features', ''))

        status_lc  = status.lower()
        row_class  = 'row-pass' if status == 'PASS' else ''
        search_val = f"{rule_id} {desc} {msg} {r.get('failed_features','')}".lower()

        # chips
        preview    = feats[:5]
        extra      = feats[5:]
        chips_html = ''.join(f'<span class="chip">{f}</span>' for f in preview)
        if extra:
            hidden_html = ''.join(f'<span class="chip">{f}</span>' for f in extra)
            chips_html += (
                f'<span class="chip-more" onclick="expandRow(this)">+{len(extra)} more</span>'
                f'</div><div class="hidden-chips">{hidden_html}'
            )
        copy_val   = ','.join(feats).replace('"', '&quot;')
        copy_cell  = (
            f'<button class="copy-btn" data-copy="{copy_val}" onclick="copyIds(this)">Copy</button>'
            if feats else ''
        )

        count_html = (
            f'<span class="vcount">{count}</span>'
            if count else
            '<span class="vcount-zero">—</span>'
        )

        rows.append(f'''
<tr class="data-row {row_class}"
    data-cat="{cat}"
    data-status="{status_lc}"
    data-search="{search_val}">
  <td><span class="rule-code">{rule_id}</span></td>
  <td><span class="cat-tag" style="background:{m["color"]}18; color:{m["color"]}">{m["tag"]}</span></td>
  <td>
    <div class="desc-text">{desc}</div>
    {f'<div class="desc-msg">{msg}</div>' if msg and msg != desc else ''}
  </td>
  <td><span class="status-pill status-{status_lc}">{status}</span></td>
  <td>{count_html}</td>
  <td><div class="chips">{chips_html}</div><div class="hidden-chips" style="display:none"></div></td>
  <td>{copy_cell}</td>
</tr>''')
    return ''.join(rows)


# ── public API ────────────────────────────────────────────────────────────────

def generate_csv_report(path, output_directory, validation_results):
    report_path = f"validation_report_{extract_design_session_name(path)}.csv"
    output_path = os.path.join(output_directory, report_path)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['rule_id', 'Description', 'status', 'violation_count', 'failed_features', 'message']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in validation_results:
            writer.writerow(result)
    return output_path


def generate_html_report(path, output_directory, validation_results):
    timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M")
    project   = extract_design_session_name(path)
    rules     = validation_results or []

    n_total = len(rules)
    n_pass  = sum(1 for r in rules if r.get('status', '') == 'PASS')
    n_fail  = n_total - n_pass
    total_v = sum(r.get('violation_count', 0) for r in rules)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Validation Report — {project}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <header class="header">
    <div>
      <div class="header-title">
        {project}
        <span class="header-badge">{n_total} rules</span>
      </div>
      <div class="header-meta">Generated {timestamp}</div>
    </div>
  </header>

  <!-- Toolbar -->
  <div class="toolbar">
    <div class="search-box">
      <span class="search-icon">&#128269;</span>
      <input type="text" placeholder="Search rule ID, description, feature…" oninput="onSearch(this)">
    </div>

    <div class="divider"></div>

    <div class="filter-pills">
      {_filter_pills_cat(rules)}
    </div>

    <div class="divider"></div>

    <div class="filter-pills">
      {_filter_pills_status(rules)}
    </div>
  </div>

  <!-- Summary bar -->
  <div class="summary-bar">
    <span>Showing <strong id="vis-count">{n_total}</strong> of {n_total} rules</span>
    <span><span class="fail-count">{n_fail}</span> failing &nbsp;·&nbsp; <span class="pass-count">{n_pass}</span> passing</span>
    <span>Total violations: <strong>{total_v}</strong></span>
  </div>

  <!-- Table -->
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Rule ID</th>
          <th>Category</th>
          <th>Description</th>
          <th>Status</th>
          <th>Violations</th>
          <th>Features</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {_table_rows(rules)}
        <tr id="empty-state" style="display:none">
          <td colspan="7">
            <div class="empty-state">No rules match your filter.</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

</div>
<script>{_JS}</script>
</body>
</html>"""

    name = f"validation_report_{project}.html"
    out  = os.path.join(output_directory, name)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    return out
