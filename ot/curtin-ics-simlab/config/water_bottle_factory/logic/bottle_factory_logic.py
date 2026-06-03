import time
import math
import random
import logging
from threading import Thread
from pymodbus.client import ModbusTcpClient

# Physical constants for realistic simulation
GRAVITY = 9.81  # m/s²
PIPE_DIAMETER = 0.05  # meters
PIPE_AREA = math.pi * (PIPE_DIAMETER/2)**2  # m²
VALVE_CV = 12.0  # Flow coefficient
SUPPLY_PRESSURE = 2.5  # bar (water supply pressure)
MAX_TANK_LEVEL = 1000  # mm
MAX_FLOW_RATE = 15.0  # L/min (max possible flow)

def logic(physical_values):
    # Initial values
    physical_values["tank_level_value"] = 500
    physical_values["tank_input_valve_state"] = False
    physical_values["tank_output_valve_state"] = True
    physical_values["bottle_level_value"] = 0
    physical_values["bottle_distance_to_filler_value"] = 130
    physical_values["conveyor_belt_engine_state"] = False
    physical_values["tank_output_flow_value"] = 0.0
    physical_values["tank_input_flow_value"] = 0.0
    physical_values["plc1_mode"] = 1
    physical_values["plc2_mode"] = 1
    # Valve positions (0 = fully closed, 1 = fully open)
    physical_values["tank_input_valve_position"] = 0.0
    physical_values["tank_output_valve_position"] = 1.0
    # Pressure values
    physical_values["tank_pressure"] = 0.0
    physical_values["supply_pressure"] = SUPPLY_PRESSURE

    time.sleep(3)

    # Start all threads
    tank_thread = Thread(target=tank_valves_thread, args=(physical_values,), daemon=True)
    tank_thread.start()

    bottle_thread = Thread(target=bottle_filling_thread, args=(physical_values,), daemon=True)
    bottle_thread.start()
    
    flow_thread = Thread(target=flow_monitoring_thread, args=(physical_values,), daemon=True)
    flow_thread.start()
    
    pressure_thread = Thread(target=pressure_simulation_thread, args=(physical_values,), daemon=True)
    pressure_thread.start()
    
    valve_position_thread = Thread(target=valve_position_simulation_thread, args=(physical_values,), daemon=True)
    valve_position_thread.start()
    
    plc1_mode_thread = Thread(target=plc1_mode_monitor_thread, args=(physical_values,), daemon=True)
    plc1_mode_thread.start()
    
    plc2_mode_thread = Thread(target=plc2_mode_monitor_thread, args=(physical_values,), daemon=True)
    plc2_mode_thread.start()

    # Block
    tank_thread.join()
    bottle_thread.join()
    flow_thread.join()
    pressure_thread.join()
    valve_position_thread.join()
    plc1_mode_thread.join()
    plc2_mode_thread.join()

def calculate_flow_rate(delta_pressure, valve_position, is_input=False):
    """
    Calculate flow rate based on pressure difference and valve position
    Using simplified orifice flow equation: Q = Cv * A * sqrt(2 * ΔP / ρ)
    
    Args:
        delta_pressure: Pressure difference across valve (bar)
        valve_position: 0-1, how open the valve is
        is_input: True for input valve (supply to tank), False for output valve (tank to bottle)
    
    Returns:
        Flow rate in L/min
    """
    if valve_position <= 0:
        return 0.0
    
    # Convert bar to Pa (Pascals)
    delta_pressure_pa = delta_pressure * 100000
    
    # Water density (kg/m³)
    water_density = 1000
    
    # Calculate flow velocity using Torricelli's law with valve coefficient
    if delta_pressure_pa <= 0:
        return 0.0
    
    # Flow velocity = Cv * valve_position * sqrt(2 * ΔP / ρ)
    velocity = VALVE_CV * valve_position * math.sqrt(2 * delta_pressure_pa / water_density)
    
    # Flow rate = velocity * area (convert to L/min: m³/s * 1000 * 60)
    flow_rate = velocity * PIPE_AREA * 1000 * 60
    
    # Cap at realistic maximum
    return min(flow_rate, MAX_FLOW_RATE)

