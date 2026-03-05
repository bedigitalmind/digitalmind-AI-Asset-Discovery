"""
Report Service — Sprint 4
Generates professional AI Discovery reports in PDF and DOCX formats.

Report sections:
  1. Cover page
  2. Executive Summary
  3. AI Asset Inventory (by category)
  4. Shadow AI Findings
  5. High & Critical Risk Assets
  6. Category Breakdown
  7. Analyst Review Status
  8. Recommendations
  9. Methodology & Disclaimer
"""
import io
import json
import logging
from datetime import datetime, date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core.tenant import get_schema_name
from ..services.file_service import get_s3_client, get_bucket_name, ensure_bucket

logger = logging.getLogger(__name__)

# ─── Brand colours ────────────────────────────────────────────────────────────
BRAND_DARK   = (15,  23,  42)   # slate-900
BRAND_MID    = (30,  41,  59)   # slate-800
BRAND_BLUE   = (99,  102, 241)  # brand-500 indigo
BRAND_WHITE  = (255, 255, 255)
TEXT_PRIMARY = (15,  23,  42)
TEXT_MUTED   = (100, 116, 139)  # slate-500

RISK_COLORS = {
    "low":      (16,  185, 129),  # emerald-500
    "medium":   (245, 158, 11),   # amber-500
    "high":     (249, 115, 22),   # orange-500
    "critical": (239, 68,  68),   # red-500
}


# ─── Data collection ──────────────────────────────────────────────────────────

async def _collect_report_data(
    db: AsyncSession,
    workspace_slug: str,
    workspace_name: str,
) -> dict[str, Any]:
    """Query all relevant data from the workspace schema for report generation."""
    schema = get_schema_name(workspace_slug)

    async def q(sql: str, params: dict | None = None) -> list[dict]:
        result = await db.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings().all()]

    async def q1(sql: str, params: dict | None = None) -> dict | None:
        result = await db.execute(text(sql), params or {})
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    # Global stats
    stats = await q1(f"""
        SELECT
            COUNT(*) AS total_assets,
            COUNT(*) FILTER (WHERE is_shadow_ai) AS shadow_ai,
            COUNT(*) FILTER (WHERE risk_level = 'critical') AS critical,
            COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk,
            COUNT(*) FILTER (WHERE risk_level = 'medium') AS medium_risk,
            COUNT(*) FILTER (WHERE risk_level = 'low') AS low_risk,
            COUNT(*) FILTER (WHERE analyst_status = 'confirmed') AS confirmed,
            COUNT(*) FILTER (WHERE analyst_status = 'pending_review') AS pending_review,
            COUNT(DISTINCT category) AS total_categories,
            MAX(last_seen_at) AS last_activity
        FROM "{schema}".discovered_assets
    """) or {}

    # By category
    categories = await q(f"""
        SELECT category, COUNT(*) AS count,
               COUNT(*) FILTER (WHERE is_shadow_ai) AS shadow_count,
               COUNT(*) FILTER (WHERE risk_level IN ('high','critical')) AS high_risk_count,
               ROUND(AVG(risk_score)::numeric, 1) AS avg_risk_score
        FROM "{schema}".discovered_assets
        GROUP BY category ORDER BY count DESC
    """)

    # Shadow AI assets
    shadow_assets = await q(f"""
        SELECT id, name, vendor, category, subcategory, risk_level, risk_score,
               description, analyst_status, analyst_notes, first_seen_at, last_seen_at
        FROM "{schema}".discovered_assets
        WHERE is_shadow_ai = TRUE
        ORDER BY risk_score DESC, name
    """)

    # High + critical risk assets
    high_risk_assets = await q(f"""
        SELECT id, name, vendor, category, subcategory, risk_level, risk_score,
               description, is_shadow_ai, analyst_status, analyst_notes,
               first_seen_at, last_seen_at
        FROM "{schema}".discovered_assets
        WHERE risk_level IN ('high', 'critical')
        ORDER BY risk_score DESC, name
    """)

    # All assets (for inventory)
    all_assets = await q(f"""
        SELECT id, name, vendor, category, subcategory, risk_level, risk_score,
               is_shadow_ai, analyst_status, description, first_seen_at
        FROM "{schema}".discovered_assets
        ORDER BY category, risk_score DESC, name
    """)

    # Connectors
    connectors = await q(f"""
        SELECT name, connector_type, platform, status,
               last_scan_at, last_scan_status
        FROM "{schema}".connectors
        ORDER BY created_at
    """)

    # Files ingested
    files_count = await q1(f"""
        SELECT COUNT(*) AS count,
               COUNT(*) FILTER (WHERE status = 'processed') AS processed
        FROM "{schema}".ingestion_files
    """) or {"count": 0, "processed": 0}

    return {
        "workspace_name": workspace_name,
        "workspace_slug": workspace_slug,
        "generated_at":   datetime.utcnow(),
        "stats":          stats,
        "categories":     categories,
        "shadow_assets":  shadow_assets,
        "high_risk_assets": high_risk_assets,
        "all_assets":     all_assets,
        "connectors":     connectors,
        "files_count":    files_count,
    }


