"""
Atlas Guard Tower (AGT) — Test Suite
Validates Common Data Model (CDM) serialization, GPS parsing, multi-stage
sensor fusion gating, false-positive filtering, and LoRa mesh packet creation.
"""

import time
import pytest
from ..config import SentryNodeConfig, RadarConfig, VisionConfig, GPSConfig, LoRaMeshConfig
from ..cdm.models import (
    GeoCoordinate,
    BoundingBox,
    ThreatClassification,
    ThreatType,
    VerificationSource,
    ThreatEvent,
    HeartbeatTelemetry,
    SystemHealth,
)
from ..drivers.radar_rcwl0516 import MockRadarSensor
from ..drivers.gps_neo6m import MockGPSReader, GPSReader
from ..drivers.vision_detector import MockVisionDetector
from ..drivers.lora_meshtastic import MockLoRaTransmitter
from ..core.fusion_engine import SentryFusionEngine
from ..core.telemetry import TelemetryWorker


class TestCommonDataModel:
    """Tests for HiveOS Common Data Model (CDM) contracts."""

    def test_geo_coordinate_compact_formatting(self):
        coord = GeoCoordinate(
            latitude=17.385044,
            longitude=78.486671,
            altitude_m=542.0,
            satellites=8,
            fix_valid=True
        )
        compact = coord.to_compact_str()
        assert "17.385044" in compact
        assert "78.486671" in compact
        assert "8sats" in compact

    def test_threat_event_serialization(self):
        event = ThreatEvent(
            node_id="AGT-ALPHA-01",
            event_id="EVT-9981",
            threat=ThreatClassification(
                threat_type=ThreatType.HUMAN_INTRUSION,
                confidence=0.88,
                verification_source=VerificationSource.MULTI_SENSOR_FUSED
            ),
            location=GeoCoordinate(latitude=17.385, longitude=78.486, altitude_m=500.0, satellites=6, fix_valid=True),
            bbox=BoundingBox(xmin=0.2, ymin=0.2, xmax=0.8, ymax=0.8, confidence=0.88)
        )
        json_output = event.to_json()
        assert "AGT-ALPHA-01" in json_output
        assert "HUMAN_INTRUSION" in json_output
        assert "MULTI_SENSOR_FUSED" in json_output

        compact_payload = event.to_compact_mesh_payload()
        assert "[AGT:ALERT" in compact_payload
        assert "EVT-9981" in compact_payload
        assert "88%" in compact_payload

    def test_heartbeat_telemetry_compact_payload(self):
        health = SystemHealth(
            battery_voltage=12.4,
            solar_voltage=18.5,
            cpu_temperature_c=47.2,
            uptime_seconds=3600
        )
        beacon = HeartbeatTelemetry(
            node_id="AGT-TEST-01",
            location=GeoCoordinate(latitude=17.38, longitude=78.48, fix_valid=True),
            health=health
        )
        compact = beacon.to_compact_mesh_payload()
        assert "[AGT:BEACON" in compact
        assert "BAT:12.4V" in compact
        assert "SOL:18.5V" in compact
        assert "CPU:47.2C" in compact


class TestFusionPipeline:
    """Tests for multi-stage sensor fusion, gating, and false alarm rejection."""

    def setup_method(self):
        self.config = SentryNodeConfig(
            node_id="TEST-NODE-01",
            radar=RadarConfig(cooldown_seconds=1.0),
            vision=VisionConfig(
                confidence_threshold=0.5,
                num_verification_frames=3,
                min_positive_frames=1
            )
        )
        self.radar = MockRadarSensor(self.config.radar)
        self.gps = MockGPSReader(self.config.gps)
        self.vision = MockVisionDetector(self.config.vision, simulated_confidence=0.92)
        self.lora = MockLoRaTransmitter(self.config.lora)

        self.dispatched_events = []
        self.engine = SentryFusionEngine(
            config=self.config,
            radar=self.radar,
            gps=self.gps,
            vision=self.vision,
            lora=self.lora,
            on_threat_detected=lambda e: self.dispatched_events.append(e)
        )

    def test_full_threat_detection_lifecycle(self):
        """Verify that Radar Trigger -> Vision Confirmed -> GPS Tagged -> LoRa Dispatched."""
        self.engine.start()

        # Trigger radar motion event
        self.radar.trigger_motion()
        time.sleep(0.5)  # Wait for worker thread to complete

        # Assertions
        assert self.engine.stats["radar_triggers_total"] >= 1
        assert self.engine.stats["threats_confirmed"] == 1
        assert self.engine.stats["mesh_alerts_dispatched"] == 1
        assert len(self.lora.transmitted_packets) == 1
        assert len(self.dispatched_events) == 1

        event: ThreatEvent = self.dispatched_events[0]
        assert event.node_id == "TEST-NODE-01"
        assert event.threat.threat_type == ThreatType.HUMAN_INTRUSION
        assert event.location is not None
        assert event.location.fix_valid is True

        self.engine.stop()

    def test_false_positive_filtering(self):
        """Verify that non-human motion (vision returns 0 detections) is filtered without alert."""
        # Configure vision mock to return 0 detections (e.g. wind/leaves)
        self.vision.simulated_confidence = 0.10  # Below 0.50 threshold
        # Overwrite method to return empty list
        self.vision.verify_human_presence = lambda num_frames=None: []

        self.engine.start()
        self.radar.trigger_motion()
        time.sleep(0.5)

        # Assertions: Radar fired, but vision rejected threat -> No LoRa alert dispatched
        assert self.engine.stats["radar_triggers_total"] >= 1
        assert self.engine.stats["false_positives_filtered"] == 1
        assert self.engine.stats["threats_confirmed"] == 0
        assert len(self.lora.transmitted_packets) == 0

        self.engine.stop()

    def test_radar_cooldown_debounce(self):
        """Verify that multiple rapid radar triggers within cooldown are debounced."""
        self.config = SentryNodeConfig(
            node_id="TEST-NODE-01",
            radar=RadarConfig(cooldown_seconds=3.0),
            vision=VisionConfig(confidence_threshold=0.5, min_positive_frames=1)
        )
        self.engine.config = self.config
        self.engine.start()

        # Trigger twice in rapid succession
        self.radar.trigger_motion()
        time.sleep(0.1)
        self.radar.trigger_motion()
        time.sleep(0.5)

        # Only 1 alert should be dispatched due to 3.0s cooldown
        assert self.engine.stats["radar_triggers_total"] == 2
        assert self.engine.stats["threats_confirmed"] == 1
        assert len(self.lora.transmitted_packets) == 1

        self.engine.stop()
