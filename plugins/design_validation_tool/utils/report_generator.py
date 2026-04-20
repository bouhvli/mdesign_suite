import csv
import os
from datetime import datetime

from .extract_design_session import extract_design_session_name


# ── category metadata ─────────────────────────────────────────────────────────

_CAT = {
    'POC':          {'tag': 'POC',          'label': 'Placement Accuracy',     'color': '#4f6bed'},
    'TRENCH':       {'tag': 'TRENCH',       'label': 'Trench Integrity',       'color': '#e8663d'},
    'DISTRIBUTION': {'tag': 'DISTRIBUTION', 'label': 'Distribution Integrity', 'color': '#3aa8c1'},
    'FEEDER':       {'tag': 'FEEDER',       'label': 'Feeder Integrity',       'color': '#c8a020'},
    'DATA_QUALITY': {'tag': 'DATA QUALITY', 'label': 'Data Quality',           'color': '#3dab7e'},
    'FEATURE_LOCK': {'tag': 'FEAT. LOCK',   'label': 'Feature Lock',           'color': '#9b59b6'},
    'OVERLAPPING':  {'tag': 'OVERLAP',      'label': 'Overlap Detection',      'color': '#c0392b'},
    'CROSSINGS':    {'tag': 'CROSSINGS',    'label': 'Crossing Accuracy',      'color': '#7f8c8d'},
    'OTHER':        {'tag': 'OTHER',        'label': 'Other',                  'color': '#95a5a6'},
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


def _category_pass_rate(rules, cat):
    subset = [r for r in rules if _category(r.get('rule_id', '')) == cat]
    if not subset:
        return 100.0
    passing = sum(1 for r in subset if r.get('status', '') == 'PASS')
    return round(passing / len(subset) * 100, 1)


def _split_features(s):
    if not s:
        return []
    return [f.strip() for f in str(s).split(',') if f.strip()]


# ── section builders ──────────────────────────────────────────────────────────

def _category_cards(rules):
    counts = {}
    for r in rules:
        c = _category(r.get('rule_id', ''))
        counts[c] = counts.get(c, 0) + r.get('violation_count', 0)

    top3 = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:3]
    html = ''
    for cat, _ in top3:
        m     = _CAT.get(cat, _CAT['OTHER'])
        score = _category_pass_rate(rules, cat)
        html += f'''
        <div class="cat-card" style="--accent:{m["color"]}">
            <div class="cat-tag">{m["tag"]}</div>
            <div class="cat-name">{m["label"]}</div>
            <div class="cat-score">{score}<span class="cat-pct">%</span></div>
            <div class="bar"><div class="bar-fill" style="width:{score}%"></div></div>
        </div>'''
    return html


def _ruleset_rows(rules):
    rows = ''
    for r in rules:
        status = r.get('status', 'FAIL')
        count  = r.get('violation_count', 0)
        sc     = status.lower() if status in ('PASS', 'FAIL') else 'error'
        rows  += f'''
        <tr data-rid="{r.get("rule_id","").lower()}">
            <td><code class="rule-id">{r.get("rule_id","")}</code></td>
            <td class="desc">{r.get("Description","")}</td>
            <td><span class="pill pill-{sc}">{status}</span></td>
            <td class="num">{count}</td>
        </tr>'''
    return rows


def _hotspot_items(rules):
    failing = [r for r in rules
               if r.get('status', 'FAIL') != 'PASS' and r.get('violation_count', 0) > 0]
    top3 = sorted(failing, key=lambda x: x.get('violation_count', 0), reverse=True)[:3]
    html = ''
    for r in top3:
        rid   = r.get('rule_id', '')
        note  = (r.get('message', '') or r.get('Description', ''))[:46]
        count = r.get('violation_count', 0)
        html += f'''
        <div class="hs-item">
            <div class="hs-count">{count}</div>
            <div class="hs-info">
                <div class="hs-rule">{rid}</div>
                <div class="hs-note">{note}</div>
            </div>
            <div class="hs-arrow">&#8250;</div>
        </div>'''
    return html


