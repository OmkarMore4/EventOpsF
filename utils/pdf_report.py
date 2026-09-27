"""
Generates a single polished "Event Report" PDF: event details, summary
stats, an attendance table and a tasks table. Alongside the CSV exports,
this is meant as the "hand this to someone" deliverable — a professor,
a college office, a sponsor.

Uses reportlab's high-level Platypus API (SimpleDocTemplate + Table/
Paragraph flowables) rather than the low-level canvas, specifically so
long tables paginate automatically instead of needing manual page-break
math.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

INK = colors.HexColor("#14171C")
SIGNAL = colors.HexColor("#D97706")
SLATE = colors.HexColor("#5B6472")
PAPER = colors.HexColor("#F6F4EF")
BORDER = colors.HexColor("#E7E4DC")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, textColor=INK, spaceAfter=2))
    styles.add(ParagraphStyle("ReportMeta", parent=styles["Normal"], fontSize=9, textColor=SLATE, spaceAfter=14))
    styles.add(ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontSize=13, textColor=INK, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("Empty", parent=styles["Normal"], fontSize=9, textColor=SLATE))
    return styles


def _details_table(event):
    data = [
        ["Venue", event.get("venue", "")],
        ["Dates", f"{event.get('start_date', '')} to {event.get('end_date', '')}"],
        ["Geofence radius", f"{event.get('geofence_radius', '')}m"],
        ["Domains", ", ".join(event.get("domains", []))],
    ]
    table = Table(data, colWidths=[32 * mm, 138 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), SLATE),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _stats_table(stats):
    header = ["Volunteers", "Attendance records", "Tasks completed", "Issues resolved"]
    values = [
        str(stats.get("total_volunteers", 0)),
        str(stats.get("total_attendance_records", 0)),
        f"{stats.get('completed_tasks', 0)} / {stats.get('total_tasks', 0)}",
        f"{stats.get('resolved_issues', 0)} / {stats.get('total_issues', 0)}",
    ]
    table = Table([header, values], colWidths=[42.5 * mm] * 4)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 13),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    return table


def _data_table(header, rows, col_widths):
    if not rows:
        return None
    table = Table([header] + rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SIGNAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _fmt_time(dt):
    return dt.strftime("%I:%M %p") if dt else "\u2013"


def build_event_report_pdf(event, stats, attendance_docs, task_docs):
    """Returns a BytesIO containing the finished PDF (seek(0) already called)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"{event.get('name', 'Event')} report",
    )
    styles = _styles()
    story = []

    story.append(Paragraph(event.get("name", "Event Report"), styles["ReportTitle"]))
    story.append(Paragraph(
        f"Event report &bull; generated {datetime.now().strftime('%d %b %Y, %I:%M %p')}", styles["ReportMeta"]
    ))
    story.append(_details_table(event))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Summary", styles["SectionHeading"]))
    story.append(_stats_table(stats))

    story.append(Paragraph("Attendance", styles["SectionHeading"]))
    att_rows = []
    for a in attendance_docs:
        ci, co = a.get("check_in") or {}, a.get("check_out") or {}
        status = "Checked out" if co else ("Present" if ci else "Incomplete")
        att_rows.append([
            a.get("volunteer_name", ""), a.get("date", ""),
            _fmt_time(ci.get("time")), _fmt_time(co.get("time")), status,
        ])
    att_table = _data_table(
        ["Volunteer", "Date", "Check-in", "Check-out", "Status"], att_rows,
        [42 * mm, 24 * mm, 30 * mm, 30 * mm, 44 * mm],
    )
    story.append(att_table if att_table else Paragraph("No attendance recorded yet.", styles["Empty"]))

    story.append(Paragraph("Tasks", styles["SectionHeading"]))
    task_rows = []
    for t in task_docs:
        task_rows.append([
            t.get("title", ""), t.get("domain") or "\u2013", t.get("assigned_to_name") or "\u2013",
            (t.get("priority") or "").capitalize(), (t.get("status") or "").replace("-", " ").capitalize(),
        ])
    task_table = _data_table(
        ["Title", "Domain", "Assigned to", "Priority", "Status"], task_rows,
        [46 * mm, 32 * mm, 38 * mm, 22 * mm, 32 * mm],
    )
    story.append(task_table if task_table else Paragraph("No tasks created yet.", styles["Empty"]))

    doc.build(story)
    buffer.seek(0)
    return buffer
