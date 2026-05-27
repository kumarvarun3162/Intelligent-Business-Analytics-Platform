# backend/core/pdf_generator.py

from pathlib import Path
from datetime import datetime
from typing import Optional


def _quality_color(score: float) -> str:
    if score >= 90: return "#0F6E56"
    if score >= 75: return "#1D9E75"
    if score >= 60: return "#BA7517"
    if score >= 45: return "#D85A30"
    return "#A32D2D"


def _grade_label(grade: str) -> str:
    return {
        "A": "Excellent", "B": "Good",
        "C": "Fair",       "D": "Poor", "F": "Failing"
    }.get(grade, grade)


def build_html_report(report_config, insights_report=None) -> str:
    """
    Build a self-contained HTML string that WeasyPrint renders to PDF.
    Uses print-optimised CSS: A4 page, 1cm margins, no external resources.
    """
    passport  = report_config.data_passport
    narrative = report_config.narrative
    now       = datetime.fromisoformat(report_config.generated_at)
    date_str  = now.strftime("%B %d, %Y at %H:%M UTC")

    # Quality score block
    qs    = passport.quality_score or 0
    qg    = passport.quality_grade or "?"
    qc    = _quality_color(qs)
    qlabel = _grade_label(qg)

    # Pipeline stages
    stages_html = ""
    for stage in passport.pipeline_stages:
        stages_html += f"""
        <div class="stage-row">
            <span class="stage-badge">Phase {stage['phase']}</span>
            <div>
                <strong>{stage['name']}</strong>
                <p class="stage-summary">{stage['summary']}</p>
            </div>
        </div>"""

    # Narrative sections
    narrative_html = ""
    for sec in narrative:
        narrative_html += f"""
        <div class="section">
            <h2>{sec.emoji} {sec.title}</h2>
            <p>{sec.content}</p>
        </div>"""

    # Stats table
    stats_rows = ""
    if insights_report:
        for s in insights_report.descriptive[:10]:
            normal_badge = (
                '<span class="badge-green">normal</span>'
                if s.is_normal else
                '<span class="badge-amber">non-normal</span>'
            )
            stats_rows += f"""
            <tr>
                <td><code>{s.column}</code></td>
                <td>{s.mean:.3f}</td>
                <td>{s.median:.3f}</td>
                <td>{s.std:.3f}</td>
                <td>{s.skewness:.3f}</td>
                <td>{normal_badge}</td>
            </tr>"""

    # Top correlations
    corr_rows = ""
    if insights_report and insights_report.correlations:
        for c in insights_report.correlations[:8]:
            corr_rows += f"""
            <tr>
                <td><code>{c.col_a}</code></td>
                <td><code>{c.col_b}</code></td>
                <td>{c.pearson:.4f}</td>
                <td>{c.spearman:.4f}</td>
                <td><span class="badge-{
                    'red'   if c.strength == 'strong'   else
                    'amber' if c.strength == 'moderate' else
                    'gray'
                }">{c.strength}</span></td>
            </tr>"""

    # Key insights
    insights_list = ""
    if insights_report and insights_report.key_insights:
        for ins in insights_report.key_insights:
            insights_list += f"<li>{ins}</li>"

    warnings_list = ""
    if insights_report and insights_report.warnings:
        for w in insights_report.warnings:
            warnings_list += f'<li class="warning-item">{w}</li>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  @page {{
    size: A4;
    margin: 1.8cm 1.5cm 1.8cm 1.5cm;
    @bottom-right {{
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9pt;
      color: #9ca3af;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Helvetica Neue", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1f2937;
    background: #fff;
  }}
  .cover {{
    padding: 60px 0 40px;
    border-bottom: 3px solid #1D9E75;
    margin-bottom: 32px;
  }}
  .cover-brand {{
    font-size: 11pt;
    color: #6b7280;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 10px;
  }}
  .cover-title {{
    font-size: 26pt;
    font-weight: 700;
    color: #111827;
    line-height: 1.2;
    margin-bottom: 8px;
  }}
  .cover-subtitle {{
    font-size: 12pt;
    color: #6b7280;
    margin-bottom: 24px;
  }}
  .cover-meta {{
    font-size: 9pt;
    color: #9ca3af;
  }}
  .quality-block {{
    display: inline-block;
    padding: 12px 20px;
    border: 2px solid {qc};
    border-radius: 8px;
    margin-top: 16px;
  }}
  .quality-score {{
    font-size: 32pt;
    font-weight: 700;
    color: {qc};
    line-height: 1;
  }}
  .quality-label {{
    font-size: 10pt;
    color: {qc};
    margin-top: 2px;
  }}
  h1 {{ font-size: 16pt; color: #111827; margin: 28px 0 12px; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }}
  h2 {{ font-size: 13pt; color: #1D9E75; margin: 22px 0 10px; font-weight: 600; }}
  p {{ margin-bottom: 10px; color: #374151; }}
  .section {{ margin-bottom: 24px; break-inside: avoid; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 9.5pt;
  }}
  th {{
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    padding: 6px 10px;
    text-align: left;
    font-weight: 600;
    color: #374151;
  }}
  td {{
    border: 1px solid #e5e7eb;
    padding: 5px 10px;
    color: #374151;
  }}
  tr:nth-child(even) td {{ background: #f9fafb; }}
  code {{
    font-family: "Courier New", monospace;
    font-size: 8.5pt;
    background: #f3f4f6;
    padding: 1px 4px;
    border-radius: 3px;
    color: #4b5563;
  }}
  .badge-green  {{ color: #0F6E56; background: #E1F5EE; padding: 1px 6px; border-radius: 9px; font-size: 8pt; }}
  .badge-amber  {{ color: #854F0B; background: #FAEEDA; padding: 1px 6px; border-radius: 9px; font-size: 8pt; }}
  .badge-red    {{ color: #A32D2D; background: #FCEBEB; padding: 1px 6px; border-radius: 9px; font-size: 8pt; }}
  .badge-gray   {{ color: #5F5E5A; background: #F1EFE8; padding: 1px 6px; border-radius: 9px; font-size: 8pt; }}
  .stage-row    {{ display: flex; align-items: flex-start; gap: 12px; margin-bottom: 10px; }}
  .stage-badge  {{ min-width: 60px; padding: 3px 8px; background: #E1F5EE; color: #0F6E56; border-radius: 4px; font-size: 8pt; font-weight: 600; text-align: center; }}
  .stage-summary {{ font-size: 9pt; color: #6b7280; margin-top: 2px; }}
  .insights-list {{ padding-left: 16px; }}
  .insights-list li {{ margin-bottom: 6px; color: #374151; }}
  .warning-item {{ color: #92400e; }}
  .footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #e5e7eb; font-size: 8.5pt; color: #9ca3af; }}
  .page-break {{ page-break-before: always; }}
</style>
</head>
<body>

<div class="cover">
  <div class="cover-brand">IBAP — Intelligent Business Analytics Platform</div>
  <div class="cover-title">{report_config.dataset_name}</div>
  <div class="cover-subtitle">Automated Data Analysis Report</div>
  <div class="cover-meta">Generated on {date_str} · Model: {report_config.model_used}</div>
  <div class="quality-block">
    <div class="quality-score">{qs}/100</div>
    <div class="quality-label">Data quality — Grade {qg} ({qlabel})</div>
  </div>
</div>

<!-- Narrative sections -->
{narrative_html}

<!-- Pipeline audit -->
<div class="page-break"></div>
<h1>Pipeline audit trail</h1>
{stages_html}

<!-- Statistical tables -->
{"<h1>Descriptive statistics</h1><table><thead><tr><th>Column</th><th>Mean</th><th>Median</th><th>Std</th><th>Skewness</th><th>Distribution</th></tr></thead><tbody>" + stats_rows + "</tbody></table>" if stats_rows else ""}

{"<h1>Correlation analysis</h1><table><thead><tr><th>Column A</th><th>Column B</th><th>Pearson r</th><th>Spearman r</th><th>Strength</th></tr></thead><tbody>" + corr_rows + "</tbody></table>" if corr_rows else ""}

{"<h1>Key insights</h1><ul class='insights-list'>" + insights_list + "</ul>" if insights_list else ""}

{"<h1>Warnings</h1><ul class='insights-list'>" + warnings_list + "</ul>" if warnings_list else ""}

<div class="footer">
  IBAP Automated Analysis · Session {report_config.session_id[:16]}
  · {report_config.dataset_name}
  · {date_str}
</div>

</body>
</html>"""

    return html


def generate_pdf(html: str, output_path: Path) -> Path:
    """Render HTML to PDF using WeasyPrint."""
    from weasyprint import HTML as WeasyHTML
    WeasyHTML(string=html).write_pdf(str(output_path))
    return output_path