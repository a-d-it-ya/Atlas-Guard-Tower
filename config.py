"""
Atlas Guard Tower (AGT) — Node Configuration
Defines all hardware pin mappings, serial ports, radio frequency profiles,
vision inference thresholds, and telemetry intervals.
"""

from dataclasses import dataclass, field
import os
from typing import Optional


@dataclass(frozen=True)
class RadarConfig:
    """Configuration for RCWL-0516 Microwave Radar sensor."""
    gpio_pin: int = 17                    # BCM Pin 17 (Physical Pin 11 on RPi 4B)
    bounce_time_ms: int = 200             # Software debounce window in milliseconds
    cooldown_seconds: float = 8.0         # Minimum time between successive radar alerts


@dataclass(frozen=True)
class GPSConfig:
    """Configuration for u-blox NEO-6M GPS Module."""
    serial_port: str = "/dev/serial0"     # Hardware UART on RPi 4B (GPIO 14/15)
    baud_rate: int = 9600                 # Standard NEO-6M default baud rate
    timeout: float = 1.0                  # Serial read timeout in seconds
    min_satellites_for_fix: int = 4       # Minimum satellites required for reliable 3D fix


@dataclass(frozen=True)
class VisionConfig:
    """Configuration for Edge AI Vision / Human Detection Pipeline."""
    camera_index: int = 0                 # /dev/video0 (V4L2 USB camera or CSI via libcamera)
    frame_width: int = 640                # Scaled width for edge inference efficiency
    frame_height: int = 480               # Scaled height for edge inference efficiency
    confidence_threshold: float = 0.55    # Minimum confidence to confirm human target
    target_class_id: int = 0              # Class 0 = 'person' in COCO / YOLO dataset
    num_verification_frames: int = 5      # Number of consecutive frames evaluated on trigger
    min_positive_frames: int = 2          # Minimum human detections required out of N frames


@dataclass(frozen=True)
class LoRaMeshConfig:
    """Configuration for Heltec LoRa32 V3 (Meshtastic integration)."""
    serial_port: str = "/dev/ttyUSB0"     # USB-Serial CDC port (CP2102/CH9102 bridge)
    frequency_band: str = "IN_865"        # Indian 865-867 MHz delicensed band (868 MHz hardware)
    channel_index: int = 0                # Primary broadcast channel (0 = Default)
    destination_id: str = "^all"          # Broadcast address across entire mesh
    max_retries: int = 3                  # Retry attempts for acknowledged packets
    heartbeat_interval_s: int = 60        # Node telemetry heartbeat broadcast period (seconds)


@dataclass
class SentryNodeConfig:
    """Master configuration for the Atlas Guard Tower (AGT) Sentry Node."""
    node_id: str = field(default_factory=lambda: os.getenv("AGT_NODE_ID", "AGT-ALPHA-01"))
    site_name: str = "Sector-7 Perimeter"
    debug_mode: bool = False
    simulation_mode: bool = False

    radar: RadarConfig = field(default_factory=RadarConfig)
    gps: GPSConfig = field(default_factory=GPSConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    lora: LoRaMeshConfig = field(default_factory=LoRaMeshConfig)


# Global default configuration instance
DEFAULT_CONFIG = SentryNodeConfig()