# ─── PDF Generation ───────────────────────────────────────────────────────────

def _generate_pdf(data: dict[str, Any]) -> bytes:
    """Generate the full discovery report as a PDF using ReportLab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, KeepTogether,
    )
    from reportlab.platypus import Flowable

    PAGE_W, PAGE_H = A4
    MARGIN = 2.2 * cm

    buffer = io.BytesIO()

    def _rgb(t: tuple) -> colors.Color:
        return colors.Color(t[0]/255, t[1]/255, t[2]/255)

    brand   = _rgb(BRAND_BLUE)
    dark    = _rgb(BRAND_DARK)
    muted   = _rgb(TEXT_MUTED)
    white   = colors.white
    red     = _rgb(RISK_COLORS["critical"])
    orange  = _rgb(RISK_COLORS["high"])
    amber   = _rgb(RISK_COLORS["medium"])
    green   = _rgb(RISK_COLORS["low"])
    slate50 = colors.Color(0.97, 0.97, 0.98)

    # ── Styles ────────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    def S(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    h1  = S("H1",  fontSize=24, textColor=dark,  leading=30, spaceAfter=6,  fontName="Helvetica-Bold")
    h2  = S("H2",  fontSize=16, textColor=dark,  leading=20, spaceAfter=4,  fontName="Helvetica-Bold", spaceBefore=14)
    h3  = S("H3",  fontSize=11, textColor=dark,  leading=14, spaceAfter=3,  fontName="Helvetica-Bold", spaceBefore=8)
    body= S("Body",fontSize=9,  textColor=dark,  leading=13, spaceAfter=4,  fontName="Helvetica")
    sm  = S("Sm",  fontSize=8,  textColor=muted, leading=11, spaceAfter=2,  fontName="Helvetica")
    cap = S("Cap", fontSize=7,  textColor=muted, leading=10, spaceAfter=2,  fontName="Helvetica",  textTransform="uppercase")
    mono= S("Mono",fontSize=8,  textColor=dark,  leading=11, spaceAfter=2,  fontName="Courier")

    def risk_color(level: str) -> colors.Color:
        return _rgb(RISK_COLORS.get(level, RISK_COLORS["medium"]))

    def status_label(s: str) -> str:
        return {"pending_review": "Revisão pendente", "confirmed": "Confirmado",
                "false_positive": "Falso positivo", "accepted_risk": "Risco aceito"}.get(s, s)

    def fmt_date(val: Any) -> str:
        if not val:
            return "—"
        if isinstance(val, (datetime, date)):
            return val.strftime("%d/%m/%Y")
        return str(val)[:10]

    # ── Page template (header/footer) ─────────────────────────────────────────
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        # Header bar
        canvas.setFillColor(dark)
        canvas.rect(0, h - 1.2*cm, w, 1.2*cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(MARGIN, h - 0.75*cm, "Digital Mind · AI Discovery Report")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - MARGIN, h - 0.75*cm, data["workspace_name"])
        # Footer
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN, 0.7*cm, f"Confidencial — {data['workspace_name']}")
        canvas.drawRightString(w - MARGIN, 0.7*cm, f"Página {doc.page}")
        canvas.restoreState()

    def on_first_page(canvas, doc):
        pass  # cover page has its own design

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.5*cm, bottomMargin=1.5*cm,
        title=f"AI Discovery Report — {data['workspace_name']}",
        author="Digital Mind",
    )

    story = []
    stats = data["stats"]
    gen_date = data["generated_at"].strftime("%d de %B de %Y")

    # ═════════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ═════════════════════════════════════════════════════════════════════════
    class CoverPage(Flowable):
        def draw(self):
            w, h = A4
            c = self.canv
            # Dark background
            c.setFillColor(dark)
            c.rect(0, 0, w, h, fill=1, stroke=0)
            # Brand accent bar
            c.setFillColor(brand)
            c.rect(0, h * 0.62, w, 4, fill=1, stroke=0)
            # Logo placeholder
            c.setFillColor(brand)
            c.roundRect(MARGIN, h - 3.5*cm, 3.5*cm, 1.4*cm, 6, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(MARGIN + 0.6*cm, h - 2.7*cm, "Digital Mind")
            # Title area
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 32)
            c.drawString(MARGIN, h * 0.68, "AI Discovery")
            c.setFont("Helvetica-Bold", 32)
            c.drawString(MARGIN, h * 0.68 - 2.2*cm, "Report")
            c.setFillColor(_rgb(BRAND_BLUE))
            c.setFont("Helvetica", 14)
            c.drawString(MARGIN, h * 0.68 - 3.8*cm, data["workspace_name"])
            # Stats row
            y_stats = h * 0.38
            boxes = [
                (str(stats.get("total_assets", 0)),  "Assets Descobertos"),
                (str(stats.get("shadow_ai", 0)),     "Shadow AI"),
                (str(stats.get("critical", 0)),      "Críticos"),
                (str(stats.get("high_risk", 0)),     "Alto Risco"),
            ]
            box_w = (w - 2 * MARGIN) / len(boxes)
            for i, (val, lbl) in enumerate(boxes):
                bx = MARGIN + i * box_w
                c.setFillColor(colors.Color(1, 1, 1, 0.08))
                c.roundRect(bx + 3, y_stats - 1.2*cm, box_w - 6, 2*cm, 6, fill=1, stroke=0)
                c.setFillColor(white)
                c.setFont("Helvetica-Bold", 22)
                c.drawCentredString(bx + box_w/2, y_stats + 0.1*cm, val)
                c.setFillColor(_rgb(TEXT_MUTED))
                c.setFont("Helvetica", 8)
                c.drawCentredString(bx + box_w/2, y_stats - 0.7*cm, lbl)
            # Footer info
            c.setFillColor(_rgb(TEXT_MUTED))
            c.setFont("Helvetica", 9)
            c.drawString(MARGIN, 2.5*cm, f"Data: {gen_date}")
            c.drawString(MARGIN, 1.8*cm, "Classificação: Confidencial")
            c.setFont("Helvetica", 8)
            c.drawString(MARGIN, 1.1*cm, "Este documento contém informações sensíveis sobre a infraestrutura de IA da organização.")

        def wrap(self, avail_w, avail_h):
            return PAGE_W, PAGE_H

    story.append(CoverPage())
    story.append(PageBreak())

    # From here, use header/footer template
    doc.onFirstPage  = on_page
    doc.onLaterPages = on_page

    # ═════════════════════════════════════════════════════════════════════════
    # 1. EXECUTIVE SUMMARY
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("1. Sumário Executivo", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=_rgb((226, 232, 240)), spaceAfter=10))

    # KPI boxes 2x2
    kpi_data = [
        [
            Paragraph(f"<b><font size=20>{stats.get('total_assets', 0)}</font></b><br/><font size=8 color='#64748b'>Total de Assets</font>", body),
            Paragraph(f"<b><font size=20 color='#f59e0b'>{stats.get('shadow_ai', 0)}</font></b><br/><font size=8 color='#64748b'>Shadow AI</font>", body),
            Paragraph(f"<b><font size=20 color='#ef4444'>{stats.get('critical', 0)}</font></b><br/><font size=8 color='#64748b'>Críticos</font>", body),
            Paragraph(f"<b><font size=20 color='#f97316'>{stats.get('high_risk', 0)}</font></b><br/><font size=8 color='#64748b'>Alto Risco</font>", body),
        ],
        [
            Paragraph(f"<b><font size=20>{stats.get('medium_risk', 0)}</font></b><br/><font size=8 color='#64748b'>Risco Médio</font>", body),
            Paragraph(f"<b><font size=20>{stats.get('low_risk', 0)}</font></b><br/><font size=8 color='#64748b'>Baixo Risco</font>", body),
            Paragraph(f"<b><font size=20>{stats.get('total_categories', 0)}</font></b><br/><font size=8 color='#64748b'>Categorias</font>", body),
            Paragraph(f"<b><font size=20>{stats.get('pending_review', 0)}</font></b><br/><font size=8 color='#64748b'>Pendentes</font>", body),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[(PAGE_W - 2*MARGIN)/4]*4, rowHeights=[1.6*cm, 1.6*cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), slate50),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [slate50, white]),
        ("BOX",         (0,0), (-1,-1), 0.5, _rgb((226,232,240))),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, _rgb((226,232,240))),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING",  (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.4*cm))

    # Findings summary paragraph
    total = stats.get("total_assets", 0)
    shadow = stats.get("shadow_ai", 0)
    critical = stats.get("critical", 0)
    high = stats.get("high_risk", 0)
    last_act = fmt_date(stats.get("last_activity"))
    shadow_pct = round(shadow / total * 100) if total else 0
    risk_pct   = round((critical + high) / total * 100) if total else 0

    summary_text = (
        f"A análise da infraestrutura de IA de <b>{data['workspace_name']}</b> identificou "
        f"<b>{total} assets de IA</b> distribuídos em {stats.get('total_categories', 0)} categorias. "
        f"Destes, <b>{shadow} ({shadow_pct}%) constituem Shadow AI</b> — ferramentas utilizadas sem aprovação formal — "
        f"representando risco significativo de segurança e compliance. "
        f"<b>{critical + high} assets ({risk_pct}%) apresentam nível de risco alto ou crítico</b>, "
        f"exigindo ação imediata das equipes de segurança e governança. "
        f"Última atividade detectada: {last_act}."
    )
    story.append(Paragraph(summary_text, body))
    story.append(Spacer(1, 0.3*cm))

    # Data sources box
    connectors = data.get("connectors", [])
    files = data.get("files_count", {})
    sources_text = (
        f"<b>Fontes de dados analisadas:</b> {len(connectors)} conector(es) configurado(s) · "
        f"{files.get('processed', 0)} arquivo(s) processado(s)."
    )
    story.append(Table([[Paragraph(sources_text, sm)]], colWidths=[PAGE_W - 2*MARGIN],
        style=[("BACKGROUND",(0,0),(-1,-1),slate50),
               ("BOX",(0,0),(-1,-1),0.5,_rgb((226,232,240))),
               ("TOPPADDING",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),8),
               ("LEFTPADDING",(0,0),(-1,-1),10)]))
    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 2. INVENTÁRIO DE ASSETS POR CATEGORIA
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("2. Inventário de Assets de IA", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=_rgb((226,232,240)), spaceAfter=10))

    categories = data.get("categories", [])
    if categories:
        cat_header = [
            Paragraph("<b>Categoria</b>", cap),
            Paragraph("<b>Total</b>", cap),
            Paragraph("<b>Shadow AI</b>", cap),
            Paragraph("<b>Alto Risco</b>", cap),
            Paragraph("<b>Score Médio</b>", cap),
        ]
        cat_rows = [cat_header]
        for cat in categories:
            cat_rows.append([
                Paragraph(cat["category"], body),
                Paragraph(str(cat["count"]), body),
                Paragraph(str(cat["shadow_count"]) if cat["shadow_count"] else "—", body),
                Paragraph(str(cat["high_risk_count"]) if cat["high_risk_count"] else "—", body),
                Paragraph(str(cat["avg_risk_score"]), body),
            ])
        col_w = (PAGE_W - 2*MARGIN)
        cat_table = Table(cat_rows, colWidths=[col_w*0.44, col_w*0.12, col_w*0.16, col_w*0.16, col_w*0.12])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  _rgb(BRAND_DARK)),
            ("TEXTCOLOR",     (0,0), (-1,0),  white),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [white, slate50]),
            ("INNERGRID",     (0,0), (-1,-1), 0.3, _rgb((226,232,240))),
            ("BOX",           (0,0), (-1,-1), 0.5, _rgb((203,213,225))),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 0.5*cm))

    # Asset inventory table (grouped by category)
    all_assets = data.get("all_assets", [])
    if all_assets:
        story.append(Paragraph("Inventário Completo", h3))
        inv_header = [
            Paragraph("<b>Asset</b>", cap), Paragraph("<b>Vendor</b>", cap),
            Paragraph("<b>Categoria</b>", cap), Paragraph("<b>Risco</b>", cap),
            Paragraph("<b>Shadow AI</b>", cap), Paragraph("<b>Status</b>", cap),
        ]
        inv_rows = [inv_header]
        for a in all_assets:
            rl = a.get("risk_level", "medium")
            rc = risk_color(rl)
            inv_rows.append([
                Paragraph(a["name"][:45], body),
                Paragraph((a.get("vendor") or "—")[:25], sm),
                Paragraph((a.get("subcategory") or a.get("category", ""))[:30], sm),
                Paragraph(f"<font color='#{int(rc.red*255):02x}{int(rc.green*255):02x}{int(rc.blue*255):02x}'><b>{rl}</b></font>", body),
                Paragraph("✓" if a.get("is_shadow_ai") else "—", body),
                Paragraph(status_label(a.get("analyst_status", "")), sm),
            ])
        col_w = (PAGE_W - 2*MARGIN)
        inv_table = Table(inv_rows, colWidths=[col_w*0.26, col_w*0.16, col_w*0.22, col_w*0.10, col_w*0.10, col_w*0.16])
        inv_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  _rgb(BRAND_DARK)),
            ("TEXTCOLOR",     (0,0), (-1,0),  white),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [white, slate50]),
            ("INNERGRID",     (0,0), (-1,-1), 0.3, _rgb((226,232,240))),
            ("BOX",           (0,0), (-1,-1), 0.5, _rgb((203,213,225))),
            ("TOPPADDING",    (0,0), (-1,-1), 4), ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 6), ("FONTSIZE",(0,0),(-1,-1), 8),
        ]))
        story.append(inv_table)

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 3. SHADOW AI
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Análise de Shadow AI", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=_rgb((226,232,240)), spaceAfter=10))

    shadow_assets = data.get("shadow_assets", [])
    if not shadow_assets:
        story.append(Paragraph("Nenhum asset de Shadow AI identificado nesta análise.", body))
    else:
        intro = (
            f"Foram identificados <b>{len(shadow_assets)} assets de Shadow AI</b> — ferramentas de IA sendo "
            f"utilizadas na organização sem aprovação formal, fora do controle do departamento de TI. "
            f"Shadow AI representa risco de vazamento de dados, violações de compliance e exposição de propriedade intelectual."
        )
        story.append(Paragraph(intro, body))
        story.append(Spacer(1, 0.3*cm))

        for a in shadow_assets:
            rl = a.get("risk_level", "medium")
            rc = risk_color(rl)
            block = [
                [
                    Paragraph(f"<b>{a['name']}</b>", h3),
                    Paragraph(
                        f"<font color='#{int(rc.red*255):02x}{int(rc.green*255):02x}{int(rc.blue*255):02x}'>"
                        f"<b>{rl.upper()} · {a.get('risk_score', 5)}/10</b></font>",
                        body
                    ),
                ],
                [
                    Paragraph(
                        f"<font color='#64748b'>Vendor:</font> {a.get('vendor') or '—'} · "
                        f"<font color='#64748b'>Categoria:</font> {a.get('category', '')} · "
                        f"<font color='#64748b'>Detectado em:</font> {fmt_date(a.get('first_seen_at'))}",
                        sm
                    ),
                    Paragraph(""),
                ],
            ]
            if a.get("description"):
                block.append([Paragraph(a["description"][:300], sm), Paragraph("")])
            if a.get("analyst_notes"):
                block.append([Paragraph(f"<b>Nota do analista:</b> {a['analyst_notes'][:200]}", sm), Paragraph("")])

            t = Table(block, colWidths=[(PAGE_W - 2*MARGIN)*0.72, (PAGE_W - 2*MARGIN)*0.28])
            t.setStyle(TableStyle([
                ("BOX",    (0,0), (-1,-1), 0.5, _rgb((226,232,240))),
                ("BACKGROUND", (0,0), (-1,-1), slate50),
                ("LEFTPADDING",(0,0),(-1,-1), 10), ("RIGHTPADDING",(0,0),(-1,-1), 10),
                ("TOPPADDING",(0,0),(-1,-1), 6), ("BOTTOMPADDING",(0,0),(-1,-1), 6),
                ("SPAN", (0,1), (1,1)),
            ]))
            story.append(KeepTogether([t, Spacer(1, 0.2*cm)]))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 4. HIGH / CRITICAL RISK ASSETS
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("4. Assets de Alto e Crítico Risco", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=_rgb((226,232,240)), spaceAfter=10))

    high_risk = data.get("high_risk_assets", [])
    if not high_risk:
        story.append(Paragraph("Nenhum asset de risco alto ou crítico identificado.", body))
    else:
        story.append(Paragraph(
            f"Os {len(high_risk)} assets abaixo requerem atenção prioritária das equipes de "
            f"segurança, compliance e TI.", body
        ))
        story.append(Spacer(1, 0.3*cm))

        hr_header = [
            Paragraph("<b>Asset</b>", cap), Paragraph("<b>Vendor</b>", cap),
            Paragraph("<b>Nível</b>", cap), Paragraph("<b>Score</b>", cap),
            Paragraph("<b>Shadow AI</b>", cap), Paragraph("<b>Ação Recomendada</b>", cap),
        ]
        hr_rows = [hr_header]
        for a in high_risk:
            rl = a.get("risk_level", "high")
            rc = risk_color(rl)
            action = a.get("analyst_notes", "Revisar com responsável e definir plano de ação")[:60] or "Revisar com responsável"
            hr_rows.append([
                Paragraph(a["name"][:40], body),
                Paragraph((a.get("vendor") or "—")[:20], sm),
                Paragraph(f"<font color='#{int(rc.red*255):02x}{int(rc.green*255):02x}{int(rc.blue*255):02x}'><b>{rl}</b></font>", body),
                Paragraph(str(a.get("risk_score", 5)), body),
                Paragraph("Sim" if a.get("is_shadow_ai") else "Não", sm),
                Paragraph(action, sm),
            ])
        col_w = (PAGE_W - 2*MARGIN)
        hr_table = Table(hr_rows, colWidths=[col_w*0.22, col_w*0.13, col_w*0.10, col_w*0.08, col_w*0.10, col_w*0.37])
        hr_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  _rgb((127,29,29))),
            ("TEXTCOLOR",     (0,0), (-1,0),  white),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [white, colors.Color(1, 0.97, 0.97)]),
            ("INNERGRID",     (0,0), (-1,-1), 0.3, _rgb((254,226,226))),
            ("BOX",           (0,0), (-1,-1), 0.5, _rgb((252,165,165))),
            ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ]))
        story.append(hr_table)

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 5. RECOMENDAÇÕES
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("5. Recomendações", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=_rgb((226,232,240)), spaceAfter=10))

    recs = [
        ("🔴 Prioridade Crítica", [
            f"Bloquear ou restringir imediatamente os {stats.get('critical', 0)} asset(s) de nível crítico identificados.",
            "Realizar investigação forense em casos de Shadow AI com dados sensíveis.",
            "Notificar o DPO (Data Protection Officer) sobre exposições de dados identificadas.",
        ]),
        ("🟠 Curto Prazo (30 dias)", [
            f"Revisar os {stats.get('high_risk', 0)} assets de alto risco com proprietários de negócio.",
            f"Criar processo formal de aprovação para os {stats.get('shadow_ai', 0)} tools de Shadow AI em uso.",
            "Implementar política de uso aceitável de IA generativa.",
            "Configurar monitoramento contínuo via conectores para detecção proativa.",
        ]),
        ("🟡 Médio Prazo (90 dias)", [
            "Estabelecer registro oficial (AI Asset Registry) para todos os tools aprovados.",
            "Treinar equipes sobre riscos de Shadow AI e canais de aprovação.",
            "Implementar Data Loss Prevention (DLP) para endpoints de AI APIs sensíveis.",
            "Agendar próximo scan de discovery completo.",
        ]),
        ("🟢 Contínuo", [
            "Manter ciclos de discovery trimestrais para detectar novos assets.",
            "Integrar AI Asset Registry ao processo de onboarding de novos fornecedores.",
            "Revisar e atualizar políticas de IA anualmente.",
        ]),
    ]

    for title, items in recs:
        story.append(Paragraph(title, h3))
        for item in items:
            story.append(Paragraph(f"• {item}", body))
        story.append(Spacer(1, 0.2*cm))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 6. METODOLOGIA E DISCLAIMER
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("6. Metodologia e Disclaimer", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=_rgb((226,232,240)), spaceAfter=10))

    methodology = (
        "Este relatório foi gerado pela plataforma <b>Digital Mind AI Discovery</b> com base na análise automatizada "
        "de fontes de dados fornecidas pela organização. A metodologia combina três abordagens complementares: "
        "(1) <b>Análise de conectores cloud</b> — varredura direta de recursos Azure, AWS e GCP via APIs de gerenciamento; "
        "(2) <b>Análise de logs e arquivos</b> — parseamento de logs de proxy, audit logs de M365, activity logs do Azure "
        "e arquivos CSV fornecidos pela equipe de TI; "
        "(3) <b>Enriquecimento por IA</b> — classificação e análise contextual de assets usando Claude (Anthropic) "
        "com base em taxonomia proprietária de mais de 50 tools de IA conhecidos."
    )
    story.append(Paragraph(methodology, body))
    story.append(Spacer(1, 0.4*cm))

    disclaimer = (
        "<b>Disclaimer:</b> Este relatório é baseado nas informações disponíveis no momento da análise e pode não "
        "representar a totalidade dos assets de IA em uso na organização. A Digital Mind recomenda complementar "
        "esta análise com entrevistas com líderes de negócio e revisão manual de contratos SaaS. "
        "As classificações de risco são indicativas e devem ser validadas pelo time de segurança da informação. "
        "Este documento é <b>confidencial</b> e destinado exclusivamente ao uso interno da organização analisada."
    )
    story.append(Table([[Paragraph(disclaimer, sm)]], colWidths=[PAGE_W - 2*MARGIN],
        style=[("BACKGROUND",(0,0),(-1,-1),slate50), ("BOX",(0,0),(-1,-1),0.5,_rgb((226,232,240))),
               ("TOPPADDING",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),10),
               ("LEFTPADDING",(0,0),(-1,-1),12)]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()


# ─── Storage helpers ──────────────────────────────────────────────────────────

async def _save_report_to_storage(
    workspace_slug: str,
    report_id: int,
    pdf_bytes: bytes,
    filename: str,
) -> tuple[str, int]:
    """Upload PDF to MinIO and return (storage_key, file_size)."""
    s3 = get_s3_client()
    bucket = get_bucket_name(workspace_slug)
    ensure_bucket(s3, bucket)
    storage_key = f"reports/{report_id}/{filename}"
    s3.put_object(
        Bucket=bucket, Key=storage_key, Body=pdf_bytes,
        ContentType="application/pdf",
        Metadata={"report-id": str(report_id), "workspace": workspace_slug},
    )
    return storage_key, len(pdf_bytes)


async def _update_report_status(
    db: AsyncSession, schema: str, report_id: int,
    status: str, storage_key: str | None = None,
    file_size: int | None = None, error: str | None = None,
    snapshot: dict | None = None,
) -> None:
    await db.execute(text(f"""
        UPDATE "{schema}".reports
        SET status = :status,
            storage_key = :storage_key,
            file_size = :file_size,
            error_message = :error,
            snapshot = :snapshot::jsonb,
            updated_at = NOW()
        WHERE id = :id
    """), {
        "status": status, "storage_key": storage_key,
        "file_size": file_size, "error": error,
        "snapshot": json.dumps(snapshot or {}), "id": report_id,
    })
    await db.commit()


# ─── Public API ───────────────────────────────────────────────────────────────

async def generate_report(
    db: AsyncSession,
    workspace_slug: str,
    workspace_name: str,
    report_id: int,
    title: str,
) -> dict[str, Any]:
    """
    Full pipeline: collect data → generate PDF → upload to MinIO → update DB.
    Returns a summary dict.
    """
    schema = get_schema_name(workspace_slug)
    try:
        # Collect data
        data = await _collect_report_data(db, workspace_slug, workspace_name)

        # Generate PDF
        pdf_bytes = _generate_pdf(data)

        # Upload
        safe_name = title.lower().replace(" ", "_")[:40]
        filename = f"{safe_name}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
        storage_key, file_size = await _save_report_to_storage(
            workspace_slug, report_id, pdf_bytes, filename
        )

        # Update DB
        snapshot = {
            "total_assets": data["stats"].get("total_assets", 0),
            "shadow_ai":    data["stats"].get("shadow_ai", 0),
            "critical":     data["stats"].get("critical", 0),
            "high_risk":    data["stats"].get("high_risk", 0),
        }
        await _update_report_status(
            db, schema, report_id, "ready",
            storage_key=storage_key, file_size=file_size, snapshot=snapshot,
        )
        return {"report_id": report_id, "status": "ready", "file_size": file_size}

    except Exception as e:
        logger.exception(f"Report generation failed for report {report_id}: {e}")
        await _update_report_status(db, schema, report_id, "error", error=str(e))
        raise


async def list_reports(db: AsyncSession, workspace_slug: str) -> list[dict]:
    schema = get_schema_name(workspace_slug)
    result = await db.execute(text(f"""
        SELECT id, title, report_type, format, status, file_size,
               generated_by_email, snapshot, error_message, created_at, updated_at
        FROM "{schema}".reports
        ORDER BY created_at DESC
    """))
    return [dict(row) for row in result.mappings().all()]


async def get_report_download_url(
    db: AsyncSession,
    workspace_slug: str,
    report_id: int,
) -> tuple[str, str] | None:
    """Returns (presigned_url, filename) or None if not found/ready."""
    schema = get_schema_name(workspace_slug)
    result = await db.execute(text(f"""
        SELECT storage_key, title FROM "{schema}".reports
        WHERE id = :id AND status = 'ready'
    """), {"id": report_id})
    row = result.mappings().one_or_none()
    if not row or not row["storage_key"]:
        return None

    s3 = get_s3_client()
    bucket = get_bucket_name(workspace_slug)
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": row["storage_key"]},
            ExpiresIn=3600,  # 1 hour
        )
        filename = row["storage_key"].split("/")[-1]
        return url, filename
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        return None
