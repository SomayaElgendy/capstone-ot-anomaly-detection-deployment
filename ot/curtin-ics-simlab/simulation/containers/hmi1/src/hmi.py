#!/usr/bin/env python3

# FILE PURPOSE: Implements the functionality of a Human Machine Interface device (HMI)

import asyncio
import time
import random
import logging
import utils
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusDeviceContext, ModbusServerContext
from pymodbus.client.base import ModbusBaseClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)

# global variables (only used for endpoints)
register_values = {}

# ============================================
# HMI TYPE DEFINITIONS
# ============================================
HMI_TYPE_READONLY = "readonly"      # HMI1 - original behavior (monitors only)
HMI_TYPE_PREDEFINED = "predefined"  # HMI2 - follows a scenario
HMI_TYPE_ATTACKER = "attacker"      # HMI3 - stealth attacker that slows down process

# ============================================
# CONTROLLER FUNCTION FOR PREDEFINED SCENARIO (HMI2)
# ============================================

def predefined_scenario_controller(configs, outbound_cons):
    """Execute realistic scenario writes to PLCs with random intervals"""
    logging.info("Starting Predefined Scenario Controller (HMI2)")
    
    # Wait for PLC2 connection to be ready
    plc2_ready = False
    
    for attempt in range(10):
        try:
            if "plc2_con" in outbound_cons:
                client2 = outbound_cons["plc2_con"]
                client2.read_coils(0, count=1)
                plc2_ready = True
                logging.info("HMI2: PLC2 connection ready")
                break
        except:
            pass
        
        logging.info(f"HMI2: Waiting for connection PLC2... (attempt {attempt+1}/10)")
        time.sleep(2)
    
    if not plc2_ready:
        logging.warning("HMI2: Could not connect to PLC2 - continuing anyway")
    
    while True:
        # Wait random time between 15-40 minutes
        wait_minutes = random.uniform(15, 40)
        logging.info(f"HMI2: Normal operation for {wait_minutes:.1f} minutes")
        time.sleep(wait_minutes * 60)
        
        # Remote mode duration (5-15 seconds)
        remote_duration = random.uniform(5, 15)
        logging.info(f"HMI2: Remote mode for {remote_duration:.1f} seconds")
        
        # ============================================
        # 1. TURN ON REMOTE MODE
        # ============================================
        if "plc2_con" in outbound_cons:
            outbound_cons["plc2_con"].write_coil(49, True)  # remote_request ON (coil 50)
            logging.info("HMI2: REMOTE MODE request sent to PLC2")
        
        time.sleep(remote_duration)
        
        # ============================================
        # 2. TURN OFF REMOTE MODE AND SEND RESUME
        # ============================================
        logging.info("HMI2: Ending remote mode and sending RESUME command")
        
        # First, turn OFF remote_request (coil 50)
        if "plc2_con" in outbound_cons:
            outbound_cons["plc2_con"].write_coil(49, False)  # remote_request OFF
        
        # Then send resume command (coil 51)
        if "plc2_con" in outbound_cons:
            outbound_cons["plc2_con"].write_coil(50, True)   # resume_request ON
            logging.info("HMI2: RESUME command sent to PLC2")
        
        time.sleep(1)
        
        # ============================================
        # 3. TURN OFF RESUME COMMAND
        # ============================================
        if "plc2_con" in outbound_cons:
            outbound_cons["plc2_con"].write_coil(50, False)  # resume_request OFF