def tank_valves_thread(physical_values):
    last_log_time = time.time()
    
    while True:
        # Get current valve positions and states
        input_valve_state = int(physical_values.get("tank_input_valve_state", 0))
        output_valve_state = int(physical_values.get("tank_output_valve_state", 0))
        input_valve_pos = float(physical_values.get("tank_input_valve_position", 0.0))
        output_valve_pos = float(physical_values.get("tank_output_valve_position", 1.0))
        
        # Calculate input flow
        if input_valve_state == 1:
            tank_pressure = physical_values["tank_pressure"]
            delta_p = max(0, SUPPLY_PRESSURE - tank_pressure)
            inflow_rate = calculate_flow_rate(delta_p, input_valve_pos, is_input=True)
            physical_values["tank_input_flow_value"] = inflow_rate
        else:
            inflow_rate = 0.0
            physical_values["tank_input_flow_value"] = 0.0
        
        # Calculate output flow
        if output_valve_state == 1:
            tank_pressure = physical_values["tank_pressure"]
            outflow_rate = calculate_flow_rate(tank_pressure, output_valve_pos, is_input=False)
            physical_values["tank_output_flow_value"] = outflow_rate
        else:
            outflow_rate = 0.0
            physical_values["tank_output_flow_value"] = 0.0
        
        # Calculate deltas
        inflow_delta = inflow_rate * (0.6 / 60)
        outflow_delta = outflow_rate * (0.6 / 60)
        
        # Update level - ONLY ONCE
        old_level = physical_values["tank_level_value"]
        new_level = old_level + inflow_delta - outflow_delta
        physical_values["tank_level_value"] = max(0, min(MAX_TANK_LEVEL, new_level))
        
        time.sleep(0.6)

def bottle_filling_thread(physical_values):
    while True:
        # Convert string to int
        output_valve_state = int(physical_values.get("tank_output_valve_state", 0))
        conveyor_state = int(physical_values.get("conveyor_belt_engine_state", 0))
        
        if output_valve_state == 1:
            if (physical_values["bottle_distance_to_filler_value"] >= 0 and 
                physical_values["bottle_distance_to_filler_value"] <= 30):
                flow_rate = physical_values["tank_output_flow_value"]
                fill_increment = flow_rate * (0.6 / 60) * 30
                physical_values["bottle_level_value"] += fill_increment
        
        if conveyor_state == 1:
            physical_values["bottle_distance_to_filler_value"] -= 4
            if physical_values["bottle_distance_to_filler_value"] < 0:
                physical_values["bottle_distance_to_filler_value"] = 130
                physical_values["bottle_level_value"] = 0
        
        time.sleep(0.6)
        
def pressure_simulation_thread(physical_values):
    """
    Simulate hydrostatic pressure in the tank
    Pressure increases with water level: P = ρgh
    """
    while True:
        # Convert tank level (mm) to pressure (bar)
        # 10 meters of water ≈ 1 bar, so 1000mm = 0.1 bar
        tank_pressure = (physical_values["tank_level_value"] / 1000) * 0.098  # bar
        physical_values["tank_pressure"] = tank_pressure
        
        time.sleep(0.5)

