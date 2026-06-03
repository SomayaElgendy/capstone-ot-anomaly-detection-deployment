#!/usr/bin/env python3
import json
import logging
from config import REDIS_SCHEMA_KEY, REDIS_ACTIVE_FLOWS_KEY

logger = logging.getLogger(__name__)

# ============================================
# UPDATED NETWORK FLOW SCHEMA (43 Features)
# ============================================
NETWORK_FLOW_SCHEMA = {
    # --- Metadata & Flow Identifiers ---
    "sender_address": {
        "type": "string",
        "description": "Source IP address (initiator)",
        "required": True,
        "pattern": r"^(\d{1,3}\.){3}\d{1,3}$"
    },
    "receiver_address": {
        "type": "string", 
        "description": "Destination IP address (receiver)",
        "required": True,
        "pattern": r"^(\d{1,3}\.){3}\d{1,3}$"
    },
    "protocol": {
        "type": "string",
        "description": "Protocol layout (e.g., IPV4-TCP, IPV4-ModbusTCP)",
        "required": True
    },
    "duration": {
        "type": "float",
        "description": "Flow window life duration in seconds",
        "required": True,
        "min": 0
    },
    "timestamp": {
        "type": "float",
        "description": "Epoch start time of the specific flow record",
        "required": True,
        "min": 0
    },

    # --- Sender Statistics ('s' prefix) ---
    "sPackets": {"type": "integer", "description": "Packets sent by sender", "required": True, "min": 0},
    "sBytesMax": {"type": "integer", "description": "Maximum packet size from sender", "required": True, "min": 0},
    "sBytesMin": {"type": "integer", "description": "Minimum packet size from sender", "required": True, "min": 0},
    "sBytesAvg": {"type": "float", "description": "Average packet size from sender", "required": True, "min": 0},
    "sBytesTotal": {"type": "integer", "description": "Total bytes sent by sender", "required": True, "min": 0},
    "sLoad": {"type": "float", "description": "Sender bits per second load", "required": True, "min": 0},
    "sPayloadMax": {"type": "integer", "description": "Maximum payload layer size from sender", "required": True, "min": 0},
    "sPayloadMin": {"type": "integer", "description": "Minimum payload layer size from sender", "required": True, "min": 0},
    "sPayloadAvg": {"type": "float", "description": "Average payload layer size from sender", "required": True, "min": 0},
    "sInterPacket": {"type": "float", "description": "Average inter-packet arrival gap for sender", "required": True, "min": 0},
    "sttl": {"type": "float", "description": "Average Time-To-Live for sender packets", "required": True, "min": 0},
    "sAckRate": {"type": "float", "description": "Percentage of TCP flags containing ACK from sender", "required": True, "min": 0, "max": 1.0},
    "sFinRate": {"type": "float", "description": "Percentage of TCP flags containing FIN from sender", "required": True, "min": 0, "max": 1.0},
    "sPshRate": {"type": "float", "description": "Percentage of TCP flags containing PSH from sender", "required": True, "min": 0, "max": 1.0},
    "sRstRate": {"type": "float", "description": "Percentage of TCP flags containing RST from sender", "required": True, "min": 0, "max": 1.0},
    "sUrgRate": {"type": "float", "description": "Percentage of TCP flags containing URG from sender", "required": True, "min": 0, "max": 1.0},
    "sSynRate": {"type": "float", "description": "Percentage of TCP flags containing SYN from sender", "required": True, "min": 0, "max": 1.0},
    "sWin": {"type": "float", "description": "Average TCP window advertising metric from sender", "required": True, "min": 0},
    "sFragmentRate": {"type": "float", "description": "Percentage of fragmented IP packets from sender", "required": True, "min": 0, "max": 1.0},

    # --- Receiver Statistics ('r' prefix) ---
    "rPackets": {"type": "integer", "description": "Packets received by receiver", "required": True, "min": 0},
    "rBytesMax": {"type": "integer", "description": "Maximum packet size from receiver", "required": True, "min": 0},
    "rBytesMin": {"type": "integer", "description": "Minimum packet size from receiver", "required": True, "min": 0},
    "rBytesAvg": {"type": "float", "description": "Average packet size from receiver", "required": True, "min": 0},
    "rBytesTotal": {"type": "integer", "description": "Total bytes sent by receiver", "required": True, "min": 0},
    "rLoad": {"type": "float", "description": "Receiver bits per second load", "required": True, "min": 0},
    "rPayloadMax": {"type": "integer", "description": "Maximum payload layer size from receiver", "required": True, "min": 0},
    "rPayloadMin": {"type": "integer", "description": "Minimum payload layer size from receiver", "required": True, "min": 0},
    "rPayloadAvg": {"type": "float", "description": "Average payload layer size from receiver", "required": True, "min": 0},
    "rInterPacket": {"type": "float", "description": "Average inter-packet arrival gap for receiver", "required": True, "min": 0},
    "rttl": {"type": "float", "description": "Average Time-To-Live for receiver packets", "required": True, "min": 0},
    "rAckRate": {"type": "float", "description": "Percentage of TCP flags containing ACK from receiver", "required": True, "min": 0, "max": 1.0},
    "rFinRate": {"type": "float", "description": "Percentage of TCP flags containing FIN from receiver", "required": True, "min": 0, "max": 1.0},
    "rPshRate": {"type": "float", "description": "Percentage of TCP flags containing PSH from receiver", "required": True, "min": 0, "max": 1.0},
    "rRstRate": {"type": "float", "description": "Percentage of TCP flags containing RST from receiver", "required": True, "min": 0, "max": 1.0},
    "rUrgRate": {"type": "float", "description": "Percentage of TCP flags containing URG from receiver", "required": True, "min": 0, "max": 1.0},
    "rSynRate": {"type": "float", "description": "Percentage of TCP flags containing SYN from receiver", "required": True, "min": 0, "max": 1.0},
    "rWin": {"type": "float", "description": "Average TCP window advertising metric from receiver", "required": True, "min": 0},
    "rFragmentRate": {"type": "float", "description": "Percentage of fragmented IP packets from receiver", "required": True, "min": 0, "max": 1.0},
}

