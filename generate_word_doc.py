"""
Script to generate a formatted Word Document (.docx) for Atlas Guard Tower Interview Guide.
Creates standard OpenXML .docx format natively without external heavy dependencies.
"""

import os
import zipfile
from xml.sax.saxutils import escape


def create_docx(output_path: str):
    # Word XML Document Template
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    # Questions and structured content
    sections = [
        ("ATLAS GUARD TOWER (AGT) — INTERVIEW MASTER GUIDE", "title"),
        ("Defense-Tech Edge AI Perimeter Surveillance & LoRa Mesh Sensor Node", "subtitle"),
        
        ("1. CORE TECHNICAL IMPLEMENTATION QUESTIONS", "h1"),
        
        ("Q1: How did you physically attach and code the web camera on the Raspberry Pi?", "h2"),
        ("Answer & Architecture:", "bold"),
        ("• Hardware Interface: Connected via high-speed USB 3.0 port (or MIPI-CSI 15-pin ribbon cable). The Linux kernel enumerates the camera under the Video4Linux2 (V4L2) subsystem at /dev/video0.", "bullet"),
        ("• Frame Buffer Lag Elimination: Standard cv2.VideoCapture on Linux queues 4-5 frames in an OS buffer, causing multi-second delay on embedded devices. We resolved this by implementing a dedicated ThreadedCameraWorker in Python that runs in the background, sets cv2.CAP_PROP_BUFFERSIZE=1, and continuously drains the buffer. When an interrupt arrives, the AI pipeline immediately gets the latest instantaneous frame.", "bullet"),
        ("• Python Code Used: Uses cv2.VideoCapture(0, cv2.CAP_V4L2) with a thread-safe get_latest_frame() lock mechanism.", "bullet"),
        
        ("Q2: Since YOLO detects 80 COCO classes, how did you filter exclusively for humans?", "h2"),
        ("Answer & Logic:", "bold"),
        ("• Target Class Gating: Filtered results strictly for COCO Class ID 0 (which corresponds to 'person'). All other 79 classes (cars, animals, chairs, etc.) are ignored.", "bullet"),
        ("• Confidence & Gating: Implemented a confidence threshold (>= 0.55) and multi-frame temporal confirmation. When the microwave radar triggers, the node evaluates 5 consecutive frames. If at least 2 frames confirm human presence, the threat is verified. Transient noise, birds, or blowing leaves are filtered out as false alarms.", "bullet"),
        
        ("Q3: How did you integrate Raspberry Pi data with Heltec LoRa32 running stock Meshtastic firmware?", "h2"),
        ("Answer & Networking:", "bold"),
        ("• Interconnect: Heltec LoRa32 V3 is connected to the Pi via USB-C to USB-A (/dev/ttyUSB0).", "bullet"),
        ("• Communication Protocol: Stock Meshtastic firmware exposes a standardized Protocol Buffers (Protobuf) RPC API over USB-serial. No firmware modification is needed.", "bullet"),
        ("• Python SDK: We use the official 'meshtastic' Python library (meshtastic.serial_interface.SerialInterface). The Pi calls interface.sendText(payload, destinationId='^all', channelIndex=0, wantAck=True).", "bullet"),
        ("• What the Heltec Handles: The ESP32-S3 and SX1262 transceiver handle AES-256 encryption, LoRa framing, RF modulation over 868 MHz / IN_865 band, and multi-hop mesh routing.", "bullet"),
        
        ("Q4: Which GPS sensor did you use and which library on Raspberry Pi parsed the data?", "h2"),
        ("Answer & Serial Setup:", "bold"),
        ("• Hardware: u-blox NEO-6M GPS receiver connected to Hardware UART pins (GPIO 14 TX -> GPS RX, GPIO 15 RX -> GPS TX).", "bullet"),
        ("• Linux OS Configuration: Enabled UART in /boot/firmware/config.txt (enable_uart=1) and removed the Linux serial login console from /boot/firmware/cmdline.txt (removed console=serial0,115200) to dedicate /dev/serial0 exclusively to GPS.", "bullet"),
        ("• Python Libraries: Used 'pyserial' at 9600 baud and 'pynmea2' to parse $GPGGA (coordinates, altitude, satellites) and $GPRMC (validity flag 'A' vs 'V', UTC timestamp).", "bullet"),

        ("2. LINUX OS STARTUP & FIELD RELIABILITY", "h1"),
        
        ("Q5: How do you make the program auto-start when the Raspberry Pi powers on in the field?", "h2"),
        ("Answer: Created a systemd unit service (/etc/systemd/system/agt-sentry.service) with 'Restart=always' and 'WantedBy=multi-user.target', enabled via 'sudo systemctl enable agt-sentry.service'.", "bullet"),
        
        ("Q6: How do you prevent SD card corruption if solar battery power dies abruptly?", "h2"),
        ("Answer: Enabled Linux Read-Only Root Filesystem (OverlayFS) using raspi-config. Temporary buffers and logs are written to RAM (tmpfs).", "bullet"),

        ("3. SENSOR FUSION & C2 PLATFORM (HIVEOS)", "h1"),
        
        ("Q7: What is the 4-stage gated pipeline architecture?", "h2"),
        ("Answer: Stage 1 (Passive Radar: RCWL-0516 Doppler interrupt) -> Stage 2 (Active AI: YOLOv8n 5-frame human check) -> Stage 3 (Geotagging: NEO-6M GPS) -> Stage 4 (LoRa Mesh Dispatch: HiveOS CDM format via Heltec LoRa32).", "bullet"),
        
        ("Q8: What is the Common Data Model (CDM) and HiveOS?", "h2"),
        ("Answer: Modeled conceptually on defense systems like Anduril's Lattice, the Common Data Model is a unified data schema (ThreatEvent) for tracks and alerts. HiveOS ingests these tracks for operator visualization. Crucially, a Human-in-the-Loop authorizes any response.", "bullet"),
    ]

    # Generate document.xml
    body_xml = []
    for text, style in sections:
        clean_text = escape(text)
        if style == "title":
            p = f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="120"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="44"/><w:color w:val="1F497D"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        elif style == "subtitle":
            p = f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="300"/></w:pPr><w:r><w:rPr><w:i/><w:sz w:val="24"/><w:color w:val="595959"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        elif style == "h1":
            p = f'<w:p><w:pPr><w:spacing w:before="300" w:after="120"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="1F497D"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        elif style == "h2":
            p = f'<w:p><w:pPr><w:spacing w:before="200" w:after="80"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="2E75B6"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        elif style == "bold":
            p = f'<w:p><w:pPr><w:spacing w:before="80" w:after="40"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="22"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        elif style == "bullet":
            p = f'<w:p><w:pPr><w:ind w:left="400"/><w:spacing w:after="80"/></w:pPr><w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        else:
            p = f'<w:p><w:pPr><w:spacing w:after="100"/></w:pPr><w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t>{clean_text}</w:t></w:r></w:p>'
        body_xml.append(p)

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        {''.join(body_xml)}
        <w:sectPr>
            <w:pgSz w:w="12240" w:h="15840"/>
            <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
        </w:sectPr>
    </w:body>
</w:document>"""

    # Package as ZIP (.docx format)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml)
        docx.writestr("_rels/.rels", rels_xml)
        docx.writestr("word/document.xml", document_xml)

    print(f"Successfully generated: {output_path}")


if __name__ == "__main__":
    out_file = os.path.join(
        os.path.dirname(__file__),
        "Atlas_Guard_Tower_Interview_Master_Guide.docx"
    )
    create_docx(out_file)
