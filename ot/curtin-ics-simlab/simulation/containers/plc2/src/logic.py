import time
import logging
from pymodbus.client import ModbusTcpClient

# ============================================
# PLC OPERATING MODES
# ============================================
PLC_MODE_RUN = 1
PLC_MODE_PROGRAM = 2
PLC_MODE_REMOTE = 3
PLC_MODE_STOP = 4

PLC_MODE_NAMES = {
    PLC_MODE_RUN: "RUN",
    PLC_MODE_PROGRAM: "PROGRAM",
    PLC_MODE_REMOTE: "REMOTE",
    PLC_MODE_STOP: "STOP"
}

class ModeManager:
    def __init__(self):
        self.current_mode = PLC_MODE_RUN
        self.mode_start_time = time.time()
        
        # Production tracking
        self.bottles_filled = 0
        self.last_maintenance_bottles = 0
        
        # Thresholds
        self.maintenance_interval = 200
        self.emergency_bottle_level_max = 220
        self.emergency_enter_time = None
        
        # ============================================
        # MODE DURATIONS (seconds)
        # ============================================
        self.program_mode_duration = 15    # Maintenance/Programming
        self.remote_mode_duration = 15     # Remote control timeout
        self.stop_mode_auto_resume = True  # Auto resume from stop if conditions met
        self.emergency_stop_duration = 3
        
        # Track pending requests
        self.pending_remote_request = False
    
    def update(self, bottle_level, bottle_distance, remote_request, resume_request):
        
        # Track bottle completions
        if bottle_level > 180 and bottle_distance < 30:
            self.bottles_filled += 1
        
        # ============================================
        # 1. EMERGENCY STOP (HIGHEST PRIORITY)
        # ============================================
        if bottle_level > self.emergency_bottle_level_max:
            if self.current_mode != PLC_MODE_STOP:
                self._change_mode(PLC_MODE_STOP, f"Emergency - bottle overfill {bottle_level}")
                self.emergency_enter_time = time.time()  # Record when emergency started
                print(f"DEBUG: EMERGENCY mode entered at {self.emergency_enter_time}")
            return self.current_mode
        
        # ============================================
        # 2. HANDLE STOP MODE - Check if emergency cleared
        # ============================================
        if self.current_mode == PLC_MODE_STOP:
            # Check if we have an emergency timer running
            if self.emergency_enter_time:
                emergency_duration = time.time() - self.emergency_enter_time
                print(f"DEBUG: Emergency mode active for {emergency_duration:.1f}s / {self.emergency_stop_duration}s")
                
                # Auto-exit after exactly 3 seconds, regardless of bottle level
                if emergency_duration >= self.emergency_stop_duration:
                    self._change_mode(PLC_MODE_RUN, f"Emergency mode auto-exit after {self.emergency_stop_duration} seconds")
                    self.emergency_enter_time = None  # Reset emergency timer
                    return self.current_mode
            return self.current_mode
        
        # ============================================
        # 3. MAINTENANCE (PROGRAM MODE)
        # ============================================
        if (self.bottles_filled - self.last_maintenance_bottles) >= self.maintenance_interval:
            if self.current_mode == PLC_MODE_RUN:
                self._change_mode(PLC_MODE_PROGRAM, f"Maintenance - {self.maintenance_interval} bottles")
                self.last_maintenance_bottles = self.bottles_filled
                print(f"DEBUG: Entered PROGRAM mode at {time.time()}, mode_start_time={self.mode_start_time}") 
                if remote_request == 1:
                    self.pending_remote_request = True
            return self.current_mode

        # ============================================
        # 4. AUTO-EXIT PROGRAM MODE
        # ============================================
        if self.current_mode == PLC_MODE_PROGRAM:
            elapsed = time.time() - self.mode_start_time
            logging.debug(f"DEBUG: PROGRAM mode elapsed={elapsed:.1f}s, duration={self.program_mode_duration}s") 
            if elapsed >= self.program_mode_duration:
                self._change_mode(PLC_MODE_RUN, "Maintenance complete")
                print("DEBUG: PROGRAM mode exited")
                if self.pending_remote_request:
                    self.pending_remote_request = False
                    self._change_mode(PLC_MODE_REMOTE, "Queued remote request executed")
            return self.current_mode 
        
        # ============================================
        # 5. REMOTE MODE (HMI triggered)
        # ============================================
        if remote_request == 1 and self.current_mode == PLC_MODE_RUN:
            print(f"DEBUG ModeManager: REMOTE CONDITION MET! remote_request={remote_request}, current_mode={self.current_mode}")
            self._change_mode(PLC_MODE_REMOTE, "Remote mode requested")
            return self.current_mode
        
        # ============================================
        # 6. AUTO-EXIT REMOTE MODE (timeout)
        # ============================================
        if self.current_mode == PLC_MODE_REMOTE:
            if time.time() - self.mode_start_time >= self.remote_mode_duration:
                self._change_mode(PLC_MODE_RUN, "Remote mode timeout - returning to run")
                if self.pending_remote_request:
                    self.pending_remote_request = False
            return self.current_mode
        
        # ============================================
        # 7. RETURN TO RUN (manual resume from remote)
        # ============================================
        if self.current_mode == PLC_MODE_REMOTE and resume_request == 1:
            print("DEBUG: Resume request received while in REMOTE mode")
            self._change_mode(PLC_MODE_RUN, "Resuming normal operation")
            return self.current_mode
        
        return self.current_mode
    
    def _change_mode(self, new_mode, reason):
        if new_mode != self.current_mode:
            old_mode = self.current_mode
            self.current_mode = new_mode
            self.mode_start_time = time.time()
            logging.info(f"PLC2 mode: {PLC_MODE_NAMES[old_mode]} → {PLC_MODE_NAMES[new_mode]} - {reason}")
            
    def logic_executing(self):
        """Returns True if control logic should run"""
        return self.current_mode in [PLC_MODE_RUN, PLC_MODE_REMOTE, PLC_MODE_PROGRAM]
    
    def outputs_enabled(self):
        """Returns True if physical outputs should be energized"""
        return self.current_mode in [PLC_MODE_RUN, PLC_MODE_REMOTE]

