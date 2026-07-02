"""
report.py — Gerador de relatório PDF de conformidade
Produz relatório no padrão ANVISA/MAPA com:
  - Cabeçalho institucional
  - Resumo do período
  - Gráfico de temperatura / pressão (matplotlib)
  - Tabela de estatísticas
  - Log de alarmes e desvios
  - Rodapé com assinatura e timestamp
"""

import io
import logging
from datetime import datetime, UTC, timedelta
from typing import Optional

import matplotlib
matplotlib.use("Agg")   # backend sem GUI — obrigatório em servidor
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Line
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger("coletor.report")

# ── Registro de fontes TrueType (evita erro 0xc06d007e no Acrobat) ────────────
# Usa Arial do Windows — embutida no PDF, sem dependência do viewer
_FONTS_REGISTERED = False

def _ensure_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        _win_fonts = "C:/Windows/Fonts/"
        pdfmetrics.registerFont(TTFont("ReportNormal",  _win_fonts + "arial.ttf"))
        pdfmetrics.registerFont(TTFont("ReportBold",    _win_fonts + "arialbd.ttf"))
        pdfmetrics.registerFont(TTFont("ReportItalic",  _win_fonts + "ariali.ttf"))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("ReportNormal",
                           normal="ReportNormal",
                           bold="ReportBold",
                           italic="ReportItalic",
                           boldItalic="ReportBold")
        _FONTS_REGISTERED = True
        logger.info("Fontes TrueType (Arial) registradas com sucesso")
    except Exception as e:
        logger.warning("Não foi possível registrar fontes TTF: %s — usando Helvetica", e)
        _FONTS_REGISTERED = True   # evita nova tentativa

# ── Caminhos de logos ─────────────────────────────────────────
from pathlib import Path
_STATIC = Path(__file__).parent / "static" / "img"
LOGO_RCR      = str(_STATIC / "logo_rcr.png")
LOGO_ICENEXUS = str(_STATIC / "logo_icenexus.png")

# ── Paleta ────────────────────────────────────────────────────
C_DARK_BLUE  = colors.HexColor("#0d1f3c")
C_BLUE       = colors.HexColor("#1a4a8c")
C_LIGHT_BLUE = colors.HexColor("#e8f0ff")
C_CYAN       = colors.HexColor("#00b4d8")
C_GREEN      = colors.HexColor("#2dc653")
C_YELLOW     = colors.HexColor("#d4a017")
C_RED        = colors.HexColor("#c0392b")
C_ORANGE     = colors.HexColor("#e3724a")
C_GRAY       = colors.HexColor("#6c757d")
C_LIGHT_GRAY = colors.HexColor("#f4f6f9")
C_BORDER     = colors.HexColor("#dee2e6")
C_WHITE      = colors.white
C_BLACK      = colors.black


# ══════════════════════════════════════════════════════════════
# GERAÇÃO DO GRÁFICO (matplotlib → PNG em memória)
# ══════════════════════════════════════════════════════════════

