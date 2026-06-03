# FILE PURPOSE: Simulates the physical layer. Data is written to the 
#               SQLite database to represent physical data collection

import asyncio
import sqlite3
import logging
import time
import utils
import redis
import json
from threading import Thread
from datetime import datetime


# ============================================
# REDIS CONFIGURATION
# ============================================
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_STREAM = 'hil:telemetry'
REDIS_CHANNEL = 'hil:updates'
REDIS_STATE_KEY = 'hil:current_state'
REDIS_SCHEMA_KEY = 'hil:schema'
MAX_STREAM_LEN = 10000

# Retry configuration
REDIS_RETRY_ATTEMPTS = 5
REDIS_RETRY_DELAY = 2  # seconds


logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ============================================
# REDIS CONNECTION WITH RETRY
# ============================================
def connect_to_redis_with_retry():
    """Attempt to connect to Redis with multiple retries"""
    redis_client = None
    REDIS_AVAILABLE = False
    
    for attempt in range(REDIS_RETRY_ATTEMPTS):
        try:
            logging.info(f"🔄 Attempting to connect to Redis (attempt {attempt+1}/{REDIS_RETRY_ATTEMPTS})")
            
            client = redis.Redis(
                host=REDIS_HOST, 
                port=REDIS_PORT, 
                db=REDIS_DB, 
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3
            )
            client.ping()
            
            # Test write capability
            client.set("connection_test", "working")
            client.delete("connection_test")
            
            redis_client = client
            REDIS_AVAILABLE = True
            logging.info("✓ Redis connected successfully")
            break
            
        except redis.ConnectionError as e:
            logging.warning(f"⏳ Redis connection attempt {attempt+1} failed: {e}")
            if attempt < REDIS_RETRY_ATTEMPTS - 1:
                time.sleep(REDIS_RETRY_DELAY)
        except Exception as e:
            logging.warning(f"⏳ Redis connection attempt {attempt+1} failed: {e}")
            if attempt < REDIS_RETRY_ATTEMPTS - 1:
                time.sleep(REDIS_RETRY_DELAY)
    
    if not REDIS_AVAILABLE:
        logging.warning("⚠ Redis not available after all retry attempts - real-time streaming disabled")
    
    return redis_client, REDIS_AVAILABLE

# Initialize Redis connection with retry
redis_client, REDIS_AVAILABLE = connect_to_redis_with_retry()

# here we import the defined logic
# the logic will always be in a python file called logic.py, which gets copied to the container
try:
    import logic # type: ignore
except ModuleNotFoundError:
    logging.error("Could not import logic for HIL component")


# ============================================
# SCHEMA DEFINITION
# ============================================
# ============================================
# SCHEMA DEFINITION
# ============================================
PHYSICAL_VALUES_SCHEMA = {
    "tank_level_value": {
        "type": "integer",
        "min": 0,
        "max": 1000,
        "unit": "liters",
        "description": "Current water level in tank",
        "required": True
    },
    "tank_input_valve_state": {
        "type": "boolean",
        "values": [0, 1],
        "description": "Tank input valve position (0=closed, 1=open)",
        "required": True
    },
    "tank_output_valve_state": {
        "type": "boolean",
        "values": [0, 1],
        "description": "Tank output valve position (0=closed, 1=open)",
        "required": True
    },
    "bottle_level_value": {
        "type": "integer",
        "min": 0,
        "max": 200,
        "unit": "milliliters",
        "description": "Current water level in bottle",
        "required": True
    },
    "bottle_distance_to_filler_value": {
        "type": "integer",
        "min": 0,
        "max": 130,
        "unit": "mm",
        "description": "Distance from bottle to filler head",
        "required": True
    },
    "conveyor_belt_engine_state": {
        "type": "boolean",
        "values": [0, 1],
        "description": "Conveyor belt state (0=stopped, 1=running)",
        "required": True
    },
    "tank_output_flow_value": {
        "type": "float",
        "min": 0,
        "max": 100,
        "unit": "liters/min",
        "description": "Flow rate from tank output",
        "required": False
    },
    "tank_input_flow_value": {
        "type": "float",
        "min": 0,
        "max": 100,
        "unit": "liters/min",
        "description": "Flow rate from tank input",
        "required": False
    },
    "tank_input_valve_position": {
        "type": "float",
        "min": 0,
        "max": 1,
        "unit": "position",
        "description": "Tank input valve position (0=closed, 1=fully open)",
        "required": False
    },
    "tank_output_valve_position": {
        "type": "float",
        "min": 0,
        "max": 1,
        "unit": "position",
        "description": "Tank output valve position (0=closed, 1=fully open)",
        "required": False
    },
    "tank_pressure": {
        "type": "float",
        "min": 0,
        "max": 0.5,
        "unit": "bar",
        "description": "Hydrostatic pressure in tank",
        "required": False
    },
    "supply_pressure": {
        "type": "float",
        "min": 0,
        "max": 5,
        "unit": "bar",
        "description": "Water supply pressure",
        "required": False
    },
    "plc1_mode": {
        "type": "integer",
        "min": 1,
        "max": 5,
        "unit": "mode",
        "description": "PLC1 operating mode (1=RUN, 2=PROGRAM, 3=REMOTE, 4=TEST, 5=STOP)",
        "required": False
    },
    "plc2_mode": {
        "type": "integer",
        "min": 1,
        "max": 5,
        "unit": "mode",
        "description": "PLC2 operating mode (1=RUN, 2=PROGRAM, 3=REMOTE, 4=TEST, 5=STOP)",
        "required": False
    }
}
# ============================================
# SCHEMA VALIDATION FUNCTION
# ============================================
def validate_telemetry_data(telemetry_data):
    """Validate telemetry data against schema"""
    errors = []
    
    for field, schema in PHYSICAL_VALUES_SCHEMA.items():
        # Check required fields
        if schema.get("required", False) and field not in telemetry_data:
            errors.append(f"Missing required field: {field}")
            continue
            
        if field in telemetry_data:
            value = telemetry_data[field]
            
            # Type validation
            if schema["type"] == "integer":
                try:
                    value = int(value)
                    if "min" in schema and value < schema["min"]:
                        errors.append(f"{field}: {value} < minimum {schema['min']}")
                    if "max" in schema and value > schema["max"]:
                        errors.append(f"{field}: {value} > maximum {schema['max']}")
                except (ValueError, TypeError):
                    errors.append(f"{field}: Expected integer, got {type(value).__name__}")
                    
            elif schema["type"] == "boolean":
                try:
                    value = int(value)
                    if value not in [0, 1]:
                        errors.append(f"{field}: Boolean must be 0 or 1, got {value}")
                except (ValueError, TypeError):
                    errors.append(f"{field}: Expected boolean (0/1), got {type(value).__name__}")
                    
            elif schema["type"] == "float":
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors.append(f"{field}: Expected float, got {type(value).__name__}")
    
    return errors

