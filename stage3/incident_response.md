# Incident Response Report
Attack: Modify_Parameters  |  Model: openai/gpt-oss-20b  |  Score: 1.000  |  Grade: EXCELLENT

**1. Incident Overview**  
During the 2026‑06‑02 10:00‑10:01 window, the monitoring system flagged a **Modify_Parameters** event (MITRE T0836) with a classifier confidence of 0.94. The alert indicates that a device on the ics_simlab network performed a parameter modification operation that deviates from normal behavior. No direct packet captures or device logs are available in the evidence set, so the exact nature of the change and the affected asset remain unconfirmed. The incident is treated as a high‑confidence anomaly that warrants immediate investigation and containment.

**2. Detection Evidence**  
- Predicted Attack Type: Modify_Parameters  
- Classifier Confidence: 0.94  
- Detection Window: 2026‑06‑02T10:00:00 → 2026‑06‑02T10:01:00  
- Network Anomaly Score: 0.81 (branch‑specific)  
- Process Anomaly Score: 0.76 (branch‑specific)  
- MITRE ATT&CK Technique: T0836  

**3. Technical Interpretation**  
The anomaly scores suggest significant deviations in both network traffic patterns and process‑level behavior during the detection window. The high confidence and the alignment with T0836 imply that a Modbus‑compatible device attempted to write to a PLC register that controls operational parameters.  
**Environment anchors:**  
- **hmi3 (192.168.0.33)** → **plc1 (192.168.0.21)** via **Modbus TCP port 502**  
- **plc1** exposes holding registers such as `holding_register[200]` (plc1_mode) and `holding_register[210]` (sleep_time_ms) that are writable by authenticated clients.  
- **hmi1** and **hmi2** also connect to plc1 and plc2, but hmi3 is explicitly labeled as an attacker HMI in the topology, making it the most likely source of anomalous writes.

Given the absence of packet or log evidence, the modification may have targeted any writable register on plc1, potentially altering operational modes, sleep timers, or other control parameters. The exact parameter and value remain unknown.

**4. Affected Assets and Operational Impact**  
- **Confirmed Impact:** None. No evidence of altered register values, actuator state changes, or sensor anomalies has been observed.  
- **Potential Future Impact:** If the suspected parameter change succeeded, it could alter plc1’s operational mode (e.g., switching to a maintenance or test mode), modify sleep timers leading to timing drift, or set out‑of‑bounds values that may cause unsafe actuator behavior. Such changes could compromise process safety, product quality, or equipment integrity if left unchecked.

**5. Risk and Severity Assessment**  
- **Risk Level:** High. The anomaly scores and classifier confidence indicate a strong likelihood of a parameter modification attempt.  
- **Severity:** Medium to High, contingent on the specific parameter altered. Modifying critical control parameters can lead to unsafe operating conditions.  
- **Likelihood of Impact:** Uncertain; requires validation.  
- **Mitigation Priority:** Immediate containment and verification of parameter integrity.

**6. Immediate Containment Actions**  
1. **Isolate hmi3** from plc1 traffic if operationally feasible.  
   - *If safe to do so*, block TCP port 502 traffic from 192.168.0.33 to 192.168.0.21.  
2. **Enable write‑protect on plc1** for all non‑critical registers.  
   - *If confirmed* that write protection is not already active, configure plc1 to reject Modbus write requests to holding registers except for authorized users.  
3. **Activate verbose Modbus logging** on plc1 for the next 30 minutes.  
   - *If safe to do so*, enable detailed logging of all write requests to holding registers.  
4. **Notify operations** that a potential parameter modification was detected and that monitoring will be intensified.  
   - *Coordinate with operations before* making any changes that could affect live processes.

**7. Investigation and Validation Steps**  
1. **Retrieve Modbus transaction logs** from plc1 covering 2026‑06‑02T09:55:00 to 2026‑06‑02T10:05:00.  
   - Verify any write requests to holding registers, especially `holding_register[200]` and `holding_register[210]`.  
2. **Cross‑check plc1 register values** against baseline configuration stored in the asset inventory.  
   - Compare current values of `plc1_mode` and `sleep_time_ms` to expected defaults.  
3. **Examine hmi3’s local logs** for any Modbus write commands issued during the detection window.  
   - Look for entries referencing `coil[50]`, `coil[51]`, or other writable registers.  
4. **Validate HIL simulation state** for any anomalous changes in `plc1_mode` or `plc2_mode`.  
   - Ensure the simulation logic has not been altered.  
5. **Perform a quick sanity check** on actuator outputs (tank_input_valve, tank_output_valve, conveyor_belt_engine) to confirm no unintended state changes.  
6. **Audit user accounts** on plc1 to confirm that only authorized engineers have write access.  
7. **If a parameter change is confirmed**, document the exact register, old value, new value, and the user or device responsible.

**8. Recovery and Hardening Recommendations**  
1. **Implement role‑based access control** on plc1 and plc2, restricting write permissions to authenticated engineers only.  
2. **Enable write protection** for all critical holding registers by default; require explicit override with multi‑factor authentication.  
3. **Deploy continuous monitoring** of Modbus traffic for anomalous write patterns, with alerts for out‑of‑bounds values.  
4. **Establish a baseline configuration repository** for all PLC parameters and enforce automated comparison checks on startup.  
5. **Schedule regular firmware and logic reviews** to ensure that no unauthorized changes are present in plc1.py or plc2.py.  
6. **Educate operators** on the risks of modifying parameters and the importance of following change‑management procedures.  
7. **Introduce a change‑approval workflow** that logs all parameter modifications and requires sign‑off before deployment.  
8. **Consider implementing a write‑audit trail** that records the source IP, timestamp, and value for every register write.

**9. Analyst Notes and Uncertainty**  
- **Benign explanation 1:** hmi3 is a dedicated test HMI used during scheduled maintenance windows; it may have been used to write test parameters to plc1, which would trigger the anomaly detection but not affect production.  
- **Benign explanation 2:** A legitimate engineer could have temporarily connected hmi3 to plc1 to adjust `sleep_time_ms` for a diagnostic routine; the change may have been reverted before the detection window, leaving no lasting impact.  

These explanations require validation through log analysis and confirmation of the intended purpose of hmi3 during the detection period.