"""Printable PDFs of a ticket's legal report: the preliminary report with its document checklist, and the final report
with signature blocks for the advocates to sign by hand after printing."""
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config, report_templates
from .models import LegalReport, ServiceRequest, User

INK = colors.HexColor("#14213d")
MUTED = colors.HexColor("#5b6475")
LINE = colors.HexColor("#c9cfda")
PROPERTY_LABELS = {
    "apartment": "Apartment", "villa": "Villa / row house", "independent_house": "Independent house", "residential_plot": "Residential plot",
    "agricultural_land": "Agricultural land", "farmhouse": "Farmhouse / managed farmland", "plantation_estate": "Coffee / plantation estate",
    "industrial_land": "Industrial land", "commercial": "Commercial property", "other": "Other",
}
FINAL_DISCLAIMER = (
    "This report is based on the documents listed above as furnished to us and on records available on the date of this report. "
    "It is not a guarantee of title. Originals should be compared with these copies before registration."
)

_base = getSampleStyleSheet()
STYLES = {
    "firm": ParagraphStyle("firm", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=14, textColor=INK, leading=17),
    "firm_sub": ParagraphStyle("firm_sub", parent=_base["Normal"], fontSize=8.5, textColor=MUTED, leading=11),
    "title": ParagraphStyle("title", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=15, textColor=INK, alignment=TA_CENTER, spaceBefore=8, spaceAfter=10, leading=19),
    "h2": ParagraphStyle("h2", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=11, textColor=INK, spaceBefore=10, spaceAfter=4, leading=14),
    "body": ParagraphStyle("body", parent=_base["Normal"], fontSize=9.5, leading=13.5),
    "cell": ParagraphStyle("cell", parent=_base["Normal"], fontSize=8.5, leading=11),
    "cell_b": ParagraphStyle("cell_b", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11),
    "small": ParagraphStyle("small", parent=_base["Normal"], fontSize=8, textColor=MUTED, leading=10.5),
}

def _text(value: str | None, style: str = "body") -> Paragraph:
    # Paragraph takes a small XML markup; escape what lawyers type and keep their line breaks.
    return Paragraph(escape((value or "").strip()).replace("\n", "<br/>") or "&nbsp;", STYLES[style])

def _local(value: datetime) -> datetime:
    from .tickets import aware

    return aware(value).astimezone(ZoneInfo(config.MEETING_TIMEZONE))

def _date(value: datetime) -> str:
    return f"{_local(value).day} {_local(value):%B %Y}"

class _NumberedCanvas(canvas.Canvas):
    """Adds 'Page n of m' and the footer once the page count is known."""

    def __init__(self, *args, footer: str = "", initials: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []
        self._footer = footer
        self._initials = initials

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(MUTED)
            self.drawString(18 * mm, 10 * mm, self._footer)
            self.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {total}")
            if self._initials:
                # Advocates initial every page of the printed report.
                self.drawRightString(A4[0] - 18 * mm, 14.5 * mm, "Advocate's initials: ____________")
            super().showPage()
        super().save()

def _header(ticket: ServiceRequest, report: LegalReport, title: str, when: datetime) -> list:
    answers = ticket.structured_answers or {}
    prop = ticket.prop
    meta = [
        ("Ticket", ticket.ticket_number), ("Date", _date(when)),
        ("Client", answers.get("customer_name") or ticket.customer.full_name), ("Service", ticket.service_type.name + (f" ({ticket.package})" if ticket.package else "")),
        ("Property", PROPERTY_LABELS.get(prop.property_type, prop.property_type) if prop else "-"), ("Location", (prop.locality if prop else None) or "-"),
        ("Advocate", report.lawyer.display_name if report.lawyer else "-"), ("", ""),
    ]
    rows = [[_text(meta[i][0], "cell_b"), _text(meta[i][1], "cell"), _text(meta[i + 1][0], "cell_b"), _text(meta[i + 1][1], "cell")] for i in range(0, len(meta), 2)]
    table = Table(rows, colWidths=[22 * mm, 63 * mm, 22 * mm, 67 * mm])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f5f9")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return [
        _text(config.FIRM_NAME, "firm"), _text(config.FIRM_ADDRESS, "firm_sub"),
        Spacer(1, 4), _rule(), _text(title, "title"), table, Spacer(1, 6),
    ]

def _rule() -> Table:
    rule = Table([[""]], colWidths=[174 * mm], rowHeights=[1])
    rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, INK)]))
    return rule

def _sections(sections: tuple, values: dict) -> list:
    flow = []
    for section in report_templates.section_view(sections, values):
        if section["text"].strip():
            flow += [_text(section["heading"], "h2"), _text(section["text"])]
    return flow