def _filter_tabs(rules):
    cats = {}
    for r in rules:
        if r.get('status', '') == 'PASS':
            continue
        c = _category(r.get('rule_id', ''))
        cats[c] = cats.get(c, 0) + r.get('violation_count', 0)

    html = ''
    for cat, total in cats.items():
        label = _CAT.get(cat, _CAT['OTHER'])['label']
        html += f'<button class="tab" onclick="filter(\'{cat}\',this)">{label} <span class="tab-count">{total}</span></button>'
    return html


def _violation_cards(rules):
    html = ''
    for r in rules:
        status = r.get('status', '')
        if status == 'PASS':
            continue
        cat     = _category(r.get('rule_id', ''))
        m       = _CAT.get(cat, _CAT['OTHER'])
        count   = r.get('violation_count', 0)
        rule_id = r.get('rule_id', '')
        desc    = r.get('Description', '') or ''
        message = r.get('message', '') or ''
        feats   = _split_features(r.get('failed_features', ''))

        if status == 'ERROR' or (status != 'FAIL' and count == 0 and message):
            html += f'''
            <div class="vcard vcard-error" data-cat="{cat}" data-search="{rule_id.lower()} {message.lower()} {desc.lower()}">
                <div class="vcard-head">
                    <span class="vcard-status-pill pill-error-inline">ERROR</span>
                    <code class="vcard-rule-id">{rule_id}</code>
                </div>
                <div class="vcard-headline">{message or desc or 'Rule could not be evaluated'}</div>
                <div class="vcard-sub">Rule could not run — check required layers or fields.</div>
            </div>'''
            continue

        if cat == 'FEATURE_LOCK':
            sample = ', '.join(feats[:5])
            more_lock = max(0, len(feats) - 5)
            html += f'''
            <div class="vcard vcard-dark vcard-wide" data-cat="{cat}" data-search="{rule_id.lower()} {message.lower()} {desc.lower()} {(r.get('failed_features','') or '').lower()}">
                <div class="vcard-dark-inner">
                    <div>
                        <div class="vcard-dark-tag">FEATURE LOCK</div>
                        <div class="vcard-dark-rule">{rule_id}</div>
                        <div class="vcard-dark-desc">{message or desc}</div>
                        {f'<div class="vcard-dark-sample">Examples: {sample}{f" (+{more_lock} more)" if more_lock else ""}</div>' if sample else ''}
                    </div>
                    <div class="vcard-dark-stat">
                        <div class="vcard-dark-count">{count}</div>
                        <div class="vcard-dark-unit">unlocked features</div>
                    </div>
                </div>
            </div>'''
            continue

        PREVIEW = 8
        shown   = feats[:PREVIEW]
        hidden  = feats[PREVIEW:]
        preview_chips = ''.join(f'<span class="chip">{f}</span>' for f in shown)
        hidden_chips  = ''.join(f'<span class="chip">{f}</span>' for f in hidden)
        expand_btn    = ''
        if hidden:
            expand_btn = (
                f'<button type="button" class="chip-toggle" onclick="toggleChips(this)">'
                f'Show {len(hidden)} more</button>'
            )
        copy_payload = (r.get('failed_features', '') or '').replace('"', '&quot;')
        copy_btn = ''
        if feats:
            copy_btn = (
                f'<button type="button" class="copy-btn" '
                f'data-copy="{copy_payload}" onclick="copyFeatures(this)" '
                f'title="Copy feature IDs">Copy IDs</button>'
            )
        if not feats:
            body = f'<div class="no-features">No feature IDs reported.</div>'
        else:
            body = f'''
                <div class="chip-head">
                    <span class="chip-label">Affected features ({count})</span>
                    {copy_btn}
                </div>
                <div class="chip-row">{preview_chips}</div>
                <div class="chip-row chip-row-hidden" style="display:none">{hidden_chips}</div>
                {expand_btn}'''

        headline = message if message else desc
        subtext  = desc if (message and desc and message != desc) else ''

        html += f'''
        <div class="vcard" data-cat="{cat}" data-search="{rule_id.lower()} {message.lower()} {desc.lower()} {(r.get('failed_features','') or '').lower()}" style="--accent:{m["color"]}">
            <div class="vcard-head">
                <div class="vcard-cat-dot" style="background:{m["color"]}"></div>
                <code class="vcard-rule-id">{rule_id}</code>
                <span class="vcard-count">{count}</span>
            </div>
            <div class="vcard-headline">{headline}</div>
            {f'<div class="vcard-sub">{subtext}</div>' if subtext else ''}
            {body}
        </div>'''
    return html


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
*{margin:0;padding:0;box-sizing:border-box}