def _build_chart(readings: list[dict], model_id: int, width_px=900, height_px=320) -> io.BytesIO:
    """Gera gráfico de tendência e retorna PNG em buffer."""
    is_pct = (model_id == 117)

    fig, ax1 = plt.subplots(figsize=(width_px / 100, height_px / 100), dpi=100)
    fig.patch.set_facecolor("#f8f9fa")
    ax1.set_facecolor("#ffffff")

    timestamps = [datetime.fromisoformat(r["timestamp"]) for r in readings]

    if is_pct:
        # ── PCT-122E: P1/P2 eixo esquerdo + T1/T3 eixo direito ─
        ax2 = ax1.twinx()

        p1_vals = [r.get("p1") for r in readings]
        p2_vals = [r.get("p2") for r in readings]
        t1_vals = [r.get("t1") for r in readings]
        t3_vals = [r.get("t3") for r in readings]

        ax1.plot(timestamps, p2_vals, color="#8957e5", linewidth=1.8,
                 label="P2 Descarga (PSIG)", zorder=3)
        ax1.plot(timestamps, p1_vals, color="#388bfd", linewidth=1.8,
                 label="P1 Sucção (PSIG)", zorder=3)
        ax1.set_ylabel("Pressão (PSIG)", color="#555", fontsize=9)
        ax1.tick_params(axis='y', labelcolor="#555", labelsize=8)

        ax2.plot(timestamps, t3_vals, color="#3fb950", linewidth=1.6,
                 linestyle="--", label="T3 Câmara (°C)", zorder=2)
        ax2.plot(timestamps, t1_vals, color="#39c5cf", linewidth=1.4,
                 linestyle=":", label="T1 Sucção (°C)", zorder=2)
        ax2.set_ylabel("Temperatura (°C)", color="#555", fontsize=9)
        ax2.tick_params(axis='y', labelcolor="#555", labelsize=8)

        # Junta legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2,
                   loc="upper left", fontsize=8, framealpha=0.85)

        ax1.set_title("Histórico de Pressão e Temperatura — R404A", fontsize=10,
                      color="#333", pad=8, fontweight="bold")

    else:
        # ── TC-900E: temperaturas ────────────────────────────────
        t1_vals = [r.get("t1") for r in readings]
        t2_vals = [r.get("t2") for r in readings]
        t3_vals = [r.get("t3") for r in readings]
        sp_vals = [r.get("setpoint") for r in readings]

        ax1.plot(timestamps, t1_vals, color="#388bfd", linewidth=1.8, label="T1 Sonda 1 (°C)")
        ax1.plot(timestamps, t2_vals, color="#3fb950", linewidth=1.8, label="T2 Sonda 2 (°C)")
        ax1.plot(timestamps, t3_vals, color="#8957e5", linewidth=1.8, label="T3 Sonda 3 (°C)")
        if any(v is not None for v in sp_vals):
            ax1.plot(timestamps, sp_vals, color="#d29922", linewidth=1.4,
                     linestyle="--", label="Setpoint (°C)")

        ax1.set_ylabel("Temperatura (°C)", color="#555", fontsize=9)
        ax1.tick_params(axis='y', labelcolor="#555", labelsize=8)
        ax1.legend(loc="upper left", fontsize=8, framealpha=0.85)
        ax1.set_title("Histórico de Temperatura", fontsize=10,
                      color="#333", pad=8, fontweight="bold")

    # Eixo X — formata tempo
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30, ha="right")

    ax1.tick_params(axis='x', labelsize=8)
    ax1.grid(axis='y', color='#e0e0e0', linewidth=0.5, linestyle='--')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    plt.tight_layout(pad=1.2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════════
# GERAÇÃO DO PDF (reportlab)
# ══════════════════════════════════════════════════════════════

def generate_pdf(
    instrument: dict,
    readings: list[dict],
    alarms: list[dict],
    period_start: datetime,
    period_end: datetime,
    company_name: str = "[PROPONENTE]",
    operator_name: str = "Sistema Automático",
) -> bytes:
    """
    Gera PDF de conformidade e retorna bytes prontos para download.

    instrument: dict com id, name, address, model_id, model_name, source
    readings:   lista de dicts do endpoint /history
    alarms:     lista de dicts do endpoint /alarms/history
    """
    _ensure_fonts()

    # Aliases — usa TTF registradas se disponíveis, senão Helvetica padrão
    F_NORMAL = "ReportNormal" if _FONTS_REGISTERED else "Helvetica"
    F_BOLD   = "ReportBold"   if _FONTS_REGISTERED else "Helvetica-Bold"

    buf = io.BytesIO()

    # ── Página A4, margens 20mm ───────────────────────────────
    W, H = A4
    ML = MR = 20 * mm
    MT = 15 * mm
    MB = 20 * mm

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=ML, rightMargin=MR,
        topMargin=MT, bottomMargin=MB,
    )

    content_w = W - ML - MR

    # ── Page template com header/footer ───────────────────────
    def _header_footer(canvas, doc):
        canvas.saveState()

        # ── Header bar ────────────────────────────────────────
        canvas.setFillColor(C_DARK_BLUE)
        canvas.rect(0, H - 16 * mm, W, 16 * mm, fill=1, stroke=0)

        # Logo RCR (esquerda)
        logo_h = 10 * mm
        logo_y = H - 14 * mm
        if Path(LOGO_RCR).exists():
            try:
                canvas.drawImage(LOGO_RCR, ML, logo_y,
                                 height=logo_h, width=logo_h,
                                 preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Logo IceNexus (direita)
        if Path(LOGO_ICENEXUS).exists():
            try:
                canvas.drawImage(LOGO_ICENEXUS, W - MR - 38 * mm, logo_y + 1 * mm,
                                 height=logo_h * 0.7, width=38 * mm,
                                 preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Texto central
        canvas.setFont(F_BOLD, 8)
        canvas.setFillColor(C_WHITE)
        canvas.drawCentredString(W / 2, H - 7 * mm,
                                 f"RELATÓRIO DE CONFORMIDADE — {instrument['name'].upper()}")
        canvas.setFont(F_NORMAL, 6.5)
        canvas.setFillColor(colors.HexColor("#a0b8d0"))
        canvas.drawCentredString(W / 2, H - 11.5 * mm,
                                 f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        # ── Footer bar ────────────────────────────────────────
        canvas.setFillColor(C_DARK_BLUE)
        canvas.rect(0, 0, W, 10 * mm, fill=1, stroke=0)
        canvas.setFont(F_NORMAL, 7)
        canvas.setFillColor(C_WHITE)
        canvas.drawString(ML, 3.5 * mm,
                          f"{company_name}  |  IceNexusIAR — Monitoramento Inteligente de Cadeia Fria")
        canvas.drawRightString(W - MR, 3.5 * mm, f"Pág. {doc.page}")

        canvas.restoreState()

    frame = Frame(ML, MB, content_w, H - MT - MB - 16 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=_header_footer)])

    # ── Estilos ───────────────────────────────────────────────
    styles = getSampleStyleSheet()
    s_title   = ParagraphStyle("title",   fontSize=16, textColor=C_DARK_BLUE,
                                fontName=F_BOLD, spaceAfter=2)
    s_subtitle= ParagraphStyle("sub",     fontSize=9,  textColor=C_GRAY,
                                fontName=F_NORMAL, spaceAfter=8)
    s_h2      = ParagraphStyle("h2",      fontSize=11, textColor=C_DARK_BLUE,
                                fontName=F_BOLD, spaceBefore=10, spaceAfter=4)
    s_h3      = ParagraphStyle("h3",      fontSize=9,  textColor=C_BLUE,
                                fontName=F_BOLD, spaceBefore=6, spaceAfter=3)
    s_normal  = ParagraphStyle("normal",  fontSize=8,  textColor=C_BLACK,
                                fontName=F_NORMAL, leading=12)
    s_small   = ParagraphStyle("small",   fontSize=7,  textColor=C_GRAY,
                                fontName=F_NORMAL, leading=10)
    s_center  = ParagraphStyle("center",  fontSize=8,  textColor=C_GRAY,
                                fontName=F_NORMAL, alignment=TA_CENTER)
    s_warning = ParagraphStyle("warn",    fontSize=8,  textColor=C_RED,
                                fontName=F_BOLD)
    s_ok      = ParagraphStyle("ok",      fontSize=8,  textColor=C_GREEN,
                                fontName=F_BOLD)

    story = []

    # ══════════════════════════════════════════════════════════
    # CABEÇALHO DO RELATÓRIO
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph("RELATÓRIO DE CONFORMIDADE DE TEMPERATURA", s_title))
    story.append(Paragraph("Monitoramento Contínuo de Cadeia Fria — Conforme RDC 430/2020 (ANVISA) / IN 87/2019 (MAPA)", s_subtitle))
    story.append(HRFlowable(width="100%", thickness=2, color=C_DARK_BLUE, spaceAfter=10))

    # ── Info do instrumento + período (tabela 2 colunas) ─────
    period_str = (f"{period_start.strftime('%d/%m/%Y %H:%M')}  →  "
                  f"{period_end.strftime('%d/%m/%Y %H:%M')}")

    total_readings   = len(readings)
    expected_readings = max(1, int((period_end - period_start).total_seconds() / 30))
    coverage_pct     = min(100, round(total_readings / expected_readings * 100, 1))

    active_alarms  = [a for a in alarms if a.get("is_active")]
    total_alarms   = len(alarms)
    resolved_alarms = len([a for a in alarms if not a.get("is_active")])

    compliance_ok = (total_alarms == 0) and (coverage_pct >= 95)
    compliance_text = "CONFORME" if compliance_ok else "REQUER ATENÇÃO"
    compliance_color = C_GREEN if compliance_ok else C_RED

    info_data = [
        ["INSTRUMENTO",   instrument["name"]],
        ["MODELO",        instrument.get("model_name") or "—"],
        ["ENDEREÇO RS-485", f"{instrument['address']}"],
        ["FONTE",         "Sitrad PRO" if instrument.get("source") == "sitrad" else "Emulador Local"],
        ["PERÍODO",       period_str],
        ["TOTAL DE LEITURAS", f"{total_readings:,}  ({coverage_pct}% de cobertura)"],
        ["ALARMES NO PERÍODO", f"{total_alarms} total  |  {len(active_alarms)} ativos  |  {resolved_alarms} resolvidos"],
        ["STATUS CONFORMIDADE", compliance_text],
    ]

    row_styles = []
    for i, row in enumerate(info_data):
        bg = C_LIGHT_GRAY if i % 2 == 0 else C_WHITE
        row_styles.append(('BACKGROUND', (0, i), (-1, i), bg))
    # Linha de conformidade colorida
    conf_row = len(info_data) - 1
    row_styles.append(('TEXTCOLOR', (1, conf_row), (1, conf_row), compliance_color))
    row_styles.append(('FONTNAME',  (1, conf_row), (1, conf_row), F_BOLD))

    info_tbl = Table(
        [[Paragraph(f"<b>{k}</b>", s_small), Paragraph(v, s_normal)]
         for k, v in info_data],
        colWidths=[content_w * 0.35, content_w * 0.65],
        hAlign="LEFT",
    )
    info_tbl.setStyle(TableStyle([
        ('FONTSIZE',  (0, 0), (-1, -1), 8),
        ('GRID',      (0, 0), (-1, -1), 0.3, C_BORDER),
        ('VALIGN',    (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING',   (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
        *row_styles,
    ]))
    story.append(info_tbl)

    # ══════════════════════════════════════════════════════════
    # ESTATÍSTICAS
    # ══════════════════════════════════════════════════════════
    story.append(Spacer(1, 8))
    story.append(Paragraph("ESTATÍSTICAS DO PERÍODO", s_h2))

    is_pct = (instrument.get("model_id") == 117)

    def _stats(values: list) -> dict:
        vals = [v for v in values if v is not None]
        if not vals:
            return {"min": "—", "max": "—", "avg": "—", "count": 0}
        return {
            "min":   f"{min(vals):.1f}",
            "max":   f"{max(vals):.1f}",
            "avg":   f"{sum(vals)/len(vals):.1f}",
            "count": len(vals),
        }

    if is_pct:
        stat_rows = [
            ["PARÂMETRO",         "MÍNIMO",    "MÁXIMO",    "MÉDIA",     "LEITURAS"],
            ["P1 Sucção (PSIG)",  *[_stats([r.get("p1") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["P2 Descarga (PSIG)",*[_stats([r.get("p2") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["T1 Gás Sucção (°C)",*[_stats([r.get("t1") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["T2 Gás Descarga (°C)",*[_stats([r.get("t2") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["T3 Câmara Fria (°C)",*[_stats([r.get("t3") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["T4 Aletado (°C)",   *[_stats([r.get("t4") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["Superaquec. SH (K)",*[_stats([r.get("superheat") for r in readings])[k] for k in ["min","max","avg","count"]]],
        ]
    else:
        stat_rows = [
            ["PARÂMETRO",        "MÍNIMO",    "MÁXIMO",    "MÉDIA",     "LEITURAS"],
            ["T1 Sonda 1 (°C)", *[_stats([r.get("t1") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["T2 Sonda 2 (°C)", *[_stats([r.get("t2") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["T3 Sonda 3 (°C)", *[_stats([r.get("t3") for r in readings])[k] for k in ["min","max","avg","count"]]],
            ["Setpoint (°C)",   *[_stats([r.get("setpoint") for r in readings])[k] for k in ["min","max","avg","count"]]],
        ]

    stat_tbl = Table(
        stat_rows,
        colWidths=[content_w * 0.38, *([content_w * 0.155] * 4)],
        hAlign="LEFT",
    )
    stat_tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), C_DARK_BLUE),
        ('TEXTCOLOR',    (0, 0), (-1, 0), C_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), F_BOLD),
        ('FONTSIZE',     (0, 0), (-1, -1), 8),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('GRID',         (0, 0), (-1, -1), 0.3, C_BORDER),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
        ('LEFTPADDING',  (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_LIGHT_GRAY]),
    ]))
    story.append(stat_tbl)

    # ══════════════════════════════════════════════════════════
    # GRÁFICO
    # ══════════════════════════════════════════════════════════
    story.append(Spacer(1, 8))
    story.append(Paragraph("GRÁFICO DE TENDÊNCIA", s_h2))

    if readings:
        try:
            chart_buf = _build_chart(readings, instrument.get("model_id", 72))
            img = Image(chart_buf, width=content_w, height=content_w * 0.35)
            story.append(img)
            story.append(Paragraph(
                f"Gráfico gerado com {total_readings} leituras  |  intervalo de coleta: 30 segundos",
                s_center,
            ))
        except Exception as e:
            logger.error("Erro ao gerar gráfico: %s", e)
            story.append(Paragraph("⚠ Gráfico não disponível.", s_warning))
    else:
        story.append(Paragraph("Sem dados para gerar gráfico no período.", s_center))

    # ══════════════════════════════════════════════════════════
    # LOG DE ALARMES
    # ══════════════════════════════════════════════════════════
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"LOG DE ALARMES E DESVIOS   ({total_alarms} ocorrência(s) no período)", s_h2))

    if alarms:
        alarm_header = ["SEV.", "CÓDIGO", "DESCRIÇÃO", "INÍCIO", "FIM", "STATUS"]
        alarm_rows   = [alarm_header]

        for a in alarms:
            sev_icon = "🔴 CRÍTICO" if a["severity"] == "alarm" else "🟡 AVISO"
            inicio   = datetime.fromisoformat(a["started_at"]).strftime("%d/%m %H:%M:%S")
            fim      = (datetime.fromisoformat(a["cleared_at"]).strftime("%d/%m %H:%M:%S")
                        if a.get("cleared_at") else "—")
            status   = "Ativo" if a.get("is_active") else "Resolvido"
            alarm_rows.append([sev_icon, a["code"], a["description"], inicio, fim, status])

        alarm_tbl = Table(
            alarm_rows,
            colWidths=[
                content_w * 0.13, content_w * 0.12, content_w * 0.33,
                content_w * 0.15, content_w * 0.15, content_w * 0.12,
            ],
            hAlign="LEFT",
            repeatRows=1,
        )
        alarm_style = [
            ('BACKGROUND',   (0, 0), (-1, 0), C_DARK_BLUE),
            ('TEXTCOLOR',    (0, 0), (-1, 0), C_WHITE),
            ('FONTNAME',     (0, 0), (-1, 0), F_BOLD),
            ('FONTSIZE',     (0, 0), (-1, -1), 7),
            ('GRID',         (0, 0), (-1, -1), 0.3, C_BORDER),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',   (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
            ('LEFTPADDING',  (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_LIGHT_GRAY]),
        ]
        # Colorir linha por severidade
        for i, a in enumerate(alarms, start=1):
            if a.get("is_active"):
                alarm_style.append(('TEXTCOLOR', (5, i), (5, i), C_RED))
                alarm_style.append(('FONTNAME',  (5, i), (5, i), F_BOLD))
            else:
                alarm_style.append(('TEXTCOLOR', (5, i), (5, i), C_GREEN))

        alarm_tbl.setStyle(TableStyle(alarm_style))
        story.append(alarm_tbl)
    else:
        story.append(Paragraph("✓  Nenhum alarme ou desvio registrado no período.", s_ok))

    # ══════════════════════════════════════════════════════════
    # DECLARAÇÃO DE CONFORMIDADE
    # ══════════════════════════════════════════════════════════
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph("DECLARAÇÃO DE CONFORMIDADE", s_h2))

    decl_text = (
        f"O presente relatório atesta que o instrumento <b>{instrument['name']}</b> "
        f"foi monitorado continuamente no período de <b>{period_start.strftime('%d/%m/%Y %H:%M')}</b> "
        f"a <b>{period_end.strftime('%d/%m/%Y %H:%M')}</b>, com cobertura de "
        f"<b>{coverage_pct}%</b> das leituras esperadas. "
        f"O sistema de monitoramento opera em conformidade com os requisitos de rastreabilidade "
        f"de temperatura estabelecidos pela <b>RDC 430/2020 (ANVISA)</b> e "
        f"<b>IN 87/2019 (MAPA)</b>. "
        f"Total de ocorrências de alarme no período: <b>{total_alarms}</b>."
    )
    story.append(Paragraph(decl_text, s_normal))

    story.append(Spacer(1, 16))

    # Assinaturas
    sig_data = [
        [
            Paragraph("_________________________________", s_center),
            Paragraph("_________________________________", s_center),
        ],
        [
            Paragraph(f"<b>{operator_name}</b>", s_center),
            Paragraph(f"<b>Responsável Técnico</b>", s_center),
        ],
        [
            Paragraph("Gerado automaticamente pelo sistema", s_small),
            Paragraph("Carimbo e assinatura", s_small),
        ],
        [
            Paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", s_small),
            Paragraph("Data: ___/___/______", s_small),
        ],
    ]
    sig_tbl = Table(sig_data, colWidths=[content_w * 0.5, content_w * 0.5], hAlign="LEFT")
    sig_tbl.setStyle(TableStyle([
        ('ALIGN',   (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',  (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
    ]))
    story.append(sig_tbl)

    # ── Gera PDF ──────────────────────────────────────────────
    doc.build(story)
    buf.seek(0)
    return buf.read()
