"""Création de bulletins PDF météo."""
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def create_pdf_report(city: str, forecast: dict, air: dict | None, destination: str) -> None:
    doc = SimpleDocTemplate(destination, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                            topMargin=16*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER,
                              textColor=colors.HexColor("#243b70")))
    story = [Paragraph("Bulletin météorologique", styles["ReportTitle"]),
             Paragraph(f"<b>{city}</b> · Généré le {datetime.now():%d/%m/%Y à %H:%M}", styles["Normal"]),
             Spacer(1, 8*mm), Paragraph("Conditions actuelles", styles["Heading2"])]
    current = forecast.get("current", {})
    story.append(Paragraph(f"Température : {current.get('temperature_2m','—')} °C · "
        f"Ressenti : {current.get('apparent_temperature','—')} °C · Vent : {current.get('wind_speed_10m','—')} km/h · "
        f"Humidité : {current.get('relative_humidity_2m','—')} %", styles["BodyText"]))
    story += [Spacer(1, 5*mm), Paragraph("Prévisions sur 7 jours", styles["Heading2"])]
    daily = forecast.get("daily", {})
    rows = [["Date","Min.","Max.","Pluie max.","Vent max.","UV max."]]
    count = min(7, len(daily.get("time", [])))
    for i in range(count):
        rows.append([daily["time"][i], f"{daily.get('temperature_2m_min',['—']*count)[i]} °C",
            f"{daily.get('temperature_2m_max',['—']*count)[i]} °C",
            f"{daily.get('precipitation_probability_max',['—']*count)[i]} %",
            f"{daily.get('wind_speed_10m_max',['—']*count)[i]} km/h",
            daily.get("uv_index_max",['—']*count)[i]])
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#243b70")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cbd2e0")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f1f4f9")]),
        ("PADDING",(0,0),(-1,-1),6)]))
    story += [table, Spacer(1, 6*mm), Paragraph("Qualité de l'air", styles["Heading2"])]
    if air and isinstance(air.get("current"), dict):
        a = air["current"]
        story.append(Paragraph(f"Indice européen : {a.get('european_aqi','—')} · PM2.5 : {a.get('pm2_5','—')} µg/m³ · "
            f"PM10 : {a.get('pm10','—')} µg/m³ · NO₂ : {a.get('nitrogen_dioxide','—')} µg/m³ · "
            f"Ozone : {a.get('ozone','—')} µg/m³", styles["BodyText"]))
    else:
        story.append(Paragraph("Données non disponibles.", styles["BodyText"]))
    story += [Spacer(1, 8*mm), Paragraph("Source : Open-Meteo. Prévisions indicatives, susceptibles d'évoluer.",
                                        styles["Italic"])]
    doc.build(story)
