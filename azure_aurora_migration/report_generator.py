"""
report_generator.py
Generates HTML and JSON reports from a MigrationEstimate result.
"""

import json
import math
from datetime import date
from pathlib import Path
from typing import Optional
from models import MigrationEstimate, WorkstreamEstimate, ComplexityBand

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def export_json(estimate: MigrationEstimate, output_path: Optional[Path] = None) -> Path:
    """Serialize the estimate to a JSON file and return the path."""
    if output_path is None:
        safe_name = estimate.project_name.replace(" ", "_").lower()
        output_path = OUTPUT_DIR / f"{safe_name}_estimate.json"

    payload = {
        "metadata": {
            "project_name": estimate.project_name,
            "client_name":  estimate.client_name,
            "prepared_by":  estimate.prepared_by,
            "report_date":  str(date.today()),
            "tool":         "Azure SQL MI → Aurora PostgreSQL Estimator v1.0",
        },
        "overall": {
            "complexity_band":    estimate.overall_complexity.label,
            "complexity_score":   estimate.complexity_score,
            "global_multiplier":  estimate.global_multiplier,
            "subtotal_days":      estimate.subtotal_days,
            "adjusted_days":      estimate.adjusted_days,
            "contingency_pct":    estimate.contingency_pct,
            "contingency_days":   estimate.contingency_days,
            "total_days":         estimate.total_days,
            "total_weeks":        estimate.total_weeks,
            "total_months":       estimate.total_months,
            "optimistic_days":    estimate.optimistic_days,
            "pessimistic_days":   estimate.pessimistic_days,
        },
        "workstreams": [
            {
                "id":                 ws.workstream_id,
                "label":              ws.label,
                "description":        ws.description,
                "complexity_band":    ws.complexity_band.label,
                "base_effort_days":   ws.base_effort_days,
                "risk_buffer_days":   ws.risk_buffer_days,
                "total_effort_days":  ws.total_effort_days,
                "effort_weeks":       ws.effort_weeks,
                "min_days":           ws.min_effort_days,
                "max_days":           ws.max_effort_days,
                "notes":              ws.notes,
            }
            for ws in estimate.workstreams
        ],
        "multiplier_notes":  estimate.multiplier_notes,
        "mi_specific_notes": estimate.mi_specific_notes,
        "risk_flags":        estimate.risk_flags,
        "recommendations":   estimate.recommendations,
    }

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    return output_path


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _badge(band: ComplexityBand) -> str:
    colors = {
        "simple":       ("#d4edda", "#155724"),
        "medium":       ("#fff3cd", "#856404"),
        "complex":      ("#ffe5b4", "#7d4000"),
        "very_complex": ("#f8d7da", "#721c24"),
    }
    bg, fg = colors[band.value]
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:12px;font-size:0.82em;font-weight:600;">'
        f'{band.label}</span>'
    )


def _bar(value: float, max_value: float, color: str, label: str = "") -> str:
    pct = min(100, round((value / max_value) * 100)) if max_value > 0 else 0
    return (
        f'<div style="background:#e9ecef;border-radius:6px;height:18px;margin:4px 0;" title="{label}">'
        f'<div style="width:{pct}%;background:{color};border-radius:6px;height:18px;'
        f'display:flex;align-items:center;padding-left:6px;">'
        f'<span style="font-size:0.72em;color:#fff;white-space:nowrap;overflow:hidden;">'
        f'{value:.1f}d</span></div></div>'
    )


def _risk_icon(flag: str) -> str:
    if flag.startswith("CRITICAL"):
        return "🔴"
    if flag.startswith("HIGH"):
        return "🟠"
    if flag.startswith("MEDIUM"):
        return "🟡"
    return "🔵"


