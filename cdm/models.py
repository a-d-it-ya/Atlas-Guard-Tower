"""
HiveOS Common Data Model (CDM) — Data Contracts
Defines standardized schemas for edge events, geotags, system telemetry,
and compact serialization formats for LoRa mesh transmission.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
import json
import uuid
from typing import Optional, Dict, Any


class ThreatType(str, Enum):
    HUMAN_INTRUSION = "HUMAN_INTRUSION"
    VEHICLE = "VEHICLE"
    UNVERIFIED_MOTION = "UNVERIFIED_MOTION"
    PERIMETER_BREACH = "PERIMETER_BREACH"


class VerificationSource(str, Enum):
    RADAR_ONLY = "RADAR_ONLY"
    VISION_VERIFIED = "VISION_VERIFIED"
    MULTI_SENSOR_FUSED = "MULTI_SENSOR_FUSED"


class PacketType(str, Enum):
    ALERT = "ALERT"
    HEARTBEAT = "HEARTBEAT"
    COMMAND = "COMMAND"
    ACK = "ACK"


@dataclass
class GeoCoordinate:
    """Geographic position tagged by u-blox NEO-6M GPS."""
    latitude: float
    longitude: float
    altitude_m: float = 0.0
    satellites: int = 0
    hdop: float = 1.0
    fix_valid: bool = False
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_compact_str(self) -> str:
        """Format as compact string for low-bandwidth LoRa payloads."""
        return f"{self.latitude:.6f},{self.longitude:.6f},{self.altitude_m:.1f}m,{self.satellites}sats"


@dataclass
class BoundingBox:
    """Normalized bounding box coordinates of visual detection (0.0 to 1.0)."""
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    confidence: float
    label: str = "person"

    @property
    def center_x(self) -> float:
        return (self.xmin + self.xmax) / 2.0

    @property
    def center_y(self) -> float:
        return (self.ymin + self.ymax) / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.xmax - self.xmin) * max(0.0, self.ymax - self.ymin)


@dataclass
class ThreatClassification:
    """Target classification and verification confidence metadata."""
    threat_type: ThreatType
    confidence: float
    verification_source: VerificationSource
    detections_count: int = 1


@dataclass
class SystemHealth:
    """Sentry node operational and power telemetry."""
    battery_voltage: float = 12.4          # Volts (e.g. 12V LiFePO4 / 3S Li-ion)
    solar_voltage: float = 18.2            # Volts (Solar panel input)
    cpu_temperature_c: float = 48.5        # Celsius (RPi 4B SoC thermal zone)
    memory_usage_pct: float = 34.2         # RAM utilization
    uptime_seconds: int = 0                # Process uptime


@dataclass
class ThreatEvent:
    """
    High-priority intrusion alert sent to HiveOS C2 when a threat is verified.
    """
    node_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    threat: ThreatClassification = field(
        default_factory=lambda: ThreatClassification(
            threat_type=ThreatType.HUMAN_INTRUSION,
            confidence=0.0,
            verification_source=VerificationSource.MULTI_SENSOR_FUSED
        )
    )
    location: Optional[GeoCoordinate] = None
    bbox: Optional[BoundingBox] = None
    requires_operator_ack: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    def to_compact_mesh_payload(self) -> str:
        """
        Generates an ultra-compact payload optimized for LoRa 237-byte MTU limit.
        Format: [AGT:ALERT|<event_id>|<node_id>|<lat>,<lon>|<type>|<conf%>|<source>]
        """
        loc_str = f"{self.location.latitude:.5f},{self.location.longitude:.5f}" if self.location else "0.0,0.0"
        conf_pct = int(self.threat.confidence * 100)
        return (
            f"[AGT:ALERT|ID:{self.event_id}|N:{self.node_id}|LOC:{loc_str}|"
            f"T:{self.threat.threat_type.value}|C:{conf_pct}%|SRC:{self.threat.verification_source.value}]"
        )


@dataclass
class HeartbeatTelemetry:
    """
    Periodic routine telemetry packet broadcasting sentry health to HiveOS.
    """
    node_id: str
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    location: Optional[GeoCoordinate] = None
    health: SystemHealth = field(default_factory=SystemHealth)
    packets_sent_total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    def to_compact_mesh_payload(self) -> str:
        """
        Compact telemetry payload for LoRa.
        Format: [AGT:HEARTBEAT|<node_id>|<lat>,<lon>|B:<batt>V|S:<solar>V|CPU:<temp>C|UP:<uptime>s]
        """
        loc_str = f"{self.location.latitude:.5f},{self.location.longitude:.5f}" if self.location else "0.0,0.0"
        return (
            f"[AGT:BEACON|N:{self.node_id}|LOC:{loc_str}|"
            f"BAT:{self.health.battery_voltage:.1f}V|SOL:{self.health.solar_voltage:.1f}V|"
            f"CPU:{self.health.cpu_temperature_c:.1f}C|UP:{self.health.uptime_seconds}s]"
        )


@dataclass
class MeshPacket:
    """Wrapper for all outgoing LoRa Meshtastic transmissions."""
    packet_type: PacketType
    sender_node_id: str
    sequence_number: int
    payload_str: str
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