def _grid(rows: list[list], widths: list[float]) -> Table:
    table = Table(rows, colWidths=[w * mm for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf3")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table

def _build(story: list, footer: str, initials: bool = False) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=22 * mm, title=footer, author=config.FIRM_NAME)
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer=footer, initials=initials, **k))
    return buffer.getvalue()

def preliminary_pdf(ticket: ServiceRequest, report: LegalReport) -> bytes:
    when = report.issued_at or report.updated_at
    story = _header(ticket, report, "Preliminary Legal Scrutiny Report", when)
    story += _sections(report_templates.PRELIMINARY_SECTIONS, report.preliminary)
    story.append(_text("Documents required", "h2"))
    rows = [[_text(h, "cell_b") for h in ("#", "Document", "Tag", "What to send", "Provided by", "Status")]]
    from .case_files import CUSTOMER_ITEM_LABELS

    for n, item in enumerate(report.items, 1):
        mark = "[x]" if item.status in ("verified", "waived") else "[  ]"
        label = CUSTOMER_ITEM_LABELS["fetching" if item.fetch_by == "homexo" and item.status == "pending" else item.status]
        who = "Homexo" if item.fetch_by == "homexo" else "You"
        rows.append([
            _text(str(n), "cell"), _text(item.label, "cell_b"), _text(f"#{item.tag}", "cell"),
            _text(item.guidance, "cell"), _text(who, "cell"), _text(f"{mark} {label}", "cell"),
        ])
    story.append(_grid(rows, [8, 42, 26, 46, 20, 32]))
    story += [
        Spacer(1, 8),
        _text(f"Upload each document on {config.PUBLIC_SITE_URL} under Track your request, using ticket {ticket.ticket_number} and the "
              "phone number or email you registered with. Pick the tag shown above for each file so it is linked to the checklist. "
              "Items provided by Homexo are public records we get from the government portals for you.", "small"),
    ]
    return _build(story, f"{config.FIRM_NAME} · Preliminary report · {ticket.ticket_number}")

def _signature_block(role: str, user: User | None, enrolment: str | None) -> Table:
    rows = [
        [_text(role, "cell_b")],
        [Spacer(1, 16 * mm)],
        [_text("Signature: ________________________________", "cell")],
        [_text(f"Name: {user.display_name}" if user else "Name: _____________________________", "cell")],
        [_text(f"Enrolment no.: {enrolment}" if enrolment else "Enrolment no.: _____________________", "cell")],
        [_text("Date: ______________   Place: ______________", "cell")],
        [_text("Seal:", "cell")],
        [Spacer(1, 18 * mm)],
    ]
    table = Table(rows, colWidths=[84 * mm])
    table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, INK), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    return table

def final_pdf(ticket: ServiceRequest, report: LegalReport, documents: list, enrolments: dict, generated_at: datetime) -> bytes:
    story = _header(ticket, report, "Legal Scrutiny Report", generated_at)
    preliminary = {k: v for k, v in (report.preliminary or {}).items() if k in ("property", "scope")}
    story += _sections(report_templates.PRELIMINARY_SECTIONS, preliminary)

    story.append(_text("Documents examined", "h2"))
    names: dict[str, list[str]] = {}
    for document in documents:
        if document.tag:
            names.setdefault(document.tag, []).append(document.original_filename)
    rows = [[_text(h, "cell_b") for h in ("#", "Document", "Tag", "Files examined", "Result")]]
    for n, item in enumerate(report.items, 1):
        result = "Verified" if item.status == "verified" else "Not applicable"
        if item.review_note:
            result += f": {item.review_note}"
        rows.append([
            _text(str(n), "cell"), _text(item.label, "cell_b"), _text(f"#{item.tag}", "cell"),
            _text("\n".join(names.get(item.tag, [])) or "-", "cell"), _text(result, "cell"),
        ])
    story.append(_grid(rows, [8, 46, 28, 54, 38]))

    story += _sections(report_templates.FINAL_SECTIONS, report.final)
    story += [Spacer(1, 6), _text(FINAL_DISCLAIMER, "small"), Spacer(1, 10)]

    blocks = Table(
        [[_signature_block("Advocate", report.lawyer, enrolments.get(report.lawyer_user_id)),
          _signature_block("Reviewing advocate", report.reviewer, enrolments.get(report.reviewer_user_id))]],
        colWidths=[87 * mm, 87 * mm],
    )
    blocks.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether([_text("Signed by", "h2"), blocks]))
    return _build(story, f"{config.FIRM_NAME} · Final report · {ticket.ticket_number} · generated {_date(generated_at)}", initials=True)
