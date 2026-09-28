"""
RCWL-0516 Microwave Radar Presence Sensor Driver
Handles Doppler microwave radar motion detection via Raspberry Pi GPIO interrupts.
Provides automatic fallback to a simulation mock when running on non-Pi platforms.
"""

import logging
import time
import threading
from typing import Callable, Optional
from .base import BaseRadarSensor
from ..config import RadarConfig

logger = logging.getLogger("AGT.Radar")

# Attempt to import Raspberry Pi GPIO library
try:
    import RPi.GPIO as GPIO
    RPI_GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_GPIO_AVAILABLE = False


class RadarSensor(BaseRadarSensor):
    """
    Physical driver for RCWL-0516 Doppler Microwave Radar sensor.
    Uses interrupt-driven edge detection (GPIO.RISING) with debounce filtering.
    """

    def __init__(self, config: RadarConfig):
        self.config = config
        self._callback: Optional[Callable[[], None]] = None
        self._is_running = False
        self._last_trigger_time = 0.0

        if not RPI_GPIO_AVAILABLE:
            raise RuntimeError(
                "RPi.GPIO library is not available. Use MockRadarSensor for non-Pi environments."
            )

    def start(self, on_motion_callback: Callable[[], None]) -> None:
        self._callback = on_motion_callback
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.config.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        # Register hardware interrupt on rising edge (motion detected)
        GPIO.add_event_detect(
            self.config.gpio_pin,
            GPIO.RISING,
            callback=self._gpio_interrupt_handler,
            bouncetime=self.config.bounce_time_ms
        )
        self._is_running = True
        logger.info(f"RCWL-0516 Radar driver active on BCM GPIO {self.config.gpio_pin}.")

    def _gpio_interrupt_handler(self, channel: int) -> None:
        now = time.time()
        # Enforce minimum cooldown window between successive alert dispatches
        if now - self._last_trigger_time < self.config.cooldown_seconds:
            logger.debug("Radar event debounced (cooldown active).")
            return

        self._last_trigger_time = now
        logger.info("[RADAR TRIGGER] Microwave presence detected (Doppler shift)!")
        if self._callback:
            self._callback()

    def is_motion_detected(self) -> bool:
        if not self._is_running:
            return False
        return bool(GPIO.input(self.config.gpio_pin))

    def stop(self) -> None:
        if self._is_running:
            try:
                GPIO.remove_event_detect(self.config.gpio_pin)
                GPIO.cleanup(self.config.gpio_pin)
            except Exception as e:
                logger.warning(f"Error cleaning up GPIO: {e}")
            self._is_running = False
            logger.info("RCWL-0516 Radar driver stopped.")


class MockRadarSensor(BaseRadarSensor):
    """
    Simulation / Demo Mock for RCWL-0516 Radar Sensor.
    Allows automated synthetic triggers or manual trigger injection for interview demos.
    """

    def __init__(self, config: RadarConfig, auto_trigger_interval: Optional[float] = None):
        self.config = config
        self.auto_trigger_interval = auto_trigger_interval
        self._callback: Optional[Callable[[], None]] = None
        self._is_running = False
        self._state = False
        self._worker_thread: Optional[threading.Thread] = None

    def start(self, on_motion_callback: Callable[[], None]) -> None:
        self._callback = on_motion_callback
        self._is_running = True
        logger.info("[MOCK] RCWL-0516 Radar initialized in Simulation Mode.")

        if self.auto_trigger_interval and self.auto_trigger_interval > 0:
            self._worker_thread = threading.Thread(target=self._auto_trigger_loop, daemon=True)
            self._worker_thread.start()

    def _auto_trigger_loop(self) -> None:
        while self._is_running:
            time.sleep(self.auto_trigger_interval)
            if self._is_running:
                logger.info("[MOCK RADAR] Generating synthetic microwave motion event...")
                self.trigger_motion()

    def trigger_motion(self) -> None:
        """Manually fire a presence detection event."""
        self._state = True
        if self._callback:
            self._callback()
        # Reset state after brief pulse
        threading.Timer(1.0, self._reset_state).start()

    def _reset_state(self) -> None:
        self._state = False

    def is_motion_detected(self) -> bool:
        return self._state

    def stop(self) -> None:
        self._is_running = False
        logger.info("[MOCK] Radar driver stopped.")