body{
    font-family:'Segoe UI',system-ui,Arial,sans-serif;
    background:#f0f2f7;
    color:#1c2232;
    font-size:13px;
    line-height:1.5;
}

/* ── layout ── */
.shell{display:flex;min-height:100vh}

/* ── sidebar ── */
.sidebar{
    width:220px;
    background:#0f1628;
    color:#fff;
    display:flex;
    flex-direction:column;
    position:fixed;
    top:0;left:0;
    height:100vh;
    z-index:200;
}
.sb-brand{
    display:flex;align-items:center;gap:10px;
    padding:22px 20px;
    border-bottom:1px solid rgba(255,255,255,.07);
}
.sb-brand-mark{
    width:32px;height:32px;
    background:#4f6bed;
    border-radius:7px;
    display:grid;place-items:center;
    font-size:13px;font-weight:900;color:#fff;
    letter-spacing:-1px;
}
.sb-brand-name{font-size:13px;font-weight:700;letter-spacing:.2px}
.sb-nav{padding:10px 0;flex:1}
.sb-link{
    display:flex;align-items:center;gap:9px;
    padding:11px 20px;
    font-size:12px;color:rgba(255,255,255,.5);
    cursor:pointer;
    border-left:2px solid transparent;
    transition:all .15s;
}
.sb-link:hover{color:#fff;background:rgba(255,255,255,.05)}
.sb-link.active{
    color:#fff;
    background:rgba(79,107,237,.18);
    border-left-color:#4f6bed;
}
.sb-link-icon{
    width:16px;height:16px;
    display:grid;place-items:center;
    opacity:.7;
    font-size:11px;
}
.sb-link.active .sb-link-icon{opacity:1}

/* ── main ── */
.main{margin-left:220px;flex:1;display:flex;flex-direction:column;min-height:100vh}

/* ── topbar ── */
.topbar{
    background:#fff;
    padding:13px 28px;
    display:flex;align-items:center;justify-content:space-between;
    border-bottom:1px solid #e4e7ef;
    position:sticky;top:0;z-index:100;
}
.tb-left{display:flex;align-items:baseline;gap:14px}
.tb-project{font-size:16px;font-weight:800;color:#0f1628}
.tb-run{font-size:11px;color:#9aa3b8}
.search{
    display:flex;align-items:center;gap:7px;
    background:#f4f6fb;border:1px solid #e4e7ef;
    border-radius:7px;padding:6px 12px;
}
.search input{
    border:none;background:none;outline:none;
    font-size:12px;color:#1c2232;width:200px;
}
.search-icon{color:#9aa3b8;font-size:13px}

/* ── pages ── */
.page{display:none;padding:24px 28px}
.page.active{display:block}

/* ── dashboard: top row ── */
.top-row{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}

.score-card{
    background:#fff;border-radius:12px;padding:26px 28px;
    box-shadow:0 1px 4px rgba(0,0,0,.06);
    min-width:200px;
    display:flex;flex-direction:column;justify-content:space-between;
}
.score-label{
    font-size:9px;font-weight:700;text-transform:uppercase;
    letter-spacing:1.2px;color:#9aa3b8;margin-bottom:12px;
}
.score-body{display:flex;align-items:flex-end;justify-content:space-between}
.score-number{
    font-size:52px;font-weight:900;color:#0f1628;line-height:1;
    letter-spacing:-2px;
}
.score-pct{font-size:22px;font-weight:400;letter-spacing:0}
.score-shield{
    width:56px;height:56px;
    border:3px solid #e8ebf5;border-radius:50%;
    display:grid;place-items:center;
    color:#c8cfe8;font-size:22px;font-weight:900;
}
.score-foot{margin-top:14px;padding-top:12px;border-top:1px solid #f0f2f7}
.score-foot-label{
    font-size:9px;font-weight:700;text-transform:uppercase;
    letter-spacing:1px;color:#9aa3b8;margin-bottom:3px;
}
.score-viol{font-size:26px;font-weight:800;color:#d94040}

.cat-card{
    background:#fff;border-radius:12px;padding:20px 20px 16px;
    box-shadow:0 1px 4px rgba(0,0,0,.06);flex:1;min-width:140px;
    border-top:3px solid var(--accent,#4f6bed);
}
.cat-tag{
    font-size:9px;font-weight:700;text-transform:uppercase;
    letter-spacing:1.2px;color:var(--accent,#4f6bed);margin-bottom:10px;
}
.cat-name{font-size:12px;color:#6e7890;margin-bottom:6px}
.cat-score{font-size:26px;font-weight:800;color:#0f1628;line-height:1;margin-bottom:10px}
.cat-pct{font-size:15px;font-weight:400}
.bar{height:3px;background:#eef0f7;border-radius:2px;overflow:hidden}
.bar-fill{height:100%;background:var(--accent,#4f6bed);border-radius:2px;transition:width .4s}

/* ── dashboard: bottom row ── */
.bottom-row{display:flex;gap:16px;align-items:flex-start}

.ruleset-card{
    background:#fff;border-radius:12px;padding:22px 24px;flex:1;
    box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden;
}
.card-title{font-size:14px;font-weight:700;color:#0f1628;margin-bottom:3px}
.card-sub{font-size:11px;color:#9aa3b8;margin-bottom:18px}

table{width:100%;border-collapse:collapse}
th{
    font-size:9px;font-weight:700;text-transform:uppercase;
    letter-spacing:1px;color:#9aa3b8;
    padding:7px 10px;text-align:left;
    border-bottom:1px solid #f0f2f7;
}
td{padding:10px;font-size:12px;border-bottom:1px solid #f8f9fc;color:#3d4761}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafbfd}
.rule-id{
    font-family:'Consolas','Courier New',monospace;
    font-size:11px;font-weight:700;color:#2d4be0;
    background:#eef1fd;padding:2px 6px;border-radius:4px;
}
.desc{color:#4d5670;max-width:260px}
.num{font-weight:700;color:#0f1628;text-align:right}

.pill{
    display:inline-flex;align-items:center;gap:4px;
    padding:2px 9px;border-radius:999px;
    font-size:10px;font-weight:700;letter-spacing:.3px;
}
.pill::before{
    content:'';width:5px;height:5px;border-radius:50%;
}
.pill-pass{background:#e6f7ee;color:#2eab6e}
.pill-pass::before{background:#2eab6e}
.pill-fail{background:#fceaea;color:#d94040}
.pill-fail::before{background:#d94040}
.pill-error{background:#fff4e5;color:#d4820a}
.pill-error::before{background:#d4820a}

/* ── hotspots ── */
.hotspots-card{
    background:#fff;border-radius:12px;padding:22px 20px;
    box-shadow:0 1px 4px rgba(0,0,0,.06);width:280px;flex-shrink:0;
}
.hs-header{
    display:flex;justify-content:space-between;align-items:center;
    margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #f0f2f7;
}
.hs-title-text{font-size:14px;font-weight:700;color:#0f1628}
.hs-warn-dot{
    width:8px;height:8px;border-radius:50%;background:#d4820a;
    box-shadow:0 0 0 3px #fff4e5;
}
.hs-item{
    display:flex;align-items:center;gap:10px;
    padding:10px 0;border-bottom:1px solid #f8f9fc;
}
.hs-item:last-of-type{border-bottom:none}
.hs-count{
    background:#fceaea;color:#d94040;
    font-size:14px;font-weight:800;
    min-width:46px;height:46px;border-radius:9px;
    display:grid;place-items:center;flex-shrink:0;
}
.hs-info{flex:1;overflow:hidden}
.hs-rule{font-size:12px;font-weight:700;color:#0f1628;margin-bottom:1px}
.hs-note{
    font-size:10px;color:#9aa3b8;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.hs-arrow{color:#c8cfe8;font-size:18px;flex-shrink:0}
.hs-foot{
    margin-top:12px;padding-top:10px;border-top:1px solid #f0f2f7;
    text-align:center;
}
.hs-foot a{font-size:11px;color:#4f6bed;cursor:pointer;font-weight:600}

/* ── violations explorer ── */
.exp-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:22px;flex-wrap:wrap;gap:12px}
.exp-title{font-size:26px;font-weight:900;color:#0f1628;letter-spacing:-.5px;margin-bottom:5px}
.exp-desc{font-size:12px;color:#6e7890;max-width:480px;line-height:1.6}

.exp-stats{display:flex;gap:10px}
.stat-box{border-radius:10px;padding:13px 18px;min-width:140px}
.stat-box.red{background:#fceaea}
.stat-box.grey{background:#fff;border:1px solid #e4e7ef}
.stat-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.stat-box.red .stat-lbl{color:#d94040}
.stat-box.grey .stat-lbl{color:#9aa3b8}
.stat-val{font-size:30px;font-weight:900;line-height:1;letter-spacing:-1px}
.stat-box.red .stat-val{color:#d94040}
.stat-box.grey .stat-val{color:#0f1628}

.tabs-row{display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap;align-items:center}
.tab{
    padding:7px 14px;border-radius:7px;
    border:1px solid #e4e7ef;
    background:#fff;color:#6e7890;
    font-size:12px;font-weight:500;cursor:pointer;
    display:flex;align-items:center;gap:6px;
}
.tab:hover:not(.active){background:#f4f6fb;border-color:#c8cfe8}
.tab.active{background:#0f1628;color:#fff;border-color:#0f1628}
.tab-count{
    background:rgba(255,255,255,.15);
    font-size:10px;font-weight:700;
    padding:1px 6px;border-radius:999px;
}
.tab:not(.active) .tab-count{background:#f0f2f7;color:#4d5670}
.export-btn{
    margin-left:auto;
    padding:7px 16px;border-radius:7px;border:1px solid #e4e7ef;
    background:#fff;font-size:12px;font-weight:600;cursor:pointer;
    color:#0f1628;
}
.export-btn:hover{background:#f4f6fb}

.vgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}

.vcard{
    background:#fff;border-radius:12px;padding:18px 20px;
    box-shadow:0 1px 4px rgba(0,0,0,.06);
    border-top:3px solid var(--accent,#4f6bed);
}
.vcard-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.vcard-cat-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.vcard-rule-id{
    font-family:'Consolas','Courier New',monospace;
    font-size:12px;font-weight:700;color:#0f1628;flex:1;
}
.vcard-count{
    background:#fceaea;color:#d94040;
    font-size:10px;font-weight:700;
    padding:2px 8px;border-radius:999px;
    white-space:nowrap;
}
.vcard-desc{font-size:12px;color:#6e7890;margin-bottom:12px;line-height:1.5}
.vcard-headline{font-size:13px;font-weight:600;color:#0f1628;margin-bottom:6px;line-height:1.45}
.vcard-sub{font-size:11px;color:#8892aa;margin-bottom:12px;line-height:1.5}
.chip-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}
.chip-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9aa3b8}
.chip-row{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px}
.chip{
    background:#f4f6fb;color:#4d5670;
    font-size:10px;padding:3px 9px;border-radius:5px;
    font-family:'Consolas','Courier New',monospace;
}
.chip-toggle{
    margin-top:4px;
    background:none;border:none;cursor:pointer;
    font-size:10px;font-weight:700;color:#4f6bed;
    padding:2px 0;letter-spacing:.2px;
}
.chip-toggle:hover{text-decoration:underline}
.copy-btn{
    background:#f4f6fb;border:1px solid #e4e7ef;border-radius:5px;
    color:#4d5670;font-size:9px;font-weight:700;letter-spacing:.5px;
    padding:3px 8px;cursor:pointer;text-transform:uppercase;
}
.copy-btn:hover{background:#eef1fd;color:#2d4be0;border-color:#c8d2f5}
.copy-btn.copied{background:#e6f7ee;color:#2eab6e;border-color:#b6e6cd}
.no-features{font-size:11px;color:#9aa3b8;font-style:italic}
.vcard-error{border-top-color:#d4820a !important}
.vcard-status-pill{
    display:inline-block;font-size:9px;font-weight:800;letter-spacing:.6px;
    padding:2px 7px;border-radius:4px;margin-right:4px;
}
.pill-error-inline{background:#fff4e5;color:#d4820a}
.vcard-dark-sample{
    font-size:11px;color:rgba(255,255,255,.55);
    margin-top:8px;font-family:'Consolas','Courier New',monospace;
}

.vcard-dark{
    background:#0f1628;color:#fff;
    border-top:none;
    grid-column:1/-1;
}
.vcard-wide{grid-column:1/-1}
.vcard-dark-inner{
    display:flex;justify-content:space-between;align-items:center;gap:24px;
}
.vcard-dark-tag{
    font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;
    color:rgba(255,255,255,.4);margin-bottom:6px;
}
.vcard-dark-rule{font-size:16px;font-weight:800;color:#fff;margin-bottom:5px}
.vcard-dark-desc{font-size:12px;color:rgba(255,255,255,.5);max-width:420px;line-height:1.5}
.vcard-dark-stat{text-align:right;flex-shrink:0}
.vcard-dark-count{font-size:48px;font-weight:900;color:#fff;line-height:1;letter-spacing:-2px}
.vcard-dark-unit{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,.35);margin-top:3px}

.vgrid-empty{
    text-align:center;padding:40px 20px;color:#9aa3b8;
    font-size:12px;background:#fff;border-radius:12px;
    border:1px dashed #e4e7ef;margin-top:10px;
}

/* ── print ── */
@media print{
    .sidebar{display:none}
    .main{margin-left:0}
    .topbar{position:static}
    .tabs-row,.export-btn{display:none !important}
    .page{display:block !important}
    #page-explorer{page-break-before:always}
    .vgrid{grid-template-columns:1fr 1fr}
    .bottom-row{flex-wrap:wrap}
    .hotspots-card{width:100%}
    @page{margin:1.2cm;size:A4}
}

@media(max-width:880px){
    .top-row,.bottom-row{flex-direction:column}
    .vgrid{grid-template-columns:1fr}
    .hotspots-card{width:100%}
    .score-card{min-width:unset}
}
"""

# ── JS ────────────────────────────────────────────────────────────────────────

_JS = """
var _activeCat = 'all';
var _query = '';

function showPage(name) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.sb-link').forEach(function(l) { l.classList.remove('active'); });
    document.getElementById('page-' + name).classList.add('active');
    var idx = name === 'dashboard' ? 0 : 1;
    document.querySelectorAll('.sb-link')[idx].classList.add('active');
}

function filter(cat, btn) {
    document.querySelectorAll('.tab').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    _activeCat = cat;
    applyViolationFilter();
}

function applyViolationFilter() {
    var visible = 0;
    document.querySelectorAll('.vcard').forEach(function(c) {
        var catOk = (_activeCat === 'all' || c.dataset.cat === _activeCat);
        var hay = (c.dataset.search || c.textContent).toLowerCase();
        var qOk = (!_query || hay.indexOf(_query) !== -1);
        var show = catOk && qOk;
        c.style.display = show ? '' : 'none';
        if (show) visible++;
    });
    var empty = document.getElementById('vgrid-empty');
    if (empty) empty.style.display = visible ? 'none' : 'block';
}

function onSearch(q) {
    _query = (q || '').toLowerCase();
    document.querySelectorAll('#ruleset-body tr').forEach(function(tr) {
        tr.style.display = tr.textContent.toLowerCase().indexOf(_query) !== -1 ? '' : 'none';
    });
    applyViolationFilter();
}

function toggleChips(btn) {
    var card = btn.closest('.vcard');
    if (!card) return;
    var hidden = card.querySelector('.chip-row-hidden');
    if (!hidden) return;
    var isHidden = hidden.style.display === 'none';
    if (isHidden) {
        hidden.style.display = 'flex';
        btn.textContent = 'Show less';
    } else {
        hidden.style.display = 'none';
        var n = hidden.querySelectorAll('.chip').length;
        btn.textContent = 'Show ' + n + ' more';
    }
}

function copyFeatures(btn) {
    var text = btn.getAttribute('data-copy') || '';
    var done = function() {
        var orig = btn.textContent;
        btn.textContent = 'Copied';
        btn.classList.add('copied');
        setTimeout(function() {
            btn.textContent = orig;
            btn.classList.remove('copied');
        }, 1400);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function(){ fallbackCopy(text); done(); });
    } else {
        fallbackCopy(text);
        done();
    }
}

function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
}
"""


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
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M")
    project    = extract_design_session_name(path)
    rules      = validation_results or []

    n_rules    = len(rules)
    n_pass     = sum(1 for r in rules if r.get('status', '') == 'PASS')
    score      = round(n_pass / n_rules * 100, 1) if n_rules else 0.0
    total_v    = sum(r.get('violation_count', 0) for r in rules)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Validation Report &mdash; {project}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="shell">

  <nav class="sidebar">
    <div class="sb-brand">
      <div class="sb-brand-mark">VE</div>
      <span class="sb-brand-name">Validation Engine</span>
    </div>
    <div class="sb-nav">
      <a class="sb-link active" href="#" onclick="showPage('dashboard');return false;">
        <span class="sb-link-icon">&#9632;</span> Dashboard
      </a>
      <a class="sb-link" href="#" onclick="showPage('explorer');return false;">
        <span class="sb-link-icon">&#9783;</span> Violations Explorer
      </a>
    </div>
  </nav>

  <div class="main">
    <div class="topbar">
      <div class="tb-left">
        <span class="tb-project">{project}</span>
        <span class="tb-run">Generated: {timestamp}</span>
      </div>
      <div class="search">
        <span class="search-icon">&#9906;</span>
        <input type="text" placeholder="Search rules or feature IDs&hellip;" oninput="onSearch(this.value)">
      </div>
    </div>

    <!-- DASHBOARD -->
    <div class="page active" id="page-dashboard">

      <div class="top-row">
        <div class="score-card">
          <div class="score-label">Overall Integrity Score</div>
          <div class="score-body">
            <div class="score-number">{score}<span class="score-pct">%</span></div>
            <div class="score-shield">&#10003;</div>
          </div>
          <div class="score-foot">
            <div class="score-foot-label">Violations Detected</div>
            <div class="score-viol">{total_v}</div>
          </div>
        </div>
        {_category_cards(rules)}
      </div>

      <div class="bottom-row">
        <div class="ruleset-card">
          <div class="card-title">Validation Ruleset</div>
          <div class="card-sub">Compliance monitoring &mdash; {project}</div>
          <table>
            <thead>
              <tr>
                <th>Rule ID</th><th>Description</th><th>Status</th><th style="text-align:right">Violations</th>
              </tr>
            </thead>
            <tbody id="ruleset-body">
              {_ruleset_rows(rules)}
            </tbody>
          </table>
        </div>

        <div class="hotspots-card">
          <div class="hs-header">
            <span class="hs-title-text">Critical Hotspots</span>
            <div class="hs-warn-dot"></div>
          </div>
          {_hotspot_items(rules)}
          <div class="hs-foot">
            <a href="#" onclick="showPage('explorer');return false;">View all failure logs</a>
          </div>
        </div>
      </div>

    </div>

    <!-- VIOLATIONS EXPLORER -->
    <div class="page" id="page-explorer">

      <div class="exp-header">
        <div>
          <div class="exp-title">Violations Explorer</div>
          <div class="exp-desc">
            Failing rules only. Each card lists the affected feature IDs &mdash;
            use the Copy IDs button to paste them into QGIS to locate features.
          </div>
        </div>
        <div class="exp-stats">
          <div class="stat-box red">
            <div class="stat-lbl">Total Violations</div>
            <div class="stat-val">{total_v}</div>
          </div>
          <div class="stat-box grey">
            <div class="stat-lbl">Failing Rules</div>
            <div class="stat-val">{sum(1 for r in rules if r.get('status','') not in ('PASS',''))}</div>
          </div>
        </div>
      </div>

      <div class="tabs-row">
        <button class="tab active" onclick="filter('all',this)">
          All Violations <span class="tab-count">{total_v}</span>
        </button>
        {_filter_tabs(rules)}
        <button class="export-btn" onclick="window.print()">Export PDF</button>
      </div>

      <div class="vgrid" id="vgrid">
        {_violation_cards(rules)}
      </div>

      <div class="vgrid-empty" id="vgrid-empty" style="display:none">No violations match your search.</div>

    </div>
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
