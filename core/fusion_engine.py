"""
Sentry Fusion Engine — Multi-Stage Perimeter Threat Verification
Orchestrates sensor fusion between passive microwave presence detection,
active Edge AI vision verification, GPS geotagging, and LoRa mesh dispatching.
"""

import logging
import threading
import time
from typing import Optional, Callable
from ..config import SentryNodeConfig
from ..cdm.models import (
    ThreatEvent,
    ThreatClassification,
    ThreatType,
    VerificationSource,
    BoundingBox,
)
from ..drivers.base import (
    BaseRadarSensor,
    BaseGPSReader,
    BaseVisionDetector,
    BaseLoRaTransmitter,
)

logger = logging.getLogger("AGT.FusionEngine")


class SentryFusionEngine:
    """
    Core state machine and sensor fusion orchestrator for Atlas Guard Tower.
    
    Processing Pipeline:
      [Stage 1] RCWL-0516 Microwave Radar -> Trigger Interrupt
      [Stage 2] Edge AI Camera Verification -> Class-restricted Human Detection (5 frames)
      [Stage 3] u-blox NEO-6M GPS Geotagging -> Coordinates + Satellites
      [Stage 4] HiveOS CDM Packaging & LoRa Mesh Dispatch (Heltec LoRa32 V3)
    """

    def __init__(
        self,
        config: SentryNodeConfig,
        radar: BaseRadarSensor,
        gps: BaseGPSReader,
        vision: BaseVisionDetector,
        lora: BaseLoRaTransmitter,
        on_threat_detected: Optional[Callable[[ThreatEvent], None]] = None,
    ):
        self.config = config
        self.radar = radar
        self.gps = gps
        self.vision = vision
        self.lora = lora
        self.on_threat_detected = on_threat_detected

        self._lock = threading.Lock()
        self._is_running = False
        self._last_alert_time = 0.0

        # Operational metrics
        self.stats = {
            "radar_triggers_total": 0,
            "vision_verifications_total": 0,
            "threats_confirmed": 0,
            "false_positives_filtered": 0,
            "mesh_alerts_dispatched": 0,
        }

    def start(self) -> None:
        """Start all underlying sensor drivers and bind fusion pipeline."""
        with self._lock:
            if self._is_running:
                return

            logger.info("Initializing Atlas Guard Tower Sensor Fusion Engine...")
            self.gps.start()
            self.vision.start()
            self.lora.connect()
            self.radar.start(on_motion_callback=self._handle_radar_trigger)
            self._is_running = True
            logger.info("Sentry Fusion Engine is ARMED and monitoring perimeter.")

    def _handle_radar_trigger(self) -> None:
        """
        Stage 1 Entry: Called asynchronously when RCWL-0516 microwave radar fires.
        Spawns worker thread to run non-blocking vision verification.
        """
        with self._lock:
            self.stats["radar_triggers_total"] += 1

        now = time.time()
        # Cooldown guard: Prevent flooding LoRa mesh if radar stays triggered
        if now - self._last_alert_time < self.config.radar.cooldown_seconds:
            logger.info("[COOLDOWN] Radar trigger ignored (cooldown window active).")
            return

        # Execute vision verification in separate worker to avoid blocking GPIO interrupts
        worker = threading.Thread(
            target=self._process_threat_pipeline,
            name="Threat-Pipeline-Worker",
            daemon=True
        )
        worker.start()

    def _process_threat_pipeline(self) -> None:
        """
        Executes Stages 2, 3, and 4 sequentially.
        """
        logger.info("\n>>> [STAGE 1: RADAR TRIGGERED] Microwave disturbance detected!")
        logger.info(">>> [STAGE 2: WAKING EDGE AI] Sampling frames for human presence...")

        with self._lock:
            self.stats["vision_verifications_total"] += 1

        # Stage 2: Computer Vision Human Verification
        detections = self.vision.verify_human_presence(
            num_frames=self.config.vision.num_verification_frames
        )

        # Check if verified detections meet requirements
        valid_human_detections = [
            d for d in detections if d.confidence >= self.config.vision.confidence_threshold
        ]

        if len(valid_human_detections) < self.config.vision.min_positive_frames:
            with self._lock:
                self.stats["false_positives_filtered"] += 1
            logger.warning(
                f"[STAGE 2: FILTERED] Visual check negative ({len(valid_human_detections)} detections). "
                f"Classified as non-human/environmental disturbance (false alarm filtered)."
            )
            return

        # Select highest confidence detection
        best_box: BoundingBox = max(valid_human_detections, key=lambda b: b.confidence)
        logger.info(
            f"✓ [STAGE 2: CONFIRMED] Human target verified! Confidence: {best_box.confidence * 100:.1f}%, "
            f"Bounding Box: [{best_box.xmin:.2f}, {best_box.ymin:.2f}, {best_box.xmax:.2f}, {best_box.ymax:.2f}]"
        )

        # Stage 3: GPS Tagging
        logger.info(">>> [STAGE 3: GEOTAGGING] Fetching live coordinates from u-blox NEO-6M...")
        coords = self.gps.get_latest_coordinates()
        logger.info(
            f"✓ [STAGE 3: TAGGED] Lat: {coords.latitude:.6f}, Lon: {coords.longitude:.6f}, "
            f"Alt: {coords.altitude_m:.1f}m (Fix: {'3D Valid' if coords.fix_valid else 'Searching'})"
        )

        # Stage 4: HiveOS CDM Packaging & LoRa Mesh Transmission
        logger.info(">>> [STAGE 4: PACKAGING & LORA MESH TX] Serializing HiveOS CDM ThreatEvent...")
        threat_event = ThreatEvent(
            node_id=self.config.node_id,
            threat=ThreatClassification(
                threat_type=ThreatType.HUMAN_INTRUSION,
                confidence=best_box.confidence,
                verification_source=VerificationSource.MULTI_SENSOR_FUSED,
                detections_count=len(valid_human_detections)
            ),
            location=coords,
            bbox=best_box,
            requires_operator_ack=True
        )

        # Update timing and counters
        self._last_alert_time = time.time()
        with self._lock:
            self.stats["threats_confirmed"] += 1
            self.stats["mesh_alerts_dispatched"] += 1

        # Dispatch compact payload over Heltec LoRa32 V3
        mesh_payload = threat_event.to_compact_mesh_payload()
        tx_success = self.lora.send_alert(mesh_payload, want_ack=True)

        if tx_success:
            logger.info("✓ [STAGE 4: COMPLETE] High-priority alert broadcasted across LoRa Mesh.")
        else:
            logger.error("✗ [STAGE 4: FAILED] Failed to transmit alert over LoRa mesh.")

        if self.on_threat_detected:
            self.on_threat_detected(threat_event)

    def trigger_manual_simulation(self) -> None:
        """Helper to trigger an intrusion event programmatically."""
        self._handle_radar_trigger()

    def stop(self) -> None:
        """Gracefully shut down all drivers."""
        with self._lock:
            if not self._is_running:
                return

            logger.info("Shutting down Sentry Fusion Engine...")
            self.radar.stop()
            self.vision.stop()
            self.gps.stop()
            self.lora.disconnect()
            self._is_running = False
            logger.info("Sentry Fusion Engine stopped.")
