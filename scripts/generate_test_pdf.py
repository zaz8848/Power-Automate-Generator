"""Generate Tech Knowledge Base PDF for V5 testing.

Creates a PDF with sample tech support articles that can be uploaded
to Dataverse Knowledge Base for the Tech Assistance Agent to search.
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

output = r'd:\A_Code\Automate Generator\tests\v5\knowledge\tech-knowledge-base.pdf'

styles = getSampleStyleSheet()
title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=22, textColor=HexColor('#0078D4'), spaceAfter=20)
h1_style = ParagraphStyle('H1', parent=styles['Heading1'], fontSize=16, textColor=HexColor('#0078D4'), spaceAfter=10)
h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, textColor=HexColor('#333333'), spaceAfter=8)
body_style = ParagraphStyle('Body', parent=styles['BodyText'], fontSize=10, leading=14, spaceAfter=6)
code_style = ParagraphStyle('Code', parent=styles['Code'], fontSize=9, leading=12, leftIndent=12, textColor=HexColor('#555555'), backColor=HexColor('#f5f5f5'))
meta_style = ParagraphStyle('Meta', parent=styles['BodyText'], fontSize=9, textColor=HexColor('#888888'), spaceAfter=4)

doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=0.6*inch, leftMargin=0.6*inch, topMargin=0.6*inch, bottomMargin=0.6*inch)
story = []

# ============================================================
# Cover
# ============================================================
story.append(Paragraph("Contoso Technical Support<br/>Knowledge Base", title_style))
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("Version 1.0 · 2026-06-04", meta_style))
story.append(Paragraph("Purpose: This PDF is uploaded to Dataverse Knowledge Article entity to enable the Tech Assistance Agent in [AutoGen] Service Email Workflow v5 to retrieve solutions via Dataverse MCP.", body_style))
story.append(Spacer(1, 0.3*inch))

# Table of contents
toc_data = [
    ['ID', 'Article Title', 'Tags'],
    ['KB-001', 'How to factory reset Contoso Smart Hub', 'firmware, reset, IoT'],
    ['KB-002', 'Mobile app sync errors troubleshooting', 'mobile, sync, HTTP 503'],
    ['KB-003', 'Espresso Maker - heating element issues', 'coffee, defective, hardware'],
    ['KB-004', 'Surface Laptop battery drain diagnosis', 'laptop, battery, performance'],
    ['KB-005', 'WiFi connectivity issues - common fixes', 'network, wifi, connectivity'],
]
t = Table(toc_data, colWidths=[0.8*inch, 4.0*inch, 2.0*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#0078D4')),
    ('TEXTCOLOR', (0,0), (-1,0), HexColor('#FFFFFF')),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,-1), 9),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#CCCCCC')),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('PADDING', (0,0), (-1,-1), 6),
]))
story.append(t)
story.append(PageBreak())

# ============================================================
# Article 1
# ============================================================
story.append(Paragraph("KB-001: How to factory reset Contoso Smart Hub", h1_style))
story.append(Paragraph("Tags: firmware, reset, IoT, Smart Hub | Updated: 2026-06-04", meta_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Symptoms", h2_style))
story.append(Paragraph("Device keeps rebooting every few minutes after firmware update. Power cycling and WiFi reset do not fix the issue.", body_style))

story.append(Paragraph("Cause", h2_style))
story.append(Paragraph("Firmware corruption during OTA update can cause boot loops. The device cannot apply rollback automatically without a hardware reset.", body_style))

story.append(Paragraph("Resolution", h2_style))
story.append(Paragraph("Perform a full factory reset and reinstall stable firmware:", body_style))
story.append(Paragraph("1. <b>Unplug the device</b> from power for 60 seconds (not 30).", body_style))
story.append(Paragraph("2. While unplugged, hold the <b>Reset button</b> (small hole on the back) with a paperclip.", body_style))
story.append(Paragraph("3. While holding Reset, plug the device back in. Keep holding for <b>15 seconds</b>.", body_style))
story.append(Paragraph("4. The LED will flash red-white-red, then turn solid white. Release the button.", body_style))
story.append(Paragraph("5. The device is now in <b>Recovery Mode</b>. Open the Contoso Hub app and tap <i>Add Device → Recovery Mode</i>.", body_style))
story.append(Paragraph("6. The app will detect the device and offer firmware versions. Choose <b>Stable v4.0.5</b> (do not pick 4.2.x).", body_style))
story.append(Paragraph("7. Wait ~5 minutes for firmware to flash. Do NOT unplug during this step.", body_style))
story.append(Paragraph("8. After completion, reconfigure WiFi and re-pair accessories.", body_style))

story.append(Paragraph("Prevention", h2_style))
story.append(Paragraph("Disable automatic firmware updates in <i>Hub Settings → Advanced → Auto Update</i> until v4.3 is released.", body_style))
story.append(PageBreak())

# ============================================================
# Article 2
# ============================================================
story.append(Paragraph("KB-002: Mobile app sync errors troubleshooting", h1_style))
story.append(Paragraph("Tags: mobile, sync, HTTP 503, iOS, Android | Updated: 2026-06-04", meta_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Symptoms", h2_style))
story.append(Paragraph("Mobile app shows 'Sync failed: HTTP 503' or 'service temporarily unavailable'. Sync may work intermittently.", body_style))

story.append(Paragraph("Likely Causes", h2_style))
story.append(Paragraph("• Backend rate limiting triggered by large account history sync.<br/>• Mobile app cached an expired auth token.<br/>• Regional backend instance under maintenance.", body_style))

story.append(Paragraph("Resolution Steps", h2_style))
story.append(Paragraph("1. Force quit the app (swipe up on iOS, recent apps on Android).", body_style))
story.append(Paragraph("2. Open the app and go to <i>Settings → Account → Sign out</i>.", body_style))
story.append(Paragraph("3. Restart the device.", body_style))
story.append(Paragraph("4. Sign in again. The app will request a fresh auth token.", body_style))
story.append(Paragraph("5. Go to <i>Settings → Data → Force Full Sync</i>. This may take 5-15 minutes.", body_style))
story.append(Paragraph("6. If still failing, check status page <b>status.contoso.com</b> for regional outages.", body_style))

story.append(Paragraph("Escalation", h2_style))
story.append(Paragraph("If error persists after the above steps, escalate to L2 with: device model, OS version, app version, account ID, and timestamp of last successful sync.", body_style))
story.append(PageBreak())

# ============================================================
# Article 3
# ============================================================
story.append(Paragraph("KB-003: Espresso Maker - heating element issues", h1_style))
story.append(Paragraph("Tags: coffee, defective, hardware, espresso | Updated: 2026-06-04", meta_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Symptoms", h2_style))
story.append(Paragraph("Premium Espresso Maker does not heat water, water comes out lukewarm, or the heating indicator never turns green.", body_style))

story.append(Paragraph("Self-Diagnosis", h2_style))
story.append(Paragraph("1. Confirm the unit is plugged into a 120V outlet (not an extension cord).", body_style))
story.append(Paragraph("2. Check the water tank is filled above the MIN line.", body_style))
story.append(Paragraph("3. Press and hold the power button for 5 seconds to trigger self-test. Listen for pump activation.", body_style))
story.append(Paragraph("4. If pump runs but water stays cold for &gt;90 seconds, the heating element is likely defective.", body_style))

story.append(Paragraph("Resolution", h2_style))
story.append(Paragraph("Defective heating element is covered under the 2-year warranty. Customers should be directed to <b>initiate a return</b> through customer service. Refund is approved when:", body_style))
story.append(Paragraph("• Days since purchase ≤ 7: <b>Auto-approved</b>, no manual review needed.<br/>• Days since purchase &gt; 7 OR order amount ≥ $200: <b>Pending review</b> by returns team.", body_style))
story.append(PageBreak())

# ============================================================
# Article 4
# ============================================================
story.append(Paragraph("KB-004: Surface Laptop battery drain diagnosis", h1_style))
story.append(Paragraph("Tags: laptop, battery, performance, Surface | Updated: 2026-06-04", meta_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Symptoms", h2_style))
story.append(Paragraph("Surface Laptop 7 battery lasts &lt; 4 hours despite 10-hour advertised lifespan. Battery drains rapidly even in standby.", body_style))

story.append(Paragraph("Diagnostic Steps", h2_style))
story.append(Paragraph("1. Run Windows <b>Battery Report</b>: open PowerShell as admin, run <i>powercfg /batteryreport /output \"battery.html\"</i>", body_style))
story.append(Paragraph("2. Review the Design Capacity vs Full Charge Capacity. If &lt; 80% of design, battery is degraded.", body_style))
story.append(Paragraph("3. Check Background Apps in Task Manager. High-power apps drain battery in standby.", body_style))
story.append(Paragraph("4. Update graphics drivers from Surface Diagnostic Toolkit (powerful drivers can save 20-30%).", body_style))

story.append(Paragraph("Resolution Path", h2_style))
story.append(Paragraph("If the battery report confirms degradation &gt; 20% below design capacity within first 90 days, the customer qualifies for a free battery replacement under warranty. Direct to Surface Service portal: surface.contoso.com/service", body_style))
story.append(PageBreak())

# ============================================================
# Article 5
# ============================================================
story.append(Paragraph("KB-005: WiFi connectivity issues - common fixes", h1_style))
story.append(Paragraph("Tags: network, wifi, connectivity | Updated: 2026-06-04", meta_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("Symptoms", h2_style))
story.append(Paragraph("Device frequently drops WiFi, slow speeds despite good signal, or fails to connect to known networks.", body_style))

story.append(Paragraph("Standard Fix Sequence", h2_style))
story.append(Paragraph("1. <b>Forget and re-add</b> the network on the device.", body_style))
story.append(Paragraph("2. <b>Restart router</b>: unplug for 60 seconds.", body_style))
story.append(Paragraph("3. <b>Change WiFi channel</b> on router: 2.4GHz channel 1/6/11; 5GHz channel 36/40/44/48.", body_style))
story.append(Paragraph("4. <b>Update firmware</b> on router and device.", body_style))
story.append(Paragraph("5. <b>Check for interference</b>: microwaves, Bluetooth speakers, neighbor APs on same channel.", body_style))

story.append(Paragraph("When to Escalate", h2_style))
story.append(Paragraph("If above steps don't help, collect: ISP name, modem model, router model, device model, signal strength dBm, and submit ticket to network L2.", body_style))

# ============================================================
# Footer page
# ============================================================
story.append(Spacer(1, 0.5*inch))
story.append(Paragraph("---", body_style))
story.append(Paragraph("<b>Document Information</b>", h2_style))
story.append(Paragraph("Source: Contoso Technical Support Knowledge Base", body_style))
story.append(Paragraph("Audience: Tech Assistance Agent (AI), L1 support staff", body_style))
story.append(Paragraph("Upload Target: Dataverse Knowledge Article entity (JiaqiDev environment)", body_style))
story.append(Paragraph("Generated: 2026-06-04 for [AutoGen] Service Email Workflow v5 testing", body_style))

doc.build(story)
print(f"PDF generated: {output}")
import os
print(f"Size: {os.path.getsize(output)} bytes")