class SchemaValidator:
    def __init__(self):
        self.schema = NETWORK_FLOW_SCHEMA
    
    def validate(self, data):
        errors = []
        for field, schema in self.schema.items():
            if schema.get("required", False) and field not in data:
                errors.append(f"Missing required field: {field}")
                continue
            
            if field in data:
                value = data[field]
                if schema["type"] == "string":
                    if not isinstance(value, str):
                        errors.append(f"{field}: Expected string, got {type(value).__name__}")
                    elif "pattern" in schema:
                        import re
                        if not re.match(schema["pattern"], value):
                            errors.append(f"{field}: '{value}' does not match pattern")
                
                elif schema["type"] == "integer":
                    if not isinstance(value, (int, float)):
                        errors.append(f"{field}: Expected integer, got {type(value).__name__}")
                    else:
                        int_val = int(value)
                        if "min" in schema and int_val < schema["min"]:
                            errors.append(f"{field}: {int_val} < minimum {schema['min']}")
                
                elif schema["type"] == "float":
                    if not isinstance(value, (int, float)):
                        errors.append(f"{field}: Expected float, got {type(value).__name__}")
                    else:
                        if "min" in schema and value < schema["min"]:
                            errors.append(f"{field}: {value} < minimum {schema['min']}")
        
        return len(errors) == 0, errors

def store_schema_in_redis(redis_client):
    try:
        redis_client.set(REDIS_SCHEMA_KEY, json.dumps(NETWORK_FLOW_SCHEMA, indent=2))
        for field, info in NETWORK_FLOW_SCHEMA.items():
            redis_client.hset(f"{REDIS_SCHEMA_KEY}:fields", field, json.dumps(info))
        logger.info("✓ Updated Network behavior schema stored in Redis")
        return True
    except Exception as e:
        logger.error(f"Failed to store schema in Redis: {e}")
        return False

def verify_schema_in_redis(redis_client):
    try:
        if redis_client.exists(REDIS_SCHEMA_KEY):
            logger.info("✓ Network behavior schema verified in Redis")
            return True
        else:
            logger.warning("⚠ Network flow schema not found in Redis")
            return False
    except Exception as e:
        logger.error(f"Error verifying schema: {e}")
        return False