def stealth_attacker_controller(configs, outbound_cons):
    """
    HMI3 Mode Detection - Monitors PLC operating modes for changes
    """
    logging.info("=" * 60)
    logging.info("🔍 HMI3 MODE DETECTION STARTED - Monitoring PLC operating modes 🔍")
    logging.info("=" * 60)
    
    PLC1_MODE_REGISTER = 200
    PLC2_MODE_REGISTER = 100
    
    MODE_NAMES = {1: "RUN", 2: "PROGRAM", 3: "REMOTE", 4: "STOP"}
    
    plc1_last_mode = None
    plc2_last_mode = None
    
    # Wait for connections to BOTH PLCs
    plc1_ready = False
    plc2_ready = False
    
    for attempt in range(10):
        try:
            if "plc1_con" in outbound_cons:
                client = outbound_cons["plc1_con"]
                client.read_coils(0, count=1)
                plc1_ready = True
                logging.info("✓ Connected to PLC1")
        except:
            pass
        
        try:
            if "plc2_con" in outbound_cons:
                client = outbound_cons["plc2_con"]
                client.read_coils(0, count=1)
                plc2_ready = True
                logging.info("✓ Connected to PLC2")
        except:
            pass
        
        if plc1_ready and plc2_ready:
            break
        time.sleep(2)
    
    # Read initial modes from PLC1
    if plc1_ready:
        try:
            client = outbound_cons["plc1_con"]
            result = client.read_holding_registers(PLC1_MODE_REGISTER - 1, count=1)
            if result and not result.isError():
                plc1_last_mode = result.registers[0]
                logging.info(f"📊 Initial PLC1 mode: {MODE_NAMES.get(plc1_last_mode, 'UNKNOWN')} ({plc1_last_mode})")
        except Exception as e:
            logging.error(f"Error reading PLC1 initial mode: {e}")
    
    # Read initial modes from PLC2
    if plc2_ready:
        try:
            client = outbound_cons["plc2_con"]
            result = client.read_holding_registers(PLC2_MODE_REGISTER - 1, count=1)
            if result and not result.isError():
                plc2_last_mode = result.registers[0]
                logging.info(f"📊 Initial PLC2 mode: {MODE_NAMES.get(plc2_last_mode, 'UNKNOWN')} ({plc2_last_mode})")
        except Exception as e:
            logging.error(f"Error reading PLC2 initial mode: {e}")
    
    logging.info("=" * 60)
    logging.info("🔍 Monitoring active - will log when PLC modes change")
    logging.info("=" * 60)
    
    last_log_time = time.time()
    
    while True:
        try:
            # Read PLC1 mode using plc1_con
            if plc1_ready:
                client = outbound_cons["plc1_con"]
                result = client.read_holding_registers(PLC1_MODE_REGISTER - 1, count=1)
                if result and not result.isError():
                    current_plc1 = result.registers[0]
                    if plc1_last_mode is not None and current_plc1 != plc1_last_mode:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        logging.warning(f"🔔 PLC1 MODE CHANGE at {timestamp}")
                        logging.warning(f"   PLC1: {MODE_NAMES.get(plc1_last_mode, plc1_last_mode)} → {MODE_NAMES.get(current_plc1, current_plc1)}")
                    plc1_last_mode = current_plc1
            
            # Read PLC2 mode using plc2_con
            if plc2_ready:
                client = outbound_cons["plc2_con"]
                result = client.read_holding_registers(PLC2_MODE_REGISTER - 1, count=1)
                if result and not result.isError():
                    current_plc2 = result.registers[0]
                    if plc2_last_mode is not None and current_plc2 != plc2_last_mode:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        logging.warning(f"🔔 PLC2 MODE CHANGE at {timestamp}")
                        logging.warning(f"   PLC2: {MODE_NAMES.get(plc2_last_mode, plc2_last_mode)} → {MODE_NAMES.get(current_plc2, current_plc2)}")
                    plc2_last_mode = current_plc2
            
            # Log current modes periodically (every 30 seconds)
            if time.time() - last_log_time >= 30:
                logging.info(f"📊 Current modes - PLC1: {MODE_NAMES.get(plc1_last_mode, 'UNKNOWN')} | PLC2: {MODE_NAMES.get(plc2_last_mode, 'UNKNOWN')}")
                last_log_time = time.time()
            
            time.sleep(0.5)
            
        except Exception as e:
            logging.error(f"Mode detection error: {e}")
            time.sleep(5)
            
# ============================================
# HMI FRAMEWORK FUNCTIONS
# ============================================

# FUNCTION: init_inbound_cons
async def init_inbound_cons(configs, context):
    server_tasks = []
    for connection in configs["inbound_connections"]:
        if connection["type"] == "tcp":            
            server_tasks.append(asyncio.create_task(utils.run_tcp_server(connection, context)))
        elif connection["type"] == "rtu":
            server_tasks.append(asyncio.create_task(utils.run_rtu_slave(connection, context))) 
    for task in server_tasks:
        await task


# FUNCTION: init_outbound_cons
def init_outbound_cons(configs):
    connections = {}
    for connection in configs["outbound_connections"]:
        time.sleep(0.75)
        if connection["type"] == "tcp":
            client = utils.run_tcp_client(connection)
            connections[connection["id"]] = client
        elif connection["type"] == "rtu":
            client = utils.run_rtu_master(connection)
            connections[connection["id"]] = client
    return connections