def valve_position_simulation_thread(physical_values):
    INPUT_VALVE_SPEED = 0.3
    OUTPUT_VALVE_SPEED = 0.25
    
    while True:
        # Convert to int for comparison
        target_input = 1.0 if int(physical_values.get("tank_input_valve_state", 0)) == 1 else 0.0
        current_input = float(physical_values.get("tank_input_valve_position", 0.0))
        
        if current_input < target_input:
            physical_values["tank_input_valve_position"] = min(
                target_input, 
                current_input + INPUT_VALVE_SPEED * 0.1
            )
        elif current_input > target_input:
            physical_values["tank_input_valve_position"] = max(
                target_input, 
                current_input - INPUT_VALVE_SPEED * 0.1
            )
        
        target_output = 1.0 if int(physical_values.get("tank_output_valve_state", 0)) == 1 else 0.0
        current_output = float(physical_values.get("tank_output_valve_position", 1.0))
        
        if current_output < target_output:
            physical_values["tank_output_valve_position"] = min(
                target_output, 
                current_output + OUTPUT_VALVE_SPEED * 0.1
            )
        elif current_output > target_output:
            physical_values["tank_output_valve_position"] = max(
                target_output, 
                current_output - OUTPUT_VALVE_SPEED * 0.1
            )
        
        time.sleep(0.1)

def flow_monitoring_thread(physical_values):
    """
    Monitor and log flow rates with realistic dynamics
    """
    while True:
        # Input flow is already calculated in tank_valves_thread
        # Just add small noise for realism
        input_flow = physical_values["tank_input_flow_value"]
        output_flow = physical_values["tank_output_flow_value"]
        
        # Add turbulence/noise (small random fluctuations)
        if input_flow > 0:
            physical_values["tank_input_flow_value"] = max(0, input_flow + random.uniform(-0.2, 0.2))
        if output_flow > 0:
            physical_values["tank_output_flow_value"] = max(0, output_flow + random.uniform(-0.2, 0.2))
        
        time.sleep(0.1)

def plc1_mode_monitor_thread(physical_values):
    """Monitor PLC mode from PLC1 via Modbus TCP"""
    plc1_client = None
    last_mode = 1
    
    while True:
        try:
            if plc1_client is None or not plc1_client.is_socket_open():
                plc1_client = ModbusTcpClient('192.168.0.21', port=502)
                plc1_client.connect()
                if not plc1_client.is_socket_open():
                    time.sleep(2)
                    continue
            
            # Read holding register 199 (address 200) for PLC1
            result = plc1_client.read_holding_registers(199, count=1)  # address-1 = 199
            if result and not result.isError():
                current_mode = result.registers[0]
                physical_values["plc1_mode"] = current_mode
                
                if current_mode != last_mode:
                    mode_names = {1: "RUN", 2: "PROGRAM", 3: "REMOTE", 4: "STOP"}
                    logging.info(f"PLC1 mode changed: {mode_names.get(last_mode, last_mode)} → {mode_names.get(current_mode, current_mode)}")
                    last_mode = current_mode
            
        except Exception as e:
            logging.debug(f"PLC 1 mode read error: {e}")
        
        time.sleep(0.5)

def plc2_mode_monitor_thread(physical_values):
    """Monitor PLC mode from PLC2 via Modbus TCP"""
    plc2_client = None
    last_mode = 1
    
    while True:
        try:
            if plc2_client is None or not plc2_client.is_socket_open():
                plc2_client = ModbusTcpClient('192.168.0.22', port=502)
                plc2_client.connect()
                if not plc2_client.is_socket_open():
                    time.sleep(2)
                    continue
            
            # Read holding register 99 (address 100) for PLC2
            result = plc2_client.read_holding_registers(99, count=1)  # address-1 = 99
            if result and not result.isError():
                current_mode = result.registers[0]
                physical_values["plc2_mode"] = current_mode
                
                if current_mode != last_mode:
                    mode_names = {1: "RUN", 2: "PROGRAM", 3: "REMOTE", 4: "STOP"}
                    logging.info(f"PLC2 mode changed: {mode_names.get(last_mode, last_mode)} → {mode_names.get(current_mode, current_mode)}")
                    last_mode = current_mode
            
        except Exception as e:
            logging.debug(f"PLC 2 mode read error: {e}")
        
        time.sleep(0.5)
