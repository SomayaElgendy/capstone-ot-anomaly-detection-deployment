#!/usr/bin/env python3
import logging
from config import REDIS_HOST, REDIS_PORT, INTERFACE_PATTERN, TARGET_IPS
from capture import PacketCapture

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("Network Telemetry Service for ICS-SimLab")
    logger.info("=" * 60)
    logger.info(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"Target IPs: {TARGET_IPS}")
    
    capture = PacketCapture()
    capture.start_capture(INTERFACE_PATTERN)


if __name__ == "__main__":
    main()