# FUNCTION: monitor
def monitor(value_config, monitor_configs, modbus_con, values):
    logging.info(f"Starting Monitor: {monitor_configs['id']}")
    interval = monitor_configs["interval"]
    value_type = monitor_configs["value_type"]
    out_address = monitor_configs["address"]
    count = monitor_configs["count"]

    while True:
        try:
            if value_type == "coil":
                response_values = modbus_con.read_coils(out_address-1, count=count).bits
                values["co"].setValues(value_config["address"], response_values)
            elif value_type == "discrete_input":
                response_values = modbus_con.read_discrete_inputs(out_address-1, count=count).bits
                values["di"].setValues(value_config["address"], response_values)
            elif value_type == "holding_register":
                response_values = modbus_con.read_holding_registers(out_address-1, count=count).registers
                values["hr"].setValues(value_config["address"], response_values)
            elif value_type == "input_register":
                response_values = modbus_con.read_input_registers(out_address-1, count=count).registers
                values["ir"].setValues(value_config["address"], response_values)
        except:
            logging.error("Error: couldn't read values")

        time.sleep(interval)


# FUNCTION: start_monitors
def start_monitors(configs, outbound_cons, values):
    monitor_threads = []
    for monitor_config in configs["monitors"]:
        outbound_con_id = monitor_config["outbound_connection_id"]
        modbus_con = outbound_cons[outbound_con_id]

        value_config = {}
        if monitor_config["value_type"] == "coil":
            for co in configs["registers"]["coil"]:
                if co["id"] == monitor_config["id"]:
                    value_config = co
        elif monitor_config["value_type"] == "discrete_input":
            for di in configs["registers"]["discrete_input"]:
                if di["id"] == monitor_config["id"]:
                    value_config = di
        elif monitor_config["value_type"] == "holding_register":
            for hr in configs["registers"]["holding_register"]:
                if hr["id"] == monitor_config["id"]:
                    value_config = hr
        elif monitor_config["value_type"] == "input_register":
            for ir in configs["registers"]["input_register"]:
                if ir["id"] == monitor_config["id"]:
                    value_config = ir

        monitor_thread = Thread(target=monitor, args=(value_config, monitor_config, modbus_con, values), daemon=True)
        monitor_thread.start()
        monitor_threads.append(monitor_thread)
    return monitor_threads


# define the flask endpoint
@app.route("/registers", methods=['GET'])
def get_registers_route():
    global register_values
    return jsonify(register_values)


# define function to run flask in another thread
def flask_app(flask_app):
    flask_app.run(host="0.0.0.0", port=1111)


# FUNCTION: get_hmi_type
def get_hmi_type(configs):
    return configs.get("hmi_type", HMI_TYPE_READONLY)


# FUNCTION: main
async def main():
    global register_values
    
    configs = utils.retrieve_configs("config.json")
    
    hmi_type = get_hmi_type(configs)
    logging.info(f"Starting HMI - Type: {hmi_type}")

    co = ModbusSequentialDataBlock.create()
    di = ModbusSequentialDataBlock.create()
    hr = ModbusSequentialDataBlock.create()
    ir = ModbusSequentialDataBlock.create()
    device_context = ModbusDeviceContext(co=co, di=di, hr=hr, ir=ir)
    context = ModbusServerContext(devices=device_context, single=True)

    values = {"co": co, "di": di, "hr": hr, "ir": ir}
    inbound_cons = asyncio.create_task(init_inbound_cons(configs, context))

    outbound_cons = init_outbound_cons(configs)

    monitor_threads = start_monitors(configs, outbound_cons, values)

    register_values = utils.create_register_values_dict(configs)

    # ============================================
    # START HMI-SPECIFIC CONTROLLERS
    # ============================================
    controller_threads = []
    
    if hmi_type == HMI_TYPE_PREDEFINED:
        controller = Thread(target=predefined_scenario_controller, 
                          args=(configs, outbound_cons), daemon=True)
        controller.start()
        controller_threads.append(controller)
        logging.info("✓ Predefined scenario controller started")
        
    elif hmi_type == HMI_TYPE_ATTACKER:
        # Start stealth attacker controller (HMI3)
        controller = Thread(target=stealth_attacker_controller, 
                          args=(configs, outbound_cons), daemon=True)
        controller.start()
        controller_threads.append(controller)
        logging.info("✓ Stealth attacker controller started")
    
    # For HMI_TYPE_READONLY (HMI1), only monitors - no controller needed
    # ============================================

    sync_registers = Thread(target=utils.update_register_values, args=(register_values, values), daemon=True)
    sync_registers.start()
    
    flask_thread = Thread(target=flask_app, args=(app,), daemon=True)
    flask_thread.start()

    await inbound_cons
    for monitor_thread in monitor_threads:
        monitor_thread.join()
    for controller_thread in controller_threads:
        controller_thread.join()
    for outbound_con in outbound_cons.values():
        outbound_con.close()
    sync_registers.join()
    flask_thread.join()

    while True:
        time.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
