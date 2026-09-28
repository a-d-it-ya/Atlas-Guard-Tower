"""
Atlas Guard Tower (AGT) — Main Application Entry Point
Autonomous Edge AI Sentry Node for Perimeter Defense & LoRa Mesh Fusion.

Usage:
  # Run in Simulation / Interview Demo Mode (Laptop / PC):
  python main.py --sim --interactive

  # Run on Raspberry Pi with Physical Hardware:
  python main.py
"""

import argparse
import logging
import os
import signal
import sys
import time
from typing import Optional

# Setup package path resolution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas_guard_tower.config import SentryNodeConfig
from atlas_guard_tower.drivers import (
    RadarSensor,
    MockRadarSensor,
    GPSReader,
    MockGPSReader,
    VisionDetector,
    MockVisionDetector,
    MeshtasticLoRaTransmitter,
    MockLoRaTransmitter,
)
from atlas_guard_tower.core import SentryFusionEngine, TelemetryWorker


def setup_logging(debug: bool = False) -> None:
    """Configures structured console logging."""
    level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt="%H:%M:%S"
    )


def print_banner(config: SentryNodeConfig, is_sim: bool) -> None:
    """Prints system startup banner."""
    banner = f"""
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║                 ATLAS GUARD TOWER (AGT) — SENTRY NODE                    ║
    ║        Edge AI Perimeter Surveillance & LoRa Mesh Sensor Fusion          ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║  Node ID:         {config.node_id:<54} ║
    ║  Deployment Site: {config.site_name:<54} ║
    ║  Mode:            {'SIMULATION / DEMO (Mock HAL)' if is_sim else 'PHYSICAL HARDWARE (Raspberry Pi 4B)':<54} ║
    ║  Radio Profile:   {config.lora.frequency_band + ' (865-867 MHz WPC Delicensed)':<54} ║
    ║  Sensors:         RCWL-0516 Radar (GPIO 17) | NEO-6M GPS | Edge AI YOLO  ║
    ║  Mesh Gateway:    Heltec LoRa32 V3 (Meshtastic Firmware via Protobuf)    ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="Atlas Guard Tower (AGT) — Edge AI Sentry Node Application"
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Run in Simulation / Interview Demo Mode (mocks physical GPIO, GPS UART, and LoRa)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive terminal mode (press [ENTER] to trigger simulated radar motion)"
    )
    parser.add_argument(
        "--auto-trigger",
        type=float,
        default=0.0,
        help="Interval in seconds for automatic periodic synthetic radar triggers in simulation mode"
    )
    parser.add_argument(
        "--node-id",
        type=str,
        default="AGT-ALPHA-01",
        help="Unique identifier for this sentry node"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging"
    )

    args = parser.parse_args()
    setup_logging(debug=args.debug)

    # Initialize node configuration
    config = SentryNodeConfig(
        node_id=args.node_id,
        debug_mode=args.debug,
        simulation_mode=args.sim
    )

    print_banner(config, is_sim=args.sim)

    # Instantiate Drivers (Physical vs Mock HAL)
    if args.sim:
        logging.info("Initializing drivers with Simulation Mock HAL...")
        radar = MockRadarSensor(
            config.radar,
            auto_trigger_interval=args.auto_trigger if args.auto_trigger > 0 else None
        )
        gps = MockGPSReader(config.gps)
        vision = MockVisionDetector(config.vision)
        lora = MockLoRaTransmitter(config.lora)
    else:
        logging.info("Initializing physical hardware drivers on Raspberry Pi...")
        try:
            radar = RadarSensor(config.radar)
            gps = GPSReader(config.gps)
            vision = VisionDetector(config.vision)
            lora = MeshtasticLoRaTransmitter(config.lora)
        except Exception as e:
            logging.error(f"Hardware initialization error: {e}")
            logging.warning("Falling back to Simulation Mode. Use --sim to avoid this warning.")
            radar = MockRadarSensor(config.radar)
            gps = MockGPSReader(config.gps)
            vision = MockVisionDetector(config.vision)
            lora = MockLoRaTransmitter(config.lora)

    # Initialize Core Engines
    fusion_engine = SentryFusionEngine(
        config=config,
        radar=radar,
        gps=gps,
        vision=vision,
        lora=lora
    )

    telemetry_worker = TelemetryWorker(
        config=config,
        gps=gps,
        lora=lora
    )

    # Register Clean Signal Handlers for Graceful Shutdown
    def handle_shutdown(signum, frame):
        print("\n\n[SHUTDOWN] Received termination signal. Releasing resources...")
        telemetry_worker.stop()
        fusion_engine.stop()
        print("[SHUTDOWN] Sentry node gracefully terminated.\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Start Services
    fusion_engine.start()
    telemetry_worker.start()

    # Interactive Demo Mode for Interviews
    if args.interactive and isinstance(radar, MockRadarSensor):
        print("\n" + "─" * 70)
        print(" [INTERACTIVE DEMO MODE ACTIVE]")
        print("  ► Press [ENTER] to simulate a Microwave Radar motion trigger")
        print("  ► Type 'q' and press [ENTER] to quit")
        print("─" * 70 + "\n")

        try:
            while True:
                user_input = input()
                if user_input.strip().lower() == "q":
                    break
                radar.trigger_motion()
        except EOFError:
            pass
        finally:
            handle_shutdown(None, None)
    else:
        # Standard daemon loop
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            handle_shutdown(None, None)


if __name__ == "__main__":
    main()