# ============================================
# STORE SCHEMA IN REDIS WITH RETRY
# ============================================
def store_schema_in_redis():
    """Store schema definition in Redis for consumers to reference with retry"""
    if not REDIS_AVAILABLE:
        return False
    
    for attempt in range(REDIS_RETRY_ATTEMPTS):
        try:
            redis_client.set(REDIS_SCHEMA_KEY, json.dumps(PHYSICAL_VALUES_SCHEMA, indent=2))
            
            for field, schema in PHYSICAL_VALUES_SCHEMA.items():
                redis_client.hset(f"{REDIS_SCHEMA_KEY}:fields", field, json.dumps(schema))
            
            logging.info("✓ Schema stored in Redis")
            return True
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logging.warning(f"⏳ Failed to store schema (attempt {attempt+1}/{REDIS_RETRY_ATTEMPTS}): {e}")
            if attempt < REDIS_RETRY_ATTEMPTS - 1:
                time.sleep(REDIS_RETRY_DELAY)
        except Exception as e:
            logging.error(f"Failed to store schema in Redis: {e}")
            return False
    
    logging.error("Failed to store schema in Redis after all retry attempts")
    return False

# ============================================
# REDIS STREAMING WITH VALIDATION AND RETRY
# ============================================
def redis_streamer(physical_values):
    """Stream physical values to Redis with schema validation and auto-reconnect"""
    if not REDIS_AVAILABLE:
        logging.info("→ Redis streamer not available with schema validation") 
        return  
        
    logging.info("→ Redis streamer started (0.2s interval) with schema validation")  
    
    # Store schema with retry
    store_schema_in_redis()
    
    error_count = 0
    last_error_log = time.time()
    reconnect_attempts = 0
    
    while True:
        try:
            # Check connection before each operation
            redis_client.ping()
            reconnect_attempts = 0
            
            telemetry = {
                "timestamp": time.time(),
                "timestamp_iso": time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                "timestamp_unix_ms": int(time.time() * 1000)
            }
            
            # Convert all values to Redis-compatible types
            for key, value in physical_values.items():
                try:
                    if value is None:
                        telemetry[key] = ""
                    elif isinstance(value, bool):
                        telemetry[key] = int(value)
                    elif isinstance(value, (int, float, str)):
                        telemetry[key] = value
                    elif isinstance(value, (dict, list, tuple, set)):
                        # Convert complex types to JSON string
                        try:
                            telemetry[key] = json.dumps(value)
                        except:
                            telemetry[key] = str(value)
                    else:
                        telemetry[key] = str(value)
                except Exception as e:
                    logging.error(f"Error converting key '{key}': {e}")
                    telemetry[key] = ""
            
            # Validate against schema
            validation_errors = validate_telemetry_data(telemetry)
            
            if validation_errors:
                error_count += 1
                if time.time() - last_error_log > 10:
                    logging.warning(f"Schema validation errors ({error_count} total):")
                    for err in validation_errors[:5]:
                        logging.warning(f"  • {err}")
                    last_error_log = time.time()
            
            # Add validation metadata as JSON string
            telemetry["_validation"] = json.dumps({
                "valid": len(validation_errors) == 0,
                "error_count": len(validation_errors),
                "schema_version": "1.0"
            })
            
            # Send to Redis
            redis_client.xadd(REDIS_STREAM, telemetry, maxlen=MAX_STREAM_LEN, approximate=True)
            redis_client.publish(REDIS_CHANNEL, json.dumps(telemetry, default=str))
            
            if len(validation_errors) == 0:
                redis_client.hset(REDIS_STATE_KEY, mapping=telemetry)
                redis_client.expire(REDIS_STATE_KEY, 3600)
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            reconnect_attempts += 1
            if reconnect_attempts <= REDIS_RETRY_ATTEMPTS:
                logging.warning(f"⚠ Redis connection lost, reconnecting ({reconnect_attempts}/{REDIS_RETRY_ATTEMPTS})...")
                time.sleep(REDIS_RETRY_DELAY)
                continue
            else:
                logging.error(f"❌ Redis connection lost permanently")
                break
                
        except Exception as e:
            logging.error(f"Redis stream error: {e}")
            
        time.sleep(0.2)

