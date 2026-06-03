# Live vs Step 3 Window Comparison Diagnosis

## Purpose

This evidence was collected to verify whether the live OT Redis telemetry produces model-ready windows similar to the offline Step 3 dataset used to train Stage 1 and Stage 2.

## Dataset Step 3 Window

Dataset window ID: 0
Window time: 17:36:34.070 to 17:36:44.070
Process rows: 47
Network rows: 45

Network protocol counts:
{
  "IPV4-TCP": 1,
  "IPV4-ModbusTCP": 44
}

Top network pairs:
{
  "192.168.0.100 -> 192.168.0.21": 20,
  "192.168.0.100 -> 192.168.0.22": 20,
  "192.168.0.100 -> 192.168.0.200": 1,
  "192.168.0.31 -> 192.168.0.22": 1,
  "192.168.0.22 -> 192.168.0.21": 1
}

## Live Environment Window

Live time: 2026-06-03T02:02:46 to 2026-06-03T02:02:56
Process rows: 51
Network rows: 2

Network protocol counts:
{
  "IPV4-TCP": 2
}

Top network pairs:
{
  "192.168.0.1 -> 192.168.0.200": 2
}

## Diagnosis

The live process stream is healthy because it produces approximately the expected number of process rows in a 10-second interval.

However, the live network stream does not match the Step 3 dataset. The Step 3 network window contains many network rows, mostly ModbusTCP, while the live network window contains very few network rows. This means the live network branch input is not equivalent to the training data.

Therefore, the unstable Stage 2 classification is likely caused by live network input distribution mismatch, not primarily by model thresholds or scaling.

## Main Cause

The offline Step 3 dataset appears to have been produced from dense PCAP/network event extraction, where many ModbusTCP events appear inside each 10-second window. The live Redis network:telemetry stream is flow-based and currently produces sparse summarized rows. As a result, the live model-ready network window is mostly padded zeros or contains unrelated generic TCP rows.

## Impact on Stage 2

Stage 2 was trained on network windows with dense ModbusTCP evidence. During live inference, it receives sparse or incomplete network evidence. This causes the classifier to produce low-confidence or wrong attack labels, often leaning toward the closest learned class rather than the true live attack class.

## Recommended Future Fixes

1. Update the live network telemetry service so it emits PCAP-equivalent Modbus event rows, similar to the offline Step 3 network rows.
2. Recreate the Step 3 windowing logic in the live pipeline using event timestamps and sufficient ModbusTCP row density.
3. Avoid publishing model-ready network windows when the network mask contains too few real rows.
4. If the live Redis telemetry format must remain sparse, retrain or recalibrate Stage 1 and Stage 2 using live-collected Redis windows instead of offline PCAP-derived windows.
5. For the current demo, use this limitation as an engineering validation result and avoid claiming that live Stage 2 classification is fully reliable on the network branch.