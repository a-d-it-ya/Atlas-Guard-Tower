"""
Hardware Abstraction Layer (HAL) — Base Driver Interfaces
Provides consistent contracts for physical hardware drivers and simulation mocks.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, List, Dict, Any
from ..cdm.models import GeoCoordinate, BoundingBox


class BaseRadarSensor(ABC):
    """Interface for RCWL-0516 Microwave Radar motion sensor."""

    @abstractmethod
    def start(self, on_motion_callback: Callable[[], None]) -> None:
        """Start listening for motion events and bind interrupt callback."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Release GPIO resources."""
        pass

    @abstractmethod
    def is_motion_detected(self) -> bool:
        """Query current digital state of presence pin."""
        pass


class BaseGPSReader(ABC):
    """Interface for u-blox NEO-6M GPS receiver."""

    @abstractmethod
    def start(self) -> None:
        """Start background NMEA serial parsing thread."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop serial thread and close UART."""
        pass

    @abstractmethod
    def get_latest_coordinates(self) -> GeoCoordinate:
        """Retrieve most recently computed valid GPS fix."""
        pass


class BaseVisionDetector(ABC):
    """Interface for edge AI camera and human classification pipeline."""

    @abstractmethod
    def start(self) -> None:
        """Initialize camera stream / video capture thread."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Release camera hardware."""
        pass

    @abstractmethod
    def verify_human_presence(self, num_frames: int = 5) -> List[BoundingBox]:
        """
        Wake vision pipeline, analyze N frames, and return list of detected human bounding boxes.
        """
        pass


class BaseLoRaTransmitter(ABC):
    """Interface for Heltec LoRa32 V3 / Meshtastic communication."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection with the LoRa node."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully disconnect from LoRa node."""
        pass

    @abstractmethod
    def send_alert(self, payload_text: str, want_ack: bool = True) -> bool:
        """Broadcast high-priority intrusion alert across the LoRa mesh."""
        pass

    @abstractmethod
    def send_telemetry(self, payload_text: str) -> bool:
        """Broadcast routine node health beacon across the LoRa mesh."""
        pass
