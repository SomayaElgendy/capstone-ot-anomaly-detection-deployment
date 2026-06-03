#!/usr/bin/env python3
import os

# ============================================
# CONFIGURATION
# ============================================
REDIS_HOST = os.environ.get('REDIS_HOST', '192.168.0.200')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

# Flow timing — matched exactly to LogicForFlow.py parameters
FLOW_INTERVAL  = float(os.environ.get('FLOW_INTERVAL',  0.05))  # loop tick (faster than idle timeout)
IDLE_TIMEOUT   = float(os.environ.get('IDLE_TIMEOUT',   0.5))   # matches interval_seconds=0.5
ACTIVE_TIMEOUT = float(os.environ.get('ACTIVE_TIMEOUT', 15.0))  # matches active_timeout_seconds=15.0
MODBUS_TIMEOUT = float(os.environ.get('MODBUS_TIMEOUT', 30.0))  # matches modbus_active_timeout_seconds=30.0

INTERFACE_PATTERN = os.environ.get('CAPTURE_INTERFACES', 'veth*')
TARGET_IPS = {
    '192.168.0.21', '192.168.0.22', '192.168.0.31',
    '192.168.0.32', '192.168.0.33', '192.168.0.100', '192.168.0.200'
}

# Redis keys
REDIS_STREAM           = 'network:telemetry'
REDIS_CHANNEL          = 'network:updates'
REDIS_STATE_KEY        = 'network:current_state'
REDIS_SCHEMA_KEY       = 'network:schema'
REDIS_ACTIVE_FLOWS_KEY = 'network:active_flows'
MAX_STREAM_LEN         = 10000
REDIS_FLOW_STATS_KEY   = 'network:flow_stats:'