def generate_html(estimate: MigrationEstimate, output_path: Optional[Path] = None) -> Path:
    """Generate a self-contained HTML estimation report."""
    if output_path is None:
        safe_name = estimate.project_name.replace(" ", "_").lower()
        output_path = OUTPUT_DIR / f"{safe_name}_report.html"

    today = date.today().strftime("%B %d, %Y")
    max_ws_days = max((ws.total_effort_days for ws in estimate.workstreams), default=1)
    band_color = estimate.overall_complexity.color

    # Workstream rows
    ws_rows = ""
    for ws in estimate.workstreams:
        notes_html = ""
        if ws.notes:
            notes_html = "<ul style='margin:4px 0 0 0;padding-left:18px;font-size:0.82em;color:#555;'>"
            for n in ws.notes:
                notes_html += f"<li>{n}</li>"
            notes_html += "</ul>"

        ws_rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e9ecef;">
            <strong>{ws.label}</strong>
            <div style="font-size:0.78em;color:#777;margin-top:2px;">{ws.description}</div>
            {notes_html}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e9ecef;text-align:center;">
            {_badge(ws.complexity_band)}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e9ecef;white-space:nowrap;">
            {_bar(ws.total_effort_days, max_ws_days, ws.complexity_band.color, ws.label)}
            <div style="font-size:0.78em;color:#555;margin-top:2px;">
              {ws.min_effort_days}d – {ws.max_effort_days}d &nbsp;|&nbsp; ~{ws.effort_weeks}w
            </div>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e9ecef;text-align:right;
                     font-weight:600;white-space:nowrap;">
            {ws.base_effort_days:.1f}d
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e9ecef;text-align:right;
                     color:#888;white-space:nowrap;">
            +{ws.risk_buffer_days:.1f}d
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e9ecef;text-align:right;
                     font-weight:700;white-space:nowrap;">
            {ws.total_effort_days:.1f}d
          </td>
        </tr>"""

    # Risk flags
    risk_html = ""
    if estimate.risk_flags:
        for flag in estimate.risk_flags:
            icon = _risk_icon(flag)
            risk_html += (
                f'<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0;">'
                f'<span style="font-size:1.2em;flex-shrink:0;">{icon}</span>'
                f'<span style="font-size:0.88em;line-height:1.5;">{flag}</span>'
                f'</div>'
            )
    else:
        risk_html = '<p style="color:#28a745;">No critical risk flags identified.</p>'

    # Recommendations
    rec_html = ""
    for i, rec in enumerate(estimate.recommendations, 1):
        rec_html += (
            f'<div style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #f0f0f0;">'
            f'<span style="font-weight:700;color:#0d6efd;flex-shrink:0;font-size:1.1em;">{i}.</span>'
            f'<span style="font-size:0.88em;line-height:1.5;">{rec}</span>'
            f'</div>'
        )

    # Multiplier notes
    mult_html = ""
    for note in estimate.multiplier_notes:
        color = "#dc3545" if note.startswith("+") else "#28a745"
        mult_html += (
            f'<span style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;'
            f'padding:4px 10px;margin:3px;display:inline-block;font-size:0.82em;color:{color};">'
            f'{note}</span>'
        )
    if not mult_html:
        mult_html = '<span style="color:#555;font-size:0.88em;">No global modifiers applied.</span>'

    # MI-specific notes
    mi_notes_html = ""
    if estimate.mi_specific_notes:
        mi_notes_html = "<ul style='margin:0;padding-left:20px;font-size:0.85em;color:#495057;line-height:1.7;'>"
        for note in estimate.mi_specific_notes:
            mi_notes_html += f"<li>{note}</li>"
        mi_notes_html += "</ul>"
    else:
        mi_notes_html = '<p style="color:#555;font-size:0.85em;">No T-SQL specific features flagged.</p>'

    # Donut chart data (inline SVG approximation via proportional bars)
    chart_segments = []
    total = estimate.subtotal_days or 1
    colors_cycle = [
        "#0d6efd","#6f42c1","#d63384","#dc3545","#fd7e14",
        "#ffc107","#198754","#20c997","#0dcaf0","#6c757d","#495057",
    ]
    for i, ws in enumerate(estimate.workstreams):
        pct = round((ws.total_effort_days / total) * 100, 1)
        chart_segments.append((ws.label, ws.total_effort_days, pct, colors_cycle[i % len(colors_cycle)]))

    legend_html = ""
    chart_bars = ""
    for label, days, pct, color in chart_segments:
        legend_html += (
            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;font-size:0.80em;">'
            f'<span style="width:12px;height:12px;background:{color};border-radius:2px;flex-shrink:0;"></span>'
            f'<span>{label} ({pct}%)</span></div>'
        )
        chart_bars += (
            f'<div title="{label}: {days:.1f}d ({pct}%)" style="width:{pct}%;background:{color};'
            f'height:36px;display:inline-block;"></div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Migration Estimate – {estimate.project_name}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           margin: 0; background: #f0f4f8; color: #212529; }}
    .page {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
    .card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.08);
             padding: 28px 32px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.6em; color: #1a1a2e; }}
    h2 {{ font-size: 1.1em; margin: 0 0 18px; color: #343a40; border-bottom: 2px solid #e9ecef;
          padding-bottom: 8px; }}
    .meta {{ font-size: 0.85em; color: #6c757d; margin-bottom: 22px; }}
    .hero {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; }}
    .kpi {{ background: #f8f9fa; border-radius: 10px; padding: 18px 20px; text-align: center; }}
    .kpi .val {{ font-size: 2em; font-weight: 700; color: {band_color}; }}
    .kpi .lbl {{ font-size: 0.78em; color: #6c757d; margin-top:4px; }}
    .range-pill {{ display:inline-block;background:#e7f3ff;color:#0d6efd;border-radius:20px;
                  padding:4px 14px;font-size:0.85em;font-weight:600;margin-top:6px;}}
    table {{ width:100%;border-collapse:collapse; }}
    th {{ background:#f8f9fa;padding:10px 12px;text-align:left;font-size:0.80em;
          color:#6c757d;border-bottom:2px solid #dee2e6;white-space:nowrap; }}
    tr:last-child td {{ border-bottom: none; }}
    .phase-badge {{ display:inline-block;background:#e8f4fd;color:#0c63a1;border-radius:6px;
                   padding:2px 8px;font-size:0.75em;font-weight:600;margin:2px; }}
    @media print {{
      body {{ background: #fff; }}
      .page {{ padding: 0; }}
      .card {{ box-shadow: none; border: 1px solid #dee2e6; page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
      <div>
        <h1>Migration Effort Estimation</h1>
        <div style="font-size:1.05em;color:#495057;margin:4px 0;">
          Azure SQL Managed Instance &nbsp;→&nbsp; Amazon Aurora PostgreSQL
        </div>
        <div class="meta">
          Project: <strong>{estimate.project_name}</strong> &nbsp;|&nbsp;
          Client: <strong>{estimate.client_name}</strong> &nbsp;|&nbsp;
          Prepared by: <strong>{estimate.prepared_by}</strong> &nbsp;|&nbsp;
          Date: <strong>{today}</strong>
        </div>
      </div>
      <div style="text-align:right;">
        {_badge(estimate.overall_complexity)}
        <div style="font-size:0.78em;color:#6c757d;margin-top:4px;">
          Complexity Score: {estimate.complexity_score}/4.0
        </div>
      </div>
    </div>

    <!-- KPIs -->
    <div class="hero">
      <div class="kpi">
        <div class="val">{estimate.total_days:.0f}</div>
        <div class="lbl">Total Person-Days</div>
        <div class="range-pill">{estimate.optimistic_days:.0f}d – {estimate.pessimistic_days:.0f}d</div>
      </div>
      <div class="kpi">
        <div class="val">{estimate.total_weeks:.1f}</div>
        <div class="lbl">Total Weeks</div>
      </div>
      <div class="kpi">
        <div class="val">{estimate.total_months:.1f}</div>
        <div class="lbl">Approx. Months</div>
      </div>
      <div class="kpi">
        <div class="val">{estimate.contingency_pct:.0f}%</div>
        <div class="lbl">Contingency Buffer</div>
        <div style="font-size:0.78em;color:#6c757d;margin-top:2px;">+{estimate.contingency_days:.0f}d</div>
      </div>
      <div class="kpi">
        <div class="val">{estimate.global_multiplier:.2f}x</div>
        <div class="lbl">Global Multiplier</div>
      </div>
    </div>
  </div>

  <!-- Effort Distribution Chart -->
  <div class="card">
    <h2>Effort Distribution by Workstream</h2>
    <div style="width:100%;border-radius:8px;overflow:hidden;margin-bottom:16px;height:36px;display:flex;">
      {chart_bars}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:4px;">
      {legend_html}
    </div>
  </div>

  <!-- Workstream Table -->
  <div class="card">
    <h2>Workstream Effort Breakdown</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th style="width:38%;">Workstream</th>
            <th>Complexity</th>
            <th style="min-width:180px;">Effort</th>
            <th style="text-align:right;">Base (d)</th>
            <th style="text-align:right;">Buffer (d)</th>
            <th style="text-align:right;">Total (d)</th>
          </tr>
        </thead>
        <tbody>
          {ws_rows}
          <tr style="background:#f8f9fa;">
            <td colspan="3" style="padding:12px;font-weight:700;font-size:0.95em;">
              Sub-total (before global adjustments)
            </td>
            <td colspan="3" style="padding:12px;text-align:right;font-weight:700;font-size:1.1em;">
              {estimate.subtotal_days:.1f} days
            </td>
          </tr>
          <tr>
            <td colspan="3" style="padding:8px 12px;color:#555;font-size:0.88em;">
              Global Multiplier ({estimate.global_multiplier:.2f}x)
            </td>
            <td colspan="3" style="padding:8px 12px;text-align:right;font-size:0.88em;">
              {estimate.adjusted_days:.1f} days
            </td>
          </tr>
          <tr>
            <td colspan="3" style="padding:8px 12px;color:#555;font-size:0.88em;">
              Contingency ({estimate.contingency_pct:.0f}%)
            </td>
            <td colspan="3" style="padding:8px 12px;text-align:right;font-size:0.88em;">
              +{estimate.contingency_days:.1f} days
            </td>
          </tr>
          <tr style="background:#1a1a2e;color:#fff;">
            <td colspan="3" style="padding:14px 12px;font-weight:700;font-size:1.05em;border-radius:0 0 0 8px;">
              TOTAL ESTIMATED EFFORT
            </td>
            <td colspan="3" style="padding:14px 12px;text-align:right;font-weight:700;
                                   font-size:1.3em;border-radius:0 0 8px 0;">
              {estimate.total_days:.1f} days
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div style="margin-top:16px;padding:14px;background:#f8f9fa;border-radius:8px;font-size:0.82em;color:#555;">
      <strong>Range:</strong>
      Optimistic <strong>{estimate.optimistic_days:.0f}d</strong> /
      Most Likely <strong>{estimate.total_days:.0f}d</strong> /
      Pessimistic <strong>{estimate.pessimistic_days:.0f}d</strong>
      &nbsp;&nbsp;|&nbsp;&nbsp;
      <strong>~{estimate.total_weeks:.1f} weeks</strong> elapsed calendar time with a properly staffed team.
    </div>
  </div>

  <!-- Global Modifiers -->
  <div class="card">
    <h2>Global Effort Modifiers</h2>
    {mult_html}
  </div>

  <!-- Risk Flags -->
  <div class="card">
    <h2>Risk Flags – Azure SQL MI Specific</h2>
    {risk_html}
  </div>

  <!-- T-SQL / Data Type Notes -->
  <div class="card">
    <h2>T-SQL Features & Data Types Detected</h2>
    {mi_notes_html}
  </div>

  <!-- Recommendations -->
  <div class="card">
    <h2>Recommendations</h2>
    {rec_html}
  </div>

  <!-- Migration Phases -->
  <div class="card">
    <h2>Suggested Migration Phases</h2>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;">
      <div style="border:1px solid #dee2e6;border-radius:10px;padding:16px;">
        <div style="font-weight:700;color:#0d6efd;margin-bottom:8px;">Phase 1 – Assess &amp; Plan</div>
        <div style="font-size:0.85em;line-height:1.6;color:#495057;">
          Run AWS SCT assessment · Schema inventory · Risk register · Team onboarding ·
          Aurora cluster provisioning (dev) · DMS instance setup
        </div>
      </div>
      <div style="border:1px solid #dee2e6;border-radius:10px;padding:16px;">
        <div style="font-weight:700;color:#6f42c1;margin-bottom:8px;">Phase 2 – Convert (Non-Prod)</div>
        <div style="font-size:0.85em;line-height:1.6;color:#495057;">
          DDL conversion · SP/function rewrite · View migration ·
          Data type remediation · Application driver updates · Unit tests
        </div>
      </div>
      <div style="border:1px solid #dee2e6;border-radius:10px;padding:16px;">
        <div style="font-weight:700;color:#198754;margin-bottom:8px;">Phase 3 – Data Migration &amp; Validation</div>
        <div style="font-size:0.85em;line-height:1.6;color:#495057;">
          DMS full-load · CDC enablement · Row-count &amp; checksum validation ·
          Performance baseline comparison · Integration testing
        </div>
      </div>
      <div style="border:1px solid #dee2e6;border-radius:10px;padding:16px;">
        <div style="font-weight:700;color:#fd7e14;margin-bottom:8px;">Phase 4 – UAT &amp; Performance</div>
        <div style="font-size:0.85em;line-height:1.6;color:#495057;">
          User acceptance testing · Load &amp; stress tests · Query tuning ·
          Autovacuum / parameter group tuning · Cutover rehearsal #1
        </div>
      </div>
      <div style="border:1px solid #dee2e6;border-radius:10px;padding:16px;">
        <div style="font-weight:700;color:#dc3545;margin-bottom:8px;">Phase 5 – Cutover &amp; Go-Live</div>
        <div style="font-size:0.85em;line-height:1.6;color:#495057;">
          Final sync (CDC) · Application switchover · DNS/connection string update ·
          Smoke tests · CloudWatch alarms · Hypercare support
        </div>
      </div>
      <div style="border:1px solid #dee2e6;border-radius:10px;padding:16px;">
        <div style="font-weight:700;color:#20c997;margin-bottom:8px;">Phase 6 – Optimise &amp; Decommission</div>
        <div style="font-size:0.85em;line-height:1.6;color:#495057;">
          Performance Insights review · Index tuning · Aurora autoscaling config ·
          Azure SQL MI decommission · Cost optimisation
        </div>
      </div>
    </div>
  </div>

  <!-- Disclaimer -->
  <div style="font-size:0.75em;color:#adb5bd;text-align:center;padding:12px 0 24px;">
    This estimate is based on the project profile inputs and AWS migration best practices.
    Actual effort may vary based on code quality, team availability, and requirements changes.
    Run AWS SCT for a detailed automated assessment before finalising commitments.
  </div>

</div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    return output_path
