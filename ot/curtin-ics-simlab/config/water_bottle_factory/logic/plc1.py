import time
import logging

# ============================================
# PLC OPERATING MODES
# ============================================
PLC_MODE_RUN = 1
PLC_MODE_PROGRAM = 2
PLC_MODE_STOP = 4

PLC_MODE_NAMES = {
    PLC_MODE_RUN: "RUN",
    PLC_MODE_PROGRAM: "PROGRAM",
    PLC_MODE_STOP: "STOP"
}

class ModeManager:
    def __init__(self, tank_input_valve_ref, state_update_callbacks):
        self.current_mode = PLC_MODE_RUN
        self.mode_start_time = time.time()

        self.tank_input_valve_ref = tank_input_valve_ref
        self.state_update_callbacks = state_update_callbacks

        self.fill_cycles = 0
        self.drain_cycles = 0
        self.total_cycles = 0
        self.last_maintenance_cycles = 0

        self.maintenance_interval = 1

        self.emergency_level_min = 50
        self.emergency_level_max = 950

        self.program_mode_duration = 15

        self.waiting_for_fill = False
        self.waiting_for_drain = False

    def update(self, tank_level):
        # ============================================
        # DETECT FILL/DRAIN CYCLE COMPLETION
        # ============================================
        if not self.waiting_for_fill and tank_level < 300:
            self.waiting_for_fill = True
            print(f"DEBUG PLC1: Tank going low (level={tank_level:.1f}), waiting for fill...")

        if self.waiting_for_fill and tank_level > 500:
            self.fill_cycles += 1
            self.total_cycles += 1
            self.waiting_for_fill = False
            print(f"DEBUG PLC1: Fill cycle #{self.fill_cycles} completed | total_cycles={self.total_cycles} | next maintenance at {self.last_maintenance_cycles + self.maintenance_interval}")

        if not self.waiting_for_drain and tank_level > 500:
            self.waiting_for_drain = True
            print(f"DEBUG PLC1: Tank going high (level={tank_level:.1f}), waiting for drain...")

        if self.waiting_for_drain and tank_level < 300:
            self.drain_cycles += 1
            self.total_cycles += 1
            self.waiting_for_drain = False
            print(f"DEBUG PLC1: Drain cycle #{self.drain_cycles} completed | total_cycles={self.total_cycles} | next maintenance at {self.last_maintenance_cycles + self.maintenance_interval}")

        # ============================================
        # 1. EMERGENCY STOP (HIGHEST PRIORITY)
        # ============================================
        if tank_level < self.emergency_level_min or tank_level > self.emergency_level_max:
            if self.current_mode != PLC_MODE_STOP:
                self._change_mode(PLC_MODE_STOP, f"Emergency - tank level {tank_level}")
            return self.current_mode

        # ============================================
        # 2. HANDLE STOP MODE
        # ============================================
        if self.current_mode == PLC_MODE_STOP:
            if tank_level >= self.emergency_level_min and tank_level <= self.emergency_level_max:
                self._change_mode(PLC_MODE_RUN, "Emergency cleared - resuming")
            return self.current_mode

        # ============================================
        # 3. AUTO-EXIT PROGRAM MODE
        # ============================================
        if self.current_mode == PLC_MODE_PROGRAM:
            elapsed = time.time() - self.mode_start_time
            if elapsed >= self.program_mode_duration:
                self._change_mode(PLC_MODE_RUN, "Maintenance complete")
            return self.current_mode

        # ============================================
        # 4. MAINTENANCE CHECK
        # ============================================
        if self.maintenance_interval > 0 and (self.total_cycles - self.last_maintenance_cycles) >= self.maintenance_interval:
            print(f"DEBUG PLC1: Maintenance threshold reached! total_cycles={self.total_cycles}, last_maintenance={self.last_maintenance_cycles}")
            if self.current_mode == PLC_MODE_RUN:
                self._change_mode(PLC_MODE_PROGRAM, f"Scheduled maintenance after {self.maintenance_interval} cycles")
                self.last_maintenance_cycles = self.total_cycles
            return self.current_mode

        return self.current_mode

    def _change_mode(self, new_mode, reason):
        if new_mode != self.current_mode:
            old_mode = self.current_mode
            self.current_mode = new_mode
            self.mode_start_time = time.time()
            logging.info(f"PLC1 mode: {PLC_MODE_NAMES[old_mode]} → {PLC_MODE_NAMES[new_mode]} - {reason}")

            if new_mode == PLC_MODE_STOP:
                if self.tank_input_valve_ref:
                    self.tank_input_valve_ref["value"] = False
                    if "tank_input_valve_state" in self.state_update_callbacks:
                        self.state_update_callbacks["tank_input_valve_state"]()
                logging.info("PLC1 STOP: input valve closed, awaiting emergency clearance")

    def logic_executing(self):
        return self.current_mode in [PLC_MODE_RUN, PLC_MODE_PROGRAM]

    def outputs_enabled(self):
        return self.current_mode == PLC_MODE_RUN


# ============================================
# MAIN PLC1 LOGIC
# ============================================
def logic(input_registers, output_registers, state_update_callbacks):
    time.sleep(5)

    tank_level_ref = input_registers.get("tank_level", None)
    tank_input_valve_ref = output_registers.get("tank_input_valve_state", None)
    tank_output_valve_ref = output_registers.get("tank_output_valve_state", None)
    plc_mode_ref = output_registers.get("plc1_mode", None)

    mode_mgr = ModeManager(tank_input_valve_ref, state_update_callbacks)

    # Initial state
    if tank_input_valve_ref:
        tank_input_valve_ref["value"] = False
        state_update_callbacks["tank_input_valve_state"]()

    if tank_output_valve_ref:
        tank_output_valve_ref["value"] = False
        state_update_callbacks["tank_output_valve_state"]()

    if plc_mode_ref:
        plc_mode_ref["value"] = PLC_MODE_RUN
        state_update_callbacks["plc1_mode"]()

    time.sleep(2)

    print(f"DEBUG PLC1: Started | maintenance_interval={mode_mgr.maintenance_interval}")

    state_change = True
    prev_tank_output_valve = tank_output_valve_ref["value"] if tank_output_valve_ref else None
    last_level_print = time.time()

    while True:
        tank_level = tank_level_ref["value"] if tank_level_ref else 0
        current_mode = mode_mgr.update(tank_level)

        if plc_mode_ref:
            plc_mode_ref["value"] = current_mode
            state_update_callbacks["plc1_mode"]()

        if mode_mgr.outputs_enabled():
            if tank_level < 300 and state_change:
                if tank_input_valve_ref:
                    tank_input_valve_ref["value"] = True
                    if "tank_input_valve_state" in state_update_callbacks:
                        state_update_callbacks["tank_input_valve_state"]()
                state_change = False
            elif tank_level > 500 and not state_change:
                if tank_input_valve_ref:
                    tank_input_valve_ref["value"] = False
                    if "tank_input_valve_state" in state_update_callbacks:
                        state_update_callbacks["tank_input_valve_state"]()
                state_change = True

        # Always forward output valve changes to actuator regardless of PLC1 mode
        if tank_output_valve_ref and tank_output_valve_ref["value"] != prev_tank_output_valve:
            if "tank_output_valve_state" in state_update_callbacks:
                state_update_callbacks["tank_output_valve_state"]()
            prev_tank_output_valve = tank_output_valve_ref["value"]

        time.sleep(0.1)
