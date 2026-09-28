"""
Edge AI Vision & Human Detection Driver
Captures camera frames using a dedicated background worker thread to eliminate
V4L2 buffer lag on embedded platforms, and runs class-restricted inference
filtering exclusively for human presence (COCO Class 0 = 'person').
"""

import logging
import threading
import time
from typing import List, Optional
from .base import BaseVisionDetector
from ..config import VisionConfig
from ..cdm.models import BoundingBox

logger = logging.getLogger("AGT.Vision")

# Check available computer vision backends
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False


class ThreadedCameraWorker:
    """
    Background worker that continuously fetches frames from cv2.VideoCapture.
    Crucial optimization for Raspberry Pi: keeps the V4L2 hardware frame buffer drained
    so the AI pipeline always evaluates the latest real-time frame rather than stale cache.
    """

    def __init__(self, camera_index: int, width: int = 640, height: int = 480):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame = None
        self.lock = threading.Lock()
        self.is_running = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV is not installed. Camera worker cannot initialize hardware.")
            return False

        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.warning(f"Failed to open video capture device /dev/video{self.camera_index}")
                return False

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop, name="Cam-Worker", daemon=True)
            self.thread.start()
            logger.info(f"Threaded camera capture active on /dev/video{self.camera_index} ({self.width}x{self.height}).")
            return True
        except Exception as e:
            logger.error(f"Error initializing camera: {e}")
            return False

    def _capture_loop(self) -> None:
        while self.is_running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.latest_frame = frame
            else:
                time.sleep(0.01)

    def get_frame(self):
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def stop(self) -> None:
        self.is_running = False
        if self.cap:
            try:
                self.cap.release()
            except Exception as e:
                logger.warning(f"Error releasing camera: {e}")
        logger.info("Camera capture worker stopped.")


class VisionDetector(BaseVisionDetector):
    """
    Physical Edge AI vision pipeline running lightweight YOLOv8n or HOG/DNN models.
    Filters exclusively for human detections (Class ID 0) with confidence gating.
    """

    def __init__(self, config: VisionConfig, model_name: str = "yolov8n.pt"):
        self.config = config
        self.model_name = model_name
        self.worker: Optional[ThreadedCameraWorker] = None
        self.model = None

    def start(self) -> None:
        self.worker = ThreadedCameraWorker(
            camera_index=self.config.camera_index,
            width=self.config.frame_width,
            height=self.config.frame_height
        )
        self.worker.start()

        if YOLO_AVAILABLE:
            try:
                self.model = YOLO(self.model_name)
                logger.info(f"Loaded Edge AI model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Failed loading YOLO model {self.model_name}: {e}")

    def verify_human_presence(self, num_frames: Optional[int] = None) -> List[BoundingBox]:
        """
        Samples N frames from the live stream and runs class-restricted detection.
        Returns validated human bounding boxes if threshold is met.
        """
        if not self.worker or not self.worker.is_running:
            logger.warning("Camera worker not running, returning empty detections.")
            return []

        frames_to_check = num_frames or self.config.num_verification_frames
        confirmed_detections: List[BoundingBox] = []

        for _ in range(frames_to_check):
            frame = self.worker.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            # If YOLO model is loaded
            if self.model:
                try:
                    results = self.model(frame, verbose=False, conf=self.config.confidence_threshold)
                    for r in results:
                        for box in r.boxes:
                            cls_id = int(box.cls[0])
                            conf = float(box.conf[0])
                            # Strictly filter for Class 0 ('person')
                            if cls_id == self.config.target_class_id and conf >= self.config.confidence_threshold:
                                xyxyn = box.xyxyn[0].tolist()
                                confirmed_detections.append(
                                    BoundingBox(
                                        xmin=xyxyn[0],
                                        ymin=xyxyn[1],
                                        xmax=xyxyn[2],
                                        ymax=xyxyn[3],
                                        confidence=conf,
                                        label="person"
                                    )
                                )
                except Exception as e:
                    logger.debug(f"Inference error: {e}")

            time.sleep(0.06)

        return confirmed_detections

    def stop(self) -> None:
        if self.worker:
            self.worker.stop()
        logger.info("Vision detector stopped.")


class MockVisionDetector(BaseVisionDetector):
    """
    Simulation / Interview Demo Mock for the Vision Detection Pipeline.
    Simulates high-confidence human presence or accepts live webcam when available.
    """

    def __init__(self, config: VisionConfig, simulated_confidence: float = 0.88):
        self.config = config
        self.simulated_confidence = simulated_confidence
        self._is_running = False

    def start(self) -> None:
        self._is_running = True
        logger.info("[MOCK] Vision Detector initialized in Simulation Mode.")

    def verify_human_presence(self, num_frames: Optional[int] = None) -> List[BoundingBox]:
        """Returns realistic simulated bounding boxes for a detected human intruder."""
        logger.info(
            f"[MOCK AI INFERENCE] Evaluating {num_frames or self.config.num_verification_frames} frames..."
        )
        time.sleep(0.3)  # Simulate edge inference latency (e.g. ~60ms per frame)

        # Return a verified human intruder bounding box
        detected_box = BoundingBox(
            xmin=0.32,
            ymin=0.18,
            xmax=0.68,
            ymax=0.92,
            confidence=self.simulated_confidence,
            label="person"
        )
        logger.info(
            f"[MOCK AI INFERENCE] Verified Target: 'person' (Confidence: {self.simulated_confidence * 100:.1f}%)"
        )
        return [detected_box]

    def stop(self) -> None:
        self._is_running = False
        logger.info("[MOCK] Vision detector stopped.")
