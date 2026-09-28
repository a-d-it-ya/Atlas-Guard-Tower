"""
Heltec LoRa32 V3 / Meshtastic Radio Transmitter Driver
Communicates with the stock Meshtastic firmware on Heltec LoRa32 V3 boards
via Serial Protocol Buffers (Protobuf) RPC interface. Transmits HiveOS CDM
alerts and telemetry beacons across the 868 MHz / IN_865 LoRa mesh network.
"""

import logging
import time
from typing import List, Optional
from .base import BaseLoRaTransmitter
from ..config import LoRaMeshConfig
from ..cdm.models import MeshPacket, PacketType

logger = logging.getLogger("AGT.LoRa")

try:
    import meshtastic
    import meshtastic.serial_interface
    MESHTASTIC_AVAILABLE = True
except ImportError:
    MESHTASTIC_AVAILABLE = False


class MeshtasticLoRaTransmitter(BaseLoRaTransmitter):
    """
    Physical driver for Heltec LoRa32 V3 running stock Meshtastic firmware.
    Interacts with the board over USB CDC Serial using the official Meshtastic Protobuf SDK.
    """

    def __init__(self, config: LoRaMeshConfig):
        self.config = config
        self.interface: Optional[meshtastic.serial_interface.SerialInterface] = None
        self._is_connected = False
        self._seq_num = 0

    def connect(self) -> bool:
        if not MESHTASTIC_AVAILABLE:
            logger.warning("Meshtastic Python SDK is not installed.")
            return False

        try:
            logger.info(f"Connecting to Heltec LoRa32 V3 on {self.config.serial_port}...")
            self.interface = meshtastic.serial_interface.SerialInterface(
                devPath=self.config.serial_port
            )
            self._is_connected = True
            logger.info(
                f"Successfully connected to Meshtastic Node on {self.config.serial_port} "
                f"(Band: {self.config.frequency_band}, Channel: {self.config.channel_index})."
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Heltec LoRa32: {e}")
            self._is_connected = False
            return False

    def send_alert(self, payload_text: str, want_ack: bool = True) -> bool:
        """
        Dispatches high-priority threat alert across the mesh.
        Packets are encrypted by Meshtastic firmware and broadcasted over RF.
        """
        if not self._is_connected or not self.interface:
            logger.error("Cannot transmit alert: LoRa interface not connected.")
            return False

        self._seq_num += 1
        try:
            logger.info(
                f"[LORA MESH TX] Sending ALERT #{self._seq_num} -> {self.config.destination_id} "
                f"({len(payload_text)} bytes, wantAck={want_ack})"
            )
            self.interface.sendText(
                text=payload_text,
                destinationId=self.config.destination_id,
                channelIndex=self.config.channel_index,
                wantAck=want_ack
            )
            return True
        except Exception as e:
            logger.error(f"Error transmitting alert over LoRa mesh: {e}")
            return False

    def send_telemetry(self, payload_text: str) -> bool:
        """Dispatches routine node health beacon."""
        if not self._is_connected or not self.interface:
            logger.debug("Telemetry dropped: LoRa interface not connected.")
            return False

        self._seq_num += 1
        try:
            self.interface.sendText(
                text=payload_text,
                destinationId=self.config.destination_id,
                channelIndex=self.config.channel_index,
                wantAck=False
            )
            return True
        except Exception as e:
            logger.warning(f"Error transmitting telemetry over LoRa: {e}")
            return False

    def disconnect(self) -> None:
        if self.interface:
            try:
                self.interface.close()
            except Exception as e:
                logger.warning(f"Error closing Meshtastic interface: {e}")
        self._is_connected = False
        logger.info("Heltec LoRa32 interface disconnected.")


class MockLoRaTransmitter(BaseLoRaTransmitter):
    """
    Simulation / Demo Mock for Heltec LoRa32 V3 Mesh Transmitter.
    Visualizes outgoing RF packets with modulation parameters and tracks packet history.
    """

    def __init__(self, config: LoRaMeshConfig):
        self.config = config
        self._is_connected = False
        self._seq_num = 0
        self.transmitted_packets: List[MeshPacket] = []

    def connect(self) -> bool:
        self._is_connected = True
        logger.info(
            f"[MOCK LORA] Connected to virtual Heltec LoRa32 V3 (Band: {self.config.frequency_band}, "
            f"Carrier: 865.200 MHz, Channel: {self.config.channel_index}, Mode: Mesh Relay)"
        )
        return True

    def send_alert(self, payload_text: str, want_ack: bool = True) -> bool:
        self._seq_num += 1
        packet = MeshPacket(
            packet_type=PacketType.ALERT,
            sender_node_id="MOCK-NODE",
            sequence_number=self._seq_num,
            payload_str=payload_text
        )
        self.transmitted_packets.append(packet)

        # Log formatted RF mesh transmission details
        print("\n" + "=" * 70)
        print(f"📡 [LoRa RF MESH TX] HIGH-PRIORITY INTRUSION ALERT DISPATCHED")
        print(f"   ► Radio Band:     {self.config.frequency_band} (865-867 MHz WPC Delicensed)")
        print(f"   ► Modulation:     LoRa (BW: 250 kHz, SF: 11, CR: 4/5, TX Power: +22 dBm)")
        print(f"   ► Mesh Route:     Destination = '{self.config.destination_id}' | Multi-Hop Enabled")
        print(f"   ► Packet Size:    {len(payload_text.encode('utf-8'))} bytes")
        print(f"   ► CDM Payload:    {payload_text}")
        print(f"   ► Mesh Status:    ACK Received (RSSI: -89 dBm, SNR: +7.5 dB, 1 Hop)")
        print("=" * 70 + "\n")
        return True

    def send_telemetry(self, payload_text: str) -> bool:
        self._seq_num += 1
        packet = MeshPacket(
            packet_type=PacketType.HEARTBEAT,
            sender_node_id="MOCK-NODE",
            sequence_number=self._seq_num,
            payload_str=payload_text
        )
        self.transmitted_packets.append(packet)
        logger.info(f"[LORA TELEMETRY BEACON] Broadcasted -> {payload_text}")
        return True

    def disconnect(self) -> None:
        self._is_connected = False
        logger.info("[MOCK] LoRa transmitter disconnected.")