# FUNCTION: output_data
def output_data(physical_values, configs):
    """Write HIL outputs to database"""
    while True:
        try:
            # Get output physical values from config
            output_values = [pv for pv in configs["database"]["physical_values"] if pv["io"] == "output"]
            
            with sqlite3.connect('/src/physical_interactions.db') as conn:
                cursor = conn.cursor()
                
                for pv in output_values:
                    value = physical_values.get(pv["name"], "")
                    cursor.execute(
                        f"INSERT INTO {pv['name']}(value, hil) VALUES(?, ?)",
                        (str(value), 'bottle_factory')
                    )
                conn.commit()
        except Exception as e:
            logging.error(f"Error writing outputs: {e}")
        
        time.sleep(0.2)

# FUNCTION: input_data
def input_data(physical_values, configs):
    """Read actuator commands from database"""
    while True:
        try:
            # Get input physical values from config
            input_values = [pv for pv in configs["database"]["physical_values"] if pv["io"] == "input"]
            
            with sqlite3.connect('/src/physical_interactions.db') as conn:
                cursor = conn.cursor()
                
                for pv in input_values:
                    cursor.execute(
                        f"SELECT value FROM {pv['name']} ORDER BY timestamp DESC LIMIT 1"
                    )
                    result = cursor.fetchone()
                    if result:
                        physical_values[pv["name"]] = result[0]
        except Exception as e:
            logging.error(f"Error reading inputs: {e}")
        
        time.sleep(0.2)

# FUNCTION: verify that the schema is working
def verify_schema():
    if not REDIS_AVAILABLE:
        logging.warning("⚠ Redis not available - cannot verify schema")
        return
    
    logging.info("Verifying schema in Redis...")
    
    for attempt in range(REDIS_RETRY_ATTEMPTS):
        try:
            time.sleep(2)
            if redis_client.exists(REDIS_SCHEMA_KEY):
                logging.info(f"✓ Schema verified in Redis")
                return True
            else:
                logging.info(f"⏳ Schema not yet stored (attempt {attempt+1}/{REDIS_RETRY_ATTEMPTS})")
        except redis.ConnectionError:
            logging.warning(f"⏳ Redis connection lost during verification")
    
    logging.warning("⚠ Schema not found in Redis after all attempts")
    return False
    
    
# FUNCTION: main
async def main():
    configs = utils.retrieve_configs("config.json")
    logging.info(f"Starting HIL")

    physical_values = {}
    for value in configs["database"]["physical_values"]:
        physical_values[value["name"]] = ""

    logic_thread = Thread(target=logic.logic, args=(physical_values,))
    logic_thread.daemon = True
    logic_thread.start()
    
    db_in_thread = Thread(target=output_data, args=(physical_values, configs))
    db_in_thread.daemon = True
    db_in_thread.start()

    db_out_thread = Thread(target=input_data, args=(physical_values, configs))
    db_out_thread.daemon = True
    db_out_thread.start()
    
    redis_thread = Thread(target=redis_streamer, args=(physical_values,))
    redis_thread.daemon = True
    redis_thread.start()
    
    
    verify_schema()

    logic_thread.join()
    db_in_thread.join()
    db_out_thread.join()
    redis_thread.join()

if __name__ == "__main__":
    asyncio.run(main())
