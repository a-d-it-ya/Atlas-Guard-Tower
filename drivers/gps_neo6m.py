"""
u-blox NEO-6M GPS Receiver Driver
Reads NMEA-0183 sentences ($GPGGA, $GPRMC) over hardware UART using pyserial
and parses geographic fix data via pynmea2. Includes thread-safe location cache
and a high-fidelity simulation mock.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from .base import BaseGPSReader
from ..config import GPSConfig
from ..cdm.models import GeoCoordinate

logger = logging.getLogger("AGT.GPS")

try:
    import serial
    import pynmea2
    PYNMEA_AVAILABLE = True
except ImportError:
    PYNMEA_AVAILABLE = False


class GPSReader(BaseGPSReader):
    """
    Physical driver for u-blox NEO-6M connected via Raspberry Pi UART (/dev/serial0).
    Runs a background reading thread that continuously parses incoming NMEA stream.
    """

    def __init__(self, config: GPSConfig):
        self.config = config
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._serial_conn: Optional[serial.Serial] = None

        # Cached latest valid coordinates
        self._latest_coords = GeoCoordinate(
            latitude=0.0,
            longitude=0.0,
            altitude_m=0.0,
            satellites=0,
            hdop=99.9,
            fix_valid=False
        )

        if not PYNMEA_AVAILABLE:
            logger.warning("pyserial/pynmea2 not installed. Physical GPS will require dependencies.")

    def start(self) -> None:
        if not PYNMEA_AVAILABLE:
            raise RuntimeError("Cannot start physical GPS without pyserial and pynmea2.")

        try:
            self._serial_conn = serial.Serial(
                port=self.config.serial_port,
                baudrate=self.config.baud_rate,
                timeout=self.config.timeout
            )
            self._is_running = True
            self._thread = threading.Thread(target=self._read_loop, name="NEO6M-Reader", daemon=True)
            self._thread.start()
            logger.info(f"NEO-6M GPS driver initialized on {self.config.serial_port} @ {self.config.baud_rate} baud.")
        except Exception as e:
            logger.error(f"Failed to open GPS serial port {self.config.serial_port}: {e}")
            raise

    def _read_loop(self) -> None:
        """Continuous serial read loop parsing NMEA sentences."""
        buffer = ""
        while self._is_running and self._serial_conn and self._serial_conn.is_open:
            try:
                raw_line = self._serial_conn.readline().decode("ascii", errors="replace").strip()
                if not raw_line.startswith("$"):
                    continue

                if raw_line.startswith("$GPGGA") or raw_line.startswith("$GNGGA"):
                    self._parse_gga(raw_line)
                elif raw_line.startswith("$GPRMC") or raw_line.startswith("$GNRMC"):
                    self._parse_rmc(raw_line)

            except Exception as e:
                logger.debug(f"GPS parsing error: {e}")
                time.sleep(0.1)

    def _parse_gga(self, nmea_str: str) -> None:
        """Parse $GPGGA for coordinates, fix quality, altitude, and satellites."""
        try:
            msg = pynmea2.parse(nmea_str)
            if msg.gps_qual and int(msg.gps_qual) > 0 and msg.latitude and msg.longitude:
                num_sats = int(msg.num_sats) if msg.num_sats else 0
                altitude = float(msg.altitude) if msg.altitude else 0.0
                hdop = float(msg.horizontal_dil) if msg.horizontal_dil else 1.0

                with self._lock:
                    self._latest_coords = GeoCoordinate(
                        latitude=float(msg.latitude),
                        longitude=float(msg.longitude),
                        altitude_m=altitude,
                        satellites=num_sats,
                        hdop=hdop,
                        fix_valid=(num_sats >= self.config.min_satellites_for_fix),
                        timestamp_utc=datetime.now(timezone.utc).isoformat()
                    )
        except Exception as e:
            logger.debug(f"Error parsing GGA: {e}")

    def _parse_rmc(self, nmea_str: str) -> None:
        """Parse $GPRMC for active fix status and timestamps."""
        try:
            msg = pynmea2.parse(nmea_str)
            is_valid = (msg.status == "A")  # 'A' = Valid/Active, 'V' = Void
            if is_valid and msg.latitude and msg.longitude:
                with self._lock:
                    if not self._latest_coords.fix_valid:
                        self._latest_coords.latitude = float(msg.latitude)
                        self._latest_coords.longitude = float(msg.longitude)
                        self._latest_coords.fix_valid = True
        except Exception as e:
            logger.debug(f"Error parsing RMC: {e}")

    def get_latest_coordinates(self) -> GeoCoordinate:
        with self._lock:
            return self._latest_coords

    def stop(self) -> None:
        self._is_running = False
        if self._serial_conn and self._serial_conn.is_open:
            try:
                self._serial_conn.close()
            except Exception as e:
                logger.warning(f"Error closing GPS serial port: {e}")
        logger.info("NEO-6M GPS driver stopped.")


class MockGPSReader(BaseGPSReader):
    """
    High-fidelity Mock for NEO-6M GPS.
    Generates realistic geographic coordinates (e.g. Hyderabad / Perimeter sector)
    with realistic satellite count and slight GPS drift.
    """

    def __init__(
        self,
        config: GPSConfig,
        initial_lat: float = 17.385044,     # Hyderabad reference coordinates
        initial_lon: float = 78.486671,
        altitude_m: float = 542.0
    ):
        self.config = config
        self.lat = initial_lat
        self.lon = initial_lon
        self.alt = altitude_m
        self._is_running = False

    def start(self) -> None:
        self._is_running = True
        logger.info(
            f"[MOCK] NEO-6M GPS initialized at Lat: {self.lat:.6f}, Lon: {self.lon:.6f}, Alt: {self.alt:.1f}m (3D Fix Locked)."
        )

    def get_latest_coordinates(self) -> GeoCoordinate:
        # Simulate subtle GPS drift (micro-meter variation)
        import random
        drift_lat = self.lat + random.uniform(-0.00002, 0.00002)
        drift_lon = self.lon + random.uniform(-0.00002, 0.00002)

        return GeoCoordinate(
            latitude=drift_lat,
            longitude=drift_lon,
            altitude_m=self.alt,
            satellites=8,
            hdop=0.9,
            fix_valid=True,
            timestamp_utc=datetime.now(timezone.utc).isoformat()
        )

    def stop(self) -> None:
        self._is_running = False
        logger.info("[MOCK] GPS driver stopped.")
