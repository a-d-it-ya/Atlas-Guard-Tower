# Atlas Guard Tower (AGT) — Autonomous Edge AI Sentry Node

**Atlas Guard Tower (AGT)** is an edge sentry and sensor fusion node for perimeter surveillance and border defense. It operates as the deployable hardware counterpart to **HiveOS**, a Command and Control (C2) software platform modeled conceptually on defense-tech multi-domain operating architectures (such as Anduril's Lattice).

AGT runs onboard sensor fusion, class-restricted computer vision, and geo-tagging, dispatching structured alerts over long-range **LoRa mesh networks** (868 MHz / IN_865 band).

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Hardware_Node ["Atlas Guard Tower (AGT) Edge Unit"]
        Radar["RCWL-0516 Microwave Radar"] -->|GPIO 17 Rising Edge| Engine["Sentry Fusion Engine"]
        CamWorker["V4L2 Camera Grabber (Threaded)"] -->|Fresh Frame Stream| Vision["YOLOv8 Edge AI (Class 0 = Person)"]
        Vision -->|Human Confirmed >= 55%| Engine
        GPS["u-blox NEO-6M GPS"] -->|UART /dev/serial0 (pynmea2)| Engine
        Health["System Telemetry (Battery / CPU)"] -->|Periodic Sample| Telemetry["Telemetry Worker"]

        Engine -->|Stage 4: Packaged CDM Alert| CDM["HiveOS Common Data Model (JSON / Binary)"]
        Telemetry -->|Periodic Beacon| CDM
        CDM -->|Protobuf RPC via USB-CDC| Heltec["Heltec LoRa32 V3 (Meshtastic Firmware)"]
    end

    subgraph Mesh_Network ["LoRa Multi-Hop Mesh (IN_865 / 868 MHz)"]
        Heltec -->|RF Broadcast| Sentry2["Neighboring AGT Sentry Node"]
        Sentry2 -->|Relayed RF| Gateway["Base Station LoRa Gateway"]
    end

    subgraph C2_Platform ["HiveOS Command & Control Platform"]
        Gateway --> Ingestion["CDM Ingestion & World Model"]
        Ingestion --> Operator["Operator C2 UI (Human-in-the-Loop Response)"]
    end
```

---

## 2. Multi-Stage Gated Fusion Pipeline

To maximize battery life and prevent false alarms in remote perimeter deployments, AGT uses a **4-stage gated pipeline**:

1. **Stage 1 — Passive Microwave Radar (Low Power):** The RCWL-0516 Doppler radar continuously monitors the perimeter at near-zero power draw. When a physical presence crosses the microwave field, it generates a hardware GPIO interrupt (`GPIO.RISING`).
2. **Stage 2 — Active Edge AI Vision Verification:** The interrupt wakes the camera worker. The node samples 5 consecutive frames through an optimized YOLOv8n / OpenCV pipeline filtered strictly for `person` (Class 0). If the confidence exceeds threshold ($\ge 55\%$) across at least 2 frames, the threat is confirmed. If it was leaves, wind, or an animal, the event is immediately discarded as a false alarm.
3. **Stage 3 — GPS Geotagging:** The node queries the latest valid coordinates, altitude, and satellite fix from the u-blox NEO-6M receiver.
4. **Stage 4 — CDM Packaging & LoRa Mesh Dispatch:** The event is serialized into the HiveOS Common Data Model (`ThreatEvent`) and transmitted across the LoRa mesh via the Heltec LoRa32 V3 transceiver.

---

## 3. Physical Hardware Wiring & Pinout

### A. Raspberry Pi 4B GPIO Pin Header (40-Pin)

| Component | Component Pin | Raspberry Pi 4B Pin | Physical Pin # | Function |
| :--- | :--- | :--- | :--- | :--- |
| **RCWL-0516 Radar** | `VIN` | 5V Power | Pin 2 | Power input |
| | `GND` | Ground | Pin 6 | System Ground |
| | `OUT` | GPIO 17 | Pin 11 | Digital Motion Interrupt |
| **u-blox NEO-6M GPS** | `VCC` | 3.3V / 5V | Pin 1 or 4 | Power input |
| | `GND` | Ground | Pin 9 | System Ground |
| | `TX` (GPS Out) | GPIO 15 (RXD0) | Pin 10 | Serial Receive *(Cross-over)* |
| | `RX` (GPS In) | GPIO 14 (TXD0) | Pin 8 | Serial Transmit *(Cross-over)* |
| **Heltec LoRa32 V3** | `USB-C` | USB 3.0 Port | USB Port | USB-CDC Serial (/dev/ttyUSB0) |
| **Camera** | `USB / CSI` | USB / CSI Ribbon | USB / CSI Port | Video4Linux2 (/dev/video0) |

---

## 4. Interview Technical Deep-Dive Q&A

### Q1: How did you integrate the camera into the Raspberry Pi for detection?
> **Answer:**
> * **Hardware/Driver Interface:** Connected a camera via USB / CSI ribbon cable. Linux automatically initializes it under the **Video4Linux2 (V4L2)** subsystem at `/dev/video0`.
> * **Latency & Buffer Elimination:** Standard `cv2.VideoCapture` on Linux has an internal OS buffer that causes multi-second video lag on embedded systems. To solve this, I designed a dedicated background `ThreadedCameraWorker` that continuously drains the buffer (`cv2.CAP_PROP_BUFFERSIZE=1`), guaranteeing that when an intrusion trigger occurs, the Edge AI pipeline immediately accesses the freshest real-time frame without stale cache.
> * **Class Restriction:** The inference engine strictly checks for COCO class index `0` (`person`) with a confidence threshold $\ge 0.55$, ignoring other classes to optimize processing time and memory bandwidth.

### Q2: Which GPS sensor did you use and which library in Raspberry Pi did you use to integrate it?
> **Answer:**
> * **Sensor:** **u-blox NEO-6M GPS module** connected to the Pi's hardware UART (GPIO 14 TX / GPIO 15 RX).
> * **Linux OS Setup:** 
>   1. Enabled hardware UART in `/boot/firmware/config.txt` (`enable_uart=1`).
>   2. Disabled the Linux Serial Console login shell in `/boot/firmware/cmdline.txt` (removed `console=serial0,115200`), dedicating `/dev/serial0` exclusively to the GPS stream.
> * **Python Integration:** Used **`pyserial`** to read the 9600-baud serial stream and **`pynmea2`** to parse NMEA-0183 sentences:
>   - `$GPGGA`: Latitude, Longitude, Altitude, Satellites in view, and Fix Quality.
>   - `$GPRMC`: Timestamp, Ground speed, and Active fix status flag (`A` vs `V`).
> * Stored coordinates in a thread-safe cache updated in the background.

### Q3: How did you integrate Raspberry Pi data with Heltec LoRa32 running stock Meshtastic firmware?
> **Answer:**
> * **Interconnect:** Connected Heltec LoRa32 V3 to the Raspberry Pi over a USB-C data cable (`/dev/ttyUSB0`).
> * **Protocol:** Stock Meshtastic firmware exposes a **Protocol Buffers (Protobuf) RPC API** over its USB-serial interface.
> * **Integration:** Used the official **`meshtastic` Python SDK** (`meshtastic.serial_interface.SerialInterface`).
> * When an alert or telemetry beacon is ready, the Python application calls `interface.sendText(text=payload, destinationId="^all", channelIndex=0, wantAck=True)`.
> * **What Heltec Handles:** The Meshtastic firmware parses the Protobuf command, encrypts the payload with the pre-shared channel key (AES-256), packages it with mesh headers (hop limit, packet ID), and transmits it over the **868 MHz / IN_865** band via its onboard SX1262 LoRa transceiver. Surrounding mesh sentry nodes relay it multi-hop to the base station.

---

## 5. Running the Application

### A. Simulation / Interview Demo Mode (Run on Laptop / PC)
No physical hardware or Raspberry Pi required. Simulates the entire pipeline with synthetic GPS drift, simulated microwave presence interrupts, and visual LoRa mesh transmission logs:

```bash
# Interactive terminal mode (Press Enter to trigger microwave motion)
python main.py --sim --interactive

# Automated periodic trigger mode (Triggers every 15 seconds)
python main.py --sim --auto-trigger 15.0
```

### B. Live Hardware Mode (Run on Raspberry Pi 4B)
```bash
python main.py
```

### C. Running Automated Tests
```bash
pytest tests/test_pipeline.py -v
```

---

## 6. Project Structure

```
atlas_guard_tower/
├── config.py                 # Hardware pinouts, radio frequency band, timings, and thresholds
├── cdm/
│   ├── __init__.py
│   └── models.py             # HiveOS Common Data Model (GeoTag, ThreatEvent, Telemetry, LoRa Packet)
├── drivers/
│   ├── __init__.py
│   ├── base.py               # Hardware Abstraction Layer (HAL) base interfaces
│   ├── radar_rcwl0516.py     # RCWL-0516 Doppler radar GPIO interrupt driver + Mock
│   ├── gps_neo6m.py          # u-blox NEO-6M UART reader with pynmea2 parser + Mock
│   ├── vision_detector.py    # Threaded V4L2 camera grabber + class-restricted human detector + Mock
│   └── lora_meshtastic.py    # Heltec LoRa32 V3 Meshtastic Protobuf serial driver + Mock
├── core/
│   ├── __init__.py
│   ├── fusion_engine.py      # 4-Stage Gated Sensor Fusion Orchestrator
│   └── telemetry.py          # Periodic node health & battery telemetry beacon worker
├── main.py                   # Main CLI entry point with live dashboard & simulation flags
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py      # Full unit and integration test suite
├── requirements.txt          # Python dependencies
└── README.md                 # Complete system documentation & interview master guide
```
