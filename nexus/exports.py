"""Local, printable fee documents. Exporting never marks a payment as received."""
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


NAVY = colors.HexColor("#123766")
TEAL = colors.HexColor("#315884")
GOLD = colors.HexColor("#c5a46d")
MUTED = colors.HexColor("#687b93")
PALE = colors.HexColor("#f3f6fb")


def _money(value):
    return f"Rs {Decimal(str(value)):,.2f}"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Academy", fontName="Times-Bold", fontSize=24, leading=29, textColor=NAVY, spaceAfter=6))
    styles.add(ParagraphStyle("DocTitle", fontName="Helvetica-Bold", fontSize=13, leading=20, textColor=TEAL, spaceBefore=16, spaceAfter=12))
    styles.add(ParagraphStyle("Detail", fontName="Helvetica", fontSize=10, leading=16, textColor=NAVY))
    styles.add(ParagraphStyle("SmallMuted", fontName="Helvetica", fontSize=9, leading=14, textColor=MUTED))
    styles.add(ParagraphStyle("Right", parent=styles["Detail"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle("Center", parent=styles["Detail"], alignment=TA_CENTER))
    return styles


def _p(text, style):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _header(settings, title, number, styles):
    blocks = [_p("ACADEMY ADMINISTRATION  /  ACCOUNTS OFFICE", styles["SmallMuted"]), Spacer(1, 3 * mm), _p(settings["academy_name"], styles["Academy"])]
    if settings.get("address"):
        blocks.append(_p(settings["address"], styles["SmallMuted"]))
    if settings.get("phone"):
        blocks.append(_p("Contact: " + settings["phone"], styles["SmallMuted"]))
    blocks.extend([Spacer(1, 5 * mm), HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=2), HRFlowable(width="100%", thickness=0.75, color=GOLD)])
    blocks.append(_p(title + "  /  " + number, styles["DocTitle"]))
    return blocks


def _details(rows, styles):
    table = Table([[_p(label, styles["SmallMuted"]), _p(value, styles["Detail"])] for label, value in rows], colWidths=[40 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _ledger(rows, styles):
    table = Table([[_p(label, styles["Detail"]), _p(value, styles["Right"])] for label, value in rows], colWidths=[120 * mm, 50 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 13),
        ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("LINEABOVE", (0, -1), (-1, -1), 1, GOLD),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5c5")),
    ]))
    return table


def _write(destination, title, blocks):
    path = Path(destination).expanduser().resolve()
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=22 * mm, bottomMargin=24 * mm, title=title, author="Intellectual Nexus Academy")

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(GOLD)
        canvas.line(20 * mm, 18 * mm, 190 * mm, 18 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 13 * mm, "Intellectual Nexus Academy | Local academy records")
        canvas.drawRightString(190 * mm, 13 * mm, f"Page {document.page}")
        canvas.restoreState()

    # Build in a sibling temporary file so failure never truncates a prior document.
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".nexus-pdf-", suffix=".pdf", dir=path.parent)
    os.close(fd)
    try:
        doc.filename = tmp
        doc.build(blocks, onFirstPage=footer, onLaterPages=footer)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return str(path)


def export_challan(service, challan_id, destination):
    challan = service.challan_details(challan_id)
    settings = service.get_settings()
    styles = _styles()
    blocks = _header(settings, "FEE CHALLAN", challan["number"], styles)
    blocks += [_details([
        ("Student", challan["student_name"]),
        ("Student ID", challan["student_number"]),
        ("Guardian", challan["guardian_name"]),
        ("Class / batch", challan["class_name"]),
        ("Fee period", challan["period"]),
        ("Issued / due", f"{challan['issued_on'][:10]} / {challan['due_date']}"),
        ("Status", challan["status"]),
    ], styles), Spacer(1, 8 * mm)]
    blocks.append(_ledger([
        ("Tuition fee", _money(challan["tuition"])),
        ("Admission / other charges", _money(challan["other"])),
        ("Discount", "- " + _money(challan["discount"])),
        ("Total payable", _money(challan["total"])),
        ("Payments received", _money(challan["paid"])),
        ("Outstanding balance", _money(challan["balance"])),
    ], styles))
    blocks += [Spacer(1, 10 * mm), _p("Please quote this challan number when paying at the academy counter. A challan is a fee request; ask for a numbered payment receipt after payment.", styles["SmallMuted"])]
    return _write(destination, "Fee challan " + challan["number"], blocks)


def export_receipt(service, payment_id, destination):
    payment = next((p for p in service.list_payments() if p["id"] == payment_id), None)
    if payment is None:
        raise ValueError("Select a valid payment receipt.")
    challan = service.challan_details(payment["challan_id"])
    settings = service.get_settings()
    styles = _styles()
    blocks = _header(settings, "PAYMENT RECEIPT", payment["number"], styles)
    if payment["reversed"]:
        blocks.append(_p("REVERSED - this receipt is no longer a valid payment.", styles["DocTitle"]))
    blocks.append(_details([
        ("Student", payment["student_name"]),
        ("Student ID", payment["student_number"]),
        ("Class / batch", challan["class_name"]),
        ("Challan", payment["challan_number"]),
        ("Fee period", challan["period"]),
        ("Received on (UTC)", payment["paid_on"].replace("T", " ")),
        ("Received by", payment["received_by"]),
        ("Payment method", payment["method"]),
        ("Reference", payment["reference"] or "—"),
    ], styles))
    blocks += [Spacer(1, 8 * mm), _ledger([
        ("This payment", _money(payment["amount"])),
        ("Challan total", _money(challan["total"])),
        ("Total paid against challan", _money(challan["paid"])),
        ("Current outstanding balance", _money(challan["balance"])),
    ], styles), Spacer(1, 10 * mm)]
    blocks.append(_p("Thank you. Keep this receipt for your records. Balances reflect academy records at the time this document was generated. Bank transfer and card entries are confirmations entered by the cashier; this offline app does not contact a payment gateway.", styles["SmallMuted"]))
    return _write(destination, "Payment receipt " + payment["number"], blocks)