# ============================================
# MAIN PLC2 LOGIC
# ============================================
def logic(input_registers, output_registers, state_update_callbacks):
    time.sleep(10)
    mode_mgr = ModeManager()
    
    bottle_level_ref = input_registers["bottle_level"]
    bottle_distance_to_filler_ref = input_registers["bottle_distance_to_filler"]
    conveyor_engine_state_ref = output_registers["conveyor_engine_state"]
    plc1_tank_output_state_ref = output_registers["plc1_tank_output_state"]
    

    remote_request_ref = output_registers.get("remote_request", None)
    resume_request_ref = output_registers.get("resume_request", None)

    plc_mode_ref = output_registers.get("plc2_mode", None)
    
    # Initial writing
    conveyor_engine_state_ref["value"] = False
    state_update_callbacks["conveyor_engine_state"]()   
    plc1_tank_output_state_ref["value"] = True
    state_update_callbacks["plc1_tank_output_state"]()
    
    if plc_mode_ref:
        plc_mode_ref["value"] = PLC_MODE_RUN
        state_update_callbacks["plc2_mode"]()
    
    time.sleep(2)
    
    # ============================================
    # WAIT FOR PLC1 TO BE READY
    # ============================================
    logging.info("PLC2: Waiting for PLC1 to become available...")
    plc1_ready = False
    for attempt in range(10):  # Try 10 times
        try:
            # Try to read a simple coil from PLC1 to test connection
            test_client = ModbusTcpClient('192.168.0.21', port=502)
            test_client.connect()
            if test_client.is_socket_open():
                test_client.close()
                plc1_ready = True
                logging.info("PLC2: PLC1 is now available")
                break
        except:
            pass
        logging.info(f"PLC2: Waiting for PLC1... attempt {attempt+1}/10")
        time.sleep(2)
    
    if not plc1_ready:
        logging.warning("PLC2: Could not connect to PLC1 - will retry during operation")
    
    state = "ready"
    
    while True:
        bottle_level = bottle_level_ref["value"]
        bottle_distance = bottle_distance_to_filler_ref["value"]
        remote_request = remote_request_ref["value"] if remote_request_ref else 0
        resume_request = resume_request_ref["value"] if resume_request_ref else 0
        
        # Update mode with bottle count
        current_mode = mode_mgr.update(bottle_level, bottle_distance, remote_request, resume_request)
        
        
        if plc_mode_ref:
            if current_mode in [PLC_MODE_RUN, PLC_MODE_PROGRAM, PLC_MODE_REMOTE, PLC_MODE_STOP]:
                plc_mode_ref["value"] = current_mode
                state_update_callbacks["plc2_mode"]()
        
        if mode_mgr.logic_executing():
            if state == "ready":
                plc1_tank_output_state_ref["value"] = True
                state_update_callbacks["plc1_tank_output_state"]()
                conveyor_engine_state_ref["value"] = False
                state_update_callbacks["conveyor_engine_state"]()
                state = "filling"

            if bottle_distance_to_filler_ref["value"] > 30 and state == "filling": 
                plc1_tank_output_state_ref["value"] = False
                state_update_callbacks["plc1_tank_output_state"]()
                conveyor_engine_state_ref["value"] = True
                state_update_callbacks["conveyor_engine_state"]()
                state = "moving"

            if bottle_level_ref["value"] >= 180 and state == "filling":
                plc1_tank_output_state_ref["value"] = False
                state_update_callbacks["plc1_tank_output_state"]()
                conveyor_engine_state_ref["value"] = True
                state_update_callbacks["conveyor_engine_state"]()
                state = "moving"

            if state == "moving":
                if bottle_distance_to_filler_ref["value"] >= 0 and bottle_distance_to_filler_ref["value"] <= 30:
                    if bottle_level_ref["value"] == 0:
                        state = "ready"

        
        time.sleep(0.1)
