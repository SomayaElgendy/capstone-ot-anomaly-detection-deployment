import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from groq import Groq
from hybrid_retriever import HybridRetriever
from evaluator import IREvaluator, REPORT_SECTIONS


# ── Single deployment model ───────────────────────────────────────────────
GROQ_MODEL = "openai/gpt-oss-20b"

# ── Generation defaults ───────────────────────────────────────────────────
GEN_TEMPERATURE = 0.2
GEN_MAX_TOKENS  = 3000
GEN_TOP_P       = 0.95
TOP_K_RETRIEVAL = 3

# ── Default alerts file path ──────────────────────────────────────────────
DEFAULT_STAGE2_PATH = Path("outputs/stage2/alerts.json")

# ── Output directories ────────────────────────────────────────────────────
BASE_OUTPUT_DIR = Path("outputs/stage3")
IR_DIR = BASE_OUTPUT_DIR / "IR"
EVAL_DIR = BASE_OUTPUT_DIR / "eval"

for _d in [IR_DIR, EVAL_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Alert schema ──────────────────────────────────────────────────────────
REQUIRED_KEYS = [
    "predicted_attack",
    "classifier_confidence",
    "network_anomaly_score",
    "process_anomaly_score",
    "window_start_time",
    "window_end_time",
]

# ═══════════════════════════════════════════════════════════════════════════
# Environment context code
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_CONFIG_PATH = Path("data/raw/env/configuration.json")


def load_environment_context(config_path=None):
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"[env_context] configuration.json not found at: {path}")
        
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return _format_context(cfg)


def _format_context(cfg):
    lines = []

    lines.append("=== OUR ICS ENVIRONMENT CONFIGURATION ===")
    lines.append(
        "The following describes the EXACT assets, IPs, protocols, and topology "
        "of the monitored ICS testbed. You MUST use this information as the "
        "definitive source of truth for all asset references, containment targets, "
        "and investigation steps in the incident response report. "
        "Do NOT use generic placeholder IPs or hypothetical assets."
    )
    lines.append("")

    # ── Network overview ───────────────────────────────────────────────────
    ip_nets = cfg.get("ip_networks", [])
    if ip_nets:
        lines.append("[ IP NETWORKS ]")
        for net in ip_nets:
            lines.append(
                f"  Network : {net.get('name')}  "
                f"Docker: {net.get('docker_name')}  "
                f"Subnet: {net.get('subnet')}"
            )
        lines.append("")

    # ── UI ─────────────────────────────────────────────────────────────────
    ui = cfg.get("ui", {})
    ui_net = ui.get("network", {})
    if ui_net:
        lines.append("[ UI NODE ]")
        lines.append(
            f"  IP: {ui_net.get('ip')}  "
            f"Port: {ui_net.get('port')}  "
            f"Network: {ui_net.get('docker_network')}"
        )
        lines.append("")

    # ── HMIs ──────────────────────────────────────────────────────────────
    hmis = cfg.get("hmis", [])
    if hmis:
        lines.append("[ HMIs ]")
        for hmi in hmis:
            name = hmi.get("name", "?")
            ip = hmi.get("network", {}).get("ip", "?")
            htype = hmi.get("hmi_type", "standard")
            lines.append(f"  {name}  IP={ip}  type={htype}")
            # outbound TCP connections
            for conn in hmi.get("outbound_connections", []):
                lines.append(
                    f"    → outbound TCP to {conn.get('ip')}:{conn.get('port')}  "
                    f"id={conn.get('id')}"
                )
            # monitors
            for mon in hmi.get("monitors", []):
                lines.append(
                    f"    monitor: {mon.get('id')}  "
                    f"via={mon.get('outbound_connection_id')}  "
                    f"reg={mon.get('value_type')}[{mon.get('address')}]  "
                    f"interval={mon.get('interval')}s"
                )
            # controllers
            for ctl in hmi.get("controllers", []):
                lines.append(
                    f"    control: {ctl.get('id')}  "
                    f"via={ctl.get('outbound_connection_id')}  "
                    f"reg={ctl.get('value_type')}[{ctl.get('address')}]"
                )
        lines.append("")

    # ── PLCs ──────────────────────────────────────────────────────────────
    plcs = cfg.get("plcs", [])
    if plcs:
        lines.append("[ PLCs ]")
        for plc in plcs:
            name = plc.get("name", "?")
            ip = plc.get("network", {}).get("ip", "?")
            logic = plc.get("logic", "?")
            lines.append(f"  {name}  IP={ip}  logic={logic}")
            for conn in plc.get("outbound_connections", []):
                if conn.get("type") == "tcp":
                    lines.append(
                        f"    → TCP to {conn.get('ip')}:{conn.get('port')}  "
                        f"id={conn.get('id')}"
                    )
                else:
                    lines.append(
                        f"    → RTU via {conn.get('comm_port')}  "
                        f"id={conn.get('id')}"
                    )
            regs = plc.get("registers", {})
            for rtype, rlist in regs.items():
                for r in rlist:
                    lines.append(
                        f"    reg {rtype}[{r.get('address')}]  "
                        f"id={r.get('id')}  io={r.get('io', 'N/A')}"
                    )
        lines.append("")

    # ── Sensors ───────────────────────────────────────────────────────────
    sensors = cfg.get("sensors", [])
    if sensors:
        lines.append("[ SENSORS ]")
        for s in sensors:
            ip = s.get("network", {}).get("ip", "?")
            lines.append(f"  {s.get('name')}  IP={ip}")
            for conn in s.get("inbound_connections", []):
                lines.append(
                    f"    ← RTU slave_id={conn.get('slave_id')}  "
                    f"port={conn.get('comm_port')}"
                )
            for rtype, rlist in s.get("registers", {}).items():
                for r in rlist:
                    if r:
                        lines.append(
                            f"    reg {rtype}[{r.get('address')}]  "
                            f"physical={r.get('physical_value', 'N/A')}"
                        )
        lines.append("")

    # ── Actuators ─────────────────────────────────────────────────────────
    actuators = cfg.get("actuators", [])
    if actuators:
        lines.append("[ ACTUATORS ]")
        for a in actuators:
            ip = a.get("network", {}).get("ip", "?")
            lines.append(f"  {a.get('name')}  IP={ip}  logic={a.get('logic', 'N/A')}")
            for conn in a.get("inbound_connections", []):
                lines.append(
                    f"    ← RTU slave_id={conn.get('slave_id')}  "
                    f"port={conn.get('comm_port')}"
                )
        lines.append("")

    # ── HILs ──────────────────────────────────────────────────────────────
    hils = cfg.get("hils", [])
    if hils:
        lines.append("[ HIL SIMULATION NODES ]")
        for h in hils:
            lines.append(f"  {h.get('name')}  logic={h.get('logic', 'N/A')}")
            for pv in h.get("physical_values", []):
                lines.append(f"    physical_value: {pv.get('name')}  io={pv.get('io')}")
        lines.append("")

    # ── Serial network wiring ──────────────────────────────────────────────
    serial_nets = cfg.get("serial_networks", [])
    if serial_nets:
        lines.append("[ SERIAL NETWORK WIRING ]")
        for sn in serial_nets:
            lines.append(f"  {sn.get('src')} ↔ {sn.get('dest')}")
        lines.append("")

    lines.append("=== END OF ENVIRONMENT CONFIGURATION ===")
    return "\n".join(lines)

def build_asset_quickref(config_path=None):
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    if not path.exists():
        return ""

    cfg = json.loads(path.read_text(encoding="utf-8"))
    lines = ["TESTBED ASSET NAME & IP REFERENCE — use EXACT names and IPs from this table:"]

    for hmi in cfg.get("hmis", []):
        ip = hmi.get("network", {}).get("ip", "?")
        lines.append(f"  HMI      : {hmi['name']}  IP={ip}")

    for plc in cfg.get("plcs", []):
        ip = plc.get("network", {}).get("ip", "?")
        lines.append(f"  PLC      : {plc['name']}  IP={ip}")

    for s in cfg.get("sensors", []):
        ip = s.get("network", {}).get("ip", "?")
        lines.append(f"  Sensor   : {s['name']}  IP={ip}")

    for a in cfg.get("actuators", []):
        ip = a.get("network", {}).get("ip", "?")
        lines.append(f"  Actuator : {a['name']}  IP={ip}")

    for h in cfg.get("hils", []):
        lines.append(f"  HIL      : {h['name']}")

    ui_ip = cfg.get("ui", {}).get("network", {}).get("ip", "?")
    lines.append(f"  UI       : ui  IP={ui_ip}")

    for net in cfg.get("ip_networks", []):
        lines.append(f"  Network  : {net.get('name')}  subnet={net.get('subnet')}")

    return "\n".join(lines)

try:
    ENV_CONTEXT_BLOCK = load_environment_context()
    ENV_ASSET_QUICKREF = build_asset_quickref()
    _ENV_LOADED = True
except FileNotFoundError as _e:
    ENV_CONTEXT_BLOCK = (
        "[WARNING] configuration.json not found. "
        f"Details: {_e}"
    )
    ENV_ASSET_QUICKREF = ""
    _ENV_LOADED = False

def env_loaded():
    return _ENV_LOADED


# ═══════════════════════════════════════════════════════════════════════════
# Alert loading
# ═══════════════════════════════════════════════════════════════════════════

def validate_alert(alert):
    if not isinstance(alert, dict):
        raise ValueError("Each alert must be a dictionary.")

    missing = [k for k in REQUIRED_KEYS if k not in alert]
    if missing:
        raise ValueError(f"Alert missing required keys: {missing}")

    # ── predicted_attack ───────────────────────────────────────────────────
    predicted_attack = alert["predicted_attack"]
    if not isinstance(predicted_attack, str) or not predicted_attack.strip():
        raise ValueError("predicted_attack must be a non-empty string.")

    # ── classifier_confidence ──────────────────────────────────────────────
    classifier_confidence = alert["classifier_confidence"]
    if not isinstance(classifier_confidence, (int, float)):
        raise ValueError("classifier_confidence must be numeric.")
    classifier_confidence = float(classifier_confidence)
    if not 0.0 <= classifier_confidence <= 1.0:
        raise ValueError("classifier_confidence must be in [0, 1].")

    # ── anomaly scores ─────────────────────────────────────────────────────
    for k in ["network_anomaly_score", "process_anomaly_score"]:
        value = alert[k]
        if not isinstance(value, (int, float)):
            raise ValueError(f"{k} must be numeric.")
        value = float(value)
        if value < 0:
            raise ValueError(f"{k} must be non-negative.")

    # ── timestamps ─────────────────────────────────────────────────────────
    for k in ["window_start_time", "window_end_time"]:
        value = alert[k]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{k} must be a non-empty string.")

    # ── technique_id (optional) ────────────────────────────────────────────
    if "technique_id" in alert:
        technique_id = alert["technique_id"]
        if technique_id is not None and (
            not isinstance(technique_id, str) or not technique_id.strip()
        ):
            raise ValueError("technique_id must be either None or a non-empty string.")

def iter_alerts_one_by_one(path_str):
    path = Path(path_str)
    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        raw = [raw]

    if not isinstance(raw, list):
        raise ValueError("Stage 2 output must be a JSON list or a single alert object.")

    if not raw:
        raise ValueError("Stage 2 output must not be an empty list.")

    for i, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Alert #{i} is not a JSON object.")
        validate_alert(row)
        yield row


# ═══════════════════════════════════════════════════════════════════════════
# Prompting code
# ═══════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = f"""You are an OT/ICS incident response analyst. Generate professional, concise incident response reports for operators, engineers, and defenders.

SOURCES OF TRUTH (use in this priority order):
1. DETECTION EVIDENCE — direct facts about this alert only.
2. OUR ENVIRONMENT — authoritative asset inventory, IPs, topology, protocols. Use real assets; do not claim information is missing if it is present here.
3. RETRIEVED OT/ICS KNOWLEDGE — general reference guidance, not proof of site conditions.

CORE RULES:
- Write as an incident responder interpreting evidence. Never mention classifiers, model training, AI reasoning, or model signatures.
- Do NOT invent assets, IPs, vendors, OS details, firmware versions, packet evidence, operator statements, or confirmed physical effects unsupported by evidence.
- Do NOT introduce protocols or technologies absent from the provided material.
- Prefer cautious wording: "may indicate", "is consistent with", "could represent", "requires validation".
- Separate current confirmed impact from potential future impact clearly.
- Low anomaly scores must reduce certainty unless corroborating evidence exists.
- ANOMALY SCORES are branch-specific (network branch vs. process branch) and are NOT on the same scale. Do not directly compare them or assume one is more severe based on magnitude alone. Interpret each score only relative to its own branch.
- Recommendations must be minimally disruptive. Do NOT recommend shutdowns, disabling PLC logic, or stopping control processes unless confirmed physical impact exists.
- RTU/Serial-connected sensors and actuators cannot be isolated from the network; investigate through PLC logic and serial-link checks instead.
- Section 9 MUST include at least TWO plausible benign or non-malicious hypothetical explanations specific to this testbed's topology and protocols.
- For low-evidence alerts, prefer validation, targeted logging, and conditional containment over broad asset isolation.
- Recommendations depending on operational state MUST use qualifiers: "if confirmed", "if safe to do so", "coordinate with operations before".

=== TESTBED ASSET QUICK REFERENCE ===
{ENV_ASSET_QUICKREF}

=== ENVIRONMENT LOADED: {_ENV_LOADED} ===
{"Full environment configuration is provided in the OUR ENVIRONMENT section." if _ENV_LOADED else "WARNING: Environment configuration missing. Do not invent environment-specific details."}
"""

ATTACK_QUERY_HINTS = {
    "detect_operating_mode":    "detect operating mode controller engineering workstation discovery industrial control system",
    "modify_alarm_settings":    "modify alarm settings industrial control system alarm threshold notification configuration",
    "modify_controller_tasking":"modify controller tasking PLC logic controller task unauthorized changes",
    "modify_parameters":        "modify parameters setpoints controller values industrial process configuration",
    "change_operating_mode":    "change operating mode controller PLC run program mode industrial control system",
}

def build_retrieval_query(alert):
    parts = []
    attack    = str(alert.get("predicted_attack", "")).strip()
    technique = alert.get("technique_id")
    conf      = alert.get("classifier_confidence")

    if attack:
        parts.append(attack)
        parts.append(ATTACK_QUERY_HINTS.get(attack, attack.replace("_", " ")))
    if technique:
        parts.append(str(technique).strip())
    if isinstance(conf, (int, float)):
        if conf >= 0.90:
            parts.append("high confidence alert")
        elif conf >= 0.70:
            parts.append("moderate confidence alert")
        else:
            parts.append("low confidence alert requires validation")

    parts.append("OT ICS incident response containment investigation recovery mitigation")
    return " ".join(parts).strip()

def build_generation_prompt(alert, hits):
    detection_block    = _format_detection_block(alert)
    context_block      = _format_retrieved_context(hits)
    env_block          = ENV_CONTEXT_BLOCK
    instruction_block  = _format_report_instructions()

    user_prompt = (
        "=== DETECTION EVIDENCE ===\n"
        f"{detection_block}\n\n"
        "=== RETRIEVED OT/ICS KNOWLEDGE ===\n"
        f"{context_block}\n\n"
        "=== OUR ENVIRONMENT ===\n"
        f"{env_block}\n\n"
        "=== REPORT INSTRUCTIONS ===\n"
        f"{instruction_block}\n\n"
        "Generate the full incident response report now, starting directly with Section 1."
    )
    return {"system": _SYSTEM_PROMPT, "user": user_prompt}

def _format_detection_block(alert):
    attack     = alert.get("predicted_attack", "unknown")
    conf       = alert.get("classifier_confidence", "N/A")
    net_score  = alert.get("network_anomaly_score", "N/A")
    proc_score = alert.get("process_anomaly_score", "N/A")
    t_start    = alert.get("window_start_time", "N/A")
    t_end      = alert.get("window_end_time", "N/A")
    technique  = alert.get("technique_id")

    lines = [
        f"Predicted Attack Type  : {attack}",
        f"Classifier Confidence  : {conf}",
        f"Detection Window       : {t_start}  ->  {t_end}",
        f"Network Anomaly Score  : {net_score}  [branch-specific; do not compare magnitude to process score]",
        f"Process Anomaly Score  : {proc_score}  [branch-specific; do not compare magnitude to network score]",
        f"MITRE ATT&CK Technique : {technique if technique else 'Not mapped'}",
        "",
        "EVIDENCE SCOPE:",
        "- Only the fields above are direct incident evidence.",
        "- No raw packet captures, confirmed compromised hosts, malware artefacts, or protocol-level artefacts are included.",
        "- OUR ENVIRONMENT section provides authoritative asset inventory, IPs, and topology.",
        "- Mark any fact not present in detection evidence as unknown, unconfirmed, or requiring validation.",
        "- If the exact affected asset is unknown, name relevant candidate assets from the environment and state compromise is unconfirmed.",
        "- Each anomaly score reflects its own model branch's deviation scale only. A numerically large process score does not automatically indicate higher severity than a numerically smaller network score.",
        "",
        "ASSET NAMING REQUIREMENT:",
        "- When mentioning candidate assets, use exact asset names from TESTBED ASSET QUICK REFERENCE.",
        "- Do not write only generic terms like 'the PLC', 'the HMI', 'the sensor', or 'the actuator' when exact candidate names are available.",
    ]
    return "\n".join(lines)

def _format_retrieved_context(hits):
    if not hits:
        return "No relevant chunks retrieved."

    blocks = []

    for i, h in enumerate(hits, start=1):
        technique_str = h.get("technique_id") or "N/A"

        attack_classes = h.get("attack_classes") or []
        if isinstance(attack_classes, list):
            attack_classes_str = ", ".join(str(x) for x in attack_classes) if attack_classes else "N/A"
        else:
            attack_classes_str = str(attack_classes)

        block = (
            f"[Source {i}]\n"
            f"Organisation   : {h.get('source_org', 'unknown')}\n"
            f"Category       : {h.get('category', 'unknown')}\n"
            f"Technique      : {technique_str}\n"
            f"Attack Classes : {attack_classes_str}\n"
            f"{(h.get('text') or '').strip()}"
        )

        blocks.append(block)

    return "\n\n---\n\n".join(blocks)

def _format_report_instructions():
    lines = [
        "Write the report using exactly these numbered section headings:",
        *[f"- {s}" for s in REPORT_SECTIONS],
        "",
        "Rules:",
        "- Keep the full report between 700 and 1200 words unless the evidence requires more detail.",
        "- Section 3 MUST include one line starting with 'Environment anchors:' and must include exact candidate asset names from TESTBED ASSET QUICK REFERENCE plus at least one IP address, protocol, port, or communication path when available.",
        "- If the exact affected asset is unknown, write 'candidate asset' or 'candidate path' and clearly state that compromise is unconfirmed.",
        "- Mention the predicted attack type explicitly in Section 1.",
        "- Separate current confirmed impact from potential future impact (Sections 4 and 5).",
        "- Include numbered action items in Sections 6, 7, and 8.",
        "- Use real assets from OUR ENVIRONMENT; do not claim information is missing if it is present there.",
        "- Name candidate environment assets using exact names from TESTBED ASSET QUICK REFERENCE; state compromise is unconfirmed when the exact affected asset is unknown.",
        "- Use retrieved knowledge as general guidance only, not proof of this site's condition.",
        "- Do NOT invent assets, IPs, logs, malware artefacts, packet findings, operator statements, or confirmed compromise.",
        "- Do NOT say traffic was intercepted, altered, spoofed, or manipulated as confirmed fact without supporting evidence.",
        "- Each anomaly score is branch-specific. Interpret severity from confidence level, retrieved context, and environment relevance—not from raw score magnitude alone.",
        "- Section 9 benign explanations must be written as hypothetical validation candidates, not confirmed facts.",
        "- For low-evidence alerts, prefer targeted validation, logging, and conditional containment over broad isolation.",
        "- Recommendations depending on operational state: use 'if confirmed', 'if safe to do so', 'coordinate with operations before'.",
        "- Keep the report OT/ICS-focused, concise, and avoid unnecessary repetition.",
        "- Section 9 MUST include at least TWO plausible hypothetical benign explanations specific to this testbed.",
        "- Section 9 MUST include exactly two bullets named 'Benign explanation 1' and 'Benign explanation 2'.",
        "- Each benign explanation must include cautious wording such as 'could', 'may', 'possible', or 'requires validation'.",
        "- Do NOT output <think> tags or internal reasoning.",
    ]
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════
# Retrieval wrapper
# ═══════════════════════════════════════════════════════════════════════════

class RetrievalEngine:
    def __init__(self):
        self._retriever = HybridRetriever()

    def retrieve(self, query, top_k=3):
        raw_hits = self._retriever.search(query, top_k=top_k)

        passthrough_fields = [
            "rank",
            "chunk_idx",
            "rrf_score",
            "chunk_id",
            "doc_id",
            "doc_family_id",
            "source_org",
            "category",
            "source_type",
            "word_count",
            "technique_id",
            "attack_classes",
            "text",
        ]

        hits = []
        for h in raw_hits:
            hit = {field: h.get(field) for field in passthrough_fields}
            hits.append(hit)

        return hits


# ═══════════════════════════════════════════════════════════════════════════
# LLM code
# ═══════════════════════════════════════════════════════════════════════════

_client = None


def _clean_report_text(text):
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*analysis\s*:?\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate_one_model(
    prompt_bundle,
    temperature=GEN_TEMPERATURE,
    max_tokens=GEN_MAX_TOKENS,
    top_p=GEN_TOP_P,
):
    global _client

    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY is not set")
        _client = Groq(api_key=api_key)

    t0 = time.time()
    try:
        response = _client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            messages=[
                {"role": "system", "content": prompt_bundle["system"]},
                {"role": "user",   "content": prompt_bundle["user"]},
            ],
        )
        elapsed = round(time.time() - t0, 2)
        choice  = response.choices[0]
        usage   = response.usage

        return {
            "model_name"       : GROQ_MODEL,
            "raw_report_text"  : choice.message.content,
            "report_text"      : _clean_report_text(choice.message.content),
            "finish_reason"    : choice.finish_reason,
            "generation_time_s": elapsed,
            "input_tokens"     : getattr(usage, "prompt_tokens",     None),
            "output_tokens"    : getattr(usage, "completion_tokens", None),
            "error"            : None,
        }

    except Exception as exc:
        elapsed = round(time.time() - t0, 2)
        return {
            "model_name"       : GROQ_MODEL,
            "raw_report_text"  : "",
            "report_text"      : "",
            "finish_reason"    : "error",
            "generation_time_s": elapsed,
            "input_tokens"     : None,
            "output_tokens"    : None,
            "error"            : str(exc),
        }


def _write_json(path, obj):
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def run_pipeline(alerts_path=str(DEFAULT_STAGE2_PATH), top_k=TOP_K_RETRIEVAL):
    """
    API-compatible wrapper around the Stage 3 deployment pipeline.
    Used by api_server.py /generate-ir endpoint.
    """
    retrieval_engine = RetrievalEngine()
    evaluator = IREvaluator()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"[deployment] model={GROQ_MODEL} alerts_path={alerts_path}")

    last_result = None

    for idx, alert in enumerate(iter_alerts_one_by_one(alerts_path), start=1):
        attack = alert["predicted_attack"]
        run_id = f"deploy_alert{idx}_{attack}_{timestamp}"

        query = build_retrieval_query(alert)

        t_ret_start = time.time()
        hits = retrieval_engine.retrieve(query, top_k=top_k)
        retrieval_time_s = round(time.time() - t_ret_start, 3)

        retrieval_eval = evaluator.evaluate_retrieval(hits, attack)
        prompt_bundle = build_generation_prompt(alert, hits)
        gen = generate_one_model(prompt_bundle)

        if gen.get("error"):
            eval_path = EVAL_DIR / f"{run_id}_eval.json"
            _write_json(
                eval_path,
                {
                    "run_id": run_id,
                    "alert": alert,
                    "query": query,
                    "retrieval_eval": retrieval_eval,
                    "generation_error": gen["error"],
                    "model_name": GROQ_MODEL,
                },
            )

            print(f"[deployment] {idx} attack={attack} FAILED")

            last_result = {
                "success": False,
                "run_id": run_id,
                "alert": alert,
                "error": gen["error"],
                "report": "",
                "retrieved_hits": hits,
            }
            continue

        report_eval = evaluator.evaluate_report(
            report_text=gen["report_text"],
            attack_type=attack,
            retrieved_hits=hits,
            finish_reason=gen.get("finish_reason"),
        )

        if report_eval["sections_found"] == "0/9":
            report_eval["grade"] = "POOR"

        total_pipeline_time_s = round(
            retrieval_time_s + gen["generation_time_s"],
            3,
        )

        final_report_text = (
            f"# Incident Response Report\n"
            f"Attack: {attack}  |  Model: {GROQ_MODEL}  |  "
            f"Score: {report_eval['overall_score']:.3f}  |  "
            f"Grade: {report_eval['grade']}\n\n"
            + gen["report_text"]
        )

        ir_path = IR_DIR / f"{run_id}.md"
        ir_path.write_text(final_report_text, encoding="utf-8")

        eval_path = EVAL_DIR / f"{run_id}_eval.json"
        _write_json(
            eval_path,
            {
                "run_id": run_id,
                "alert": alert,
                "query": query,
                "model_name": GROQ_MODEL,
                "retrieval_time_s": retrieval_time_s,
                "generation_time_s": gen["generation_time_s"],
                "total_pipeline_time_s": total_pipeline_time_s,
                "input_tokens": gen.get("input_tokens"),
                "output_tokens": gen.get("output_tokens"),
                "finish_reason": gen.get("finish_reason"),
                "retrieval_eval": retrieval_eval,
                "report_eval": report_eval,
                "retrieved_hits": hits,
                "ir_path": str(ir_path),
            },
        )

        print(
            f"[deployment] {idx} attack={attack} "
            f"score={report_eval['overall_score']:.3f} grade={report_eval['grade']}"
        )

        last_result = {
            "success": True,
            "run_id": run_id,
            "alert": alert,
            "report": final_report_text,
            "ir_path": str(ir_path),
            "eval_path": str(eval_path),
            "grade": report_eval["grade"],
            "score": report_eval["overall_score"],
            "retrieved_hits": hits,
            "retrieval_time_s": retrieval_time_s,
            "generation_time_s": gen.get("generation_time_s"),
            "total_pipeline_time_s": total_pipeline_time_s,
        }

    return last_result


def run_chat(message: str, context: dict, top_k=TOP_K_RETRIEVAL):
    """
    API-compatible chat wrapper.
    Used by api_server.py /chat endpoint.
    """
    retrieval_engine = RetrievalEngine()

    attack_label = (
        context.get("label")
        or context.get("attack_label")
        or context.get("predicted_attack")
        or "unknown"
    )

    attack_label = str(attack_label).lower()

    severity = context.get("severity", "unknown")
    anomaly_score = context.get("anomaly_score", 0.0)
    network_anomaly_score = context.get("network_anomaly_score", "unknown")
    process_anomaly_score = context.get("process_anomaly_score", "unknown")
    status = context.get("status", "unknown")
    created_at = context.get("created_at", "unknown")
    recommended_actions = context.get("recommended_actions", {})
    incident_summary = context.get("incident_summary", "")
    full_report = context.get("full_report", context.get("report", ""))

    retrieval_query = f"""
Attack type: {attack_label}
Severity: {severity}
Anomaly score: {anomaly_score}
Network anomaly score: {network_anomaly_score}
Process anomaly score: {process_anomaly_score}
Status: {status}
Created at: {created_at}
User question: {message}
""".strip()

    hits = retrieval_engine.retrieve(retrieval_query, top_k=top_k)

    retrieved_context = _format_retrieved_context(hits)

    prompt_bundle = {
        "system": (
            "You are an ICS cybersecurity assistant helping a security specialist "
            "understand a detected OT/ICS alert."
        ),
        "user": f"""
Answer the user's question clearly, accurately, and briefly.

Use only:
1. the provided alert context
2. the retrieved ICS/OT knowledge
3. the already generated incident response if relevant

Do not invent facts not supported by the given context.
If something is unknown, say so clearly.

ALERT CONTEXT:
- Attack Label: {attack_label}
- Severity: {severity}
- Anomaly Score: {anomaly_score}
- Network Anomaly Score: {network_anomaly_score}
- Process Anomaly Score: {process_anomaly_score}
- Status: {status}
- Created At: {created_at}
- Recommended Actions: {recommended_actions}
- Incident Summary: {incident_summary}
- Full Report: {full_report}

RETRIEVED KNOWLEDGE:
{retrieved_context}

USER QUESTION:
{message}

Return only the assistant answer.
""".strip(),
    }

    gen = generate_one_model(prompt_bundle)

    if gen.get("error"):
        return {
            "success": False,
            "error": gen["error"],
            "reply": "",
        }

    reply = (gen.get("report_text") or "").strip()

    return {
        "success": True,
        "reply": reply,
        "generation_time_s": gen.get("generation_time_s"),
        "input_tokens": gen.get("input_tokens"),
        "output_tokens": gen.get("output_tokens"),
        "finish_reason": gen.get("finish_reason"),
        "retrieved_hits": hits,
    }

def main():
    parser = argparse.ArgumentParser(description="Stage 3 deployment runner")
    parser.add_argument(
        "--alerts_path",
        default=str(DEFAULT_STAGE2_PATH),
        help=f"Path to Stage 2-style alerts JSON (default: {DEFAULT_STAGE2_PATH})",
    )
    parser.add_argument(
        "--top_k",
        type=int,
        default=TOP_K_RETRIEVAL,
        help=f"Number of retrieved chunks per alert (default: {TOP_K_RETRIEVAL}).",
    )
    args = parser.parse_args()

    retrieval_engine = RetrievalEngine()
    evaluator = IREvaluator()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"[deployment] model={GROQ_MODEL} alerts_path={args.alerts_path}")

    for idx, alert in enumerate(iter_alerts_one_by_one(args.alerts_path), start=1):
        attack = alert["predicted_attack"]
        run_id = f"deploy_alert{idx}_{attack}_{timestamp}"

        query = build_retrieval_query(alert)

        t_ret_start = time.time()
        hits = retrieval_engine.retrieve(query, top_k=args.top_k)
        retrieval_time_s = round(time.time() - t_ret_start, 3)

        retrieval_eval = evaluator.evaluate_retrieval(hits, attack)
        prompt_bundle = build_generation_prompt(alert, hits)
        gen = generate_one_model(prompt_bundle)

        if gen.get("error"):
            eval_path = EVAL_DIR / f"{run_id}_eval.json"
            _write_json(eval_path, {
                "run_id": run_id,
                "alert": alert,
                "query": query,
                "retrieval_eval": retrieval_eval,
                "generation_error": gen["error"],
                "model_name": GROQ_MODEL,
            })
            print(f"[deployment] {idx} attack={attack} FAILED")
            continue

        report_eval = evaluator.evaluate_report(
            report_text=gen["report_text"],
            attack_type=attack,
            retrieved_hits=hits,
            finish_reason=gen.get("finish_reason"),
        )
        if report_eval["sections_found"] == "0/9":
            report_eval["grade"] = "POOR"

        total_pipeline_time_s = round(retrieval_time_s + gen["generation_time_s"], 3)

        ir_path = IR_DIR / f"{run_id}.md"
        ir_path.write_text(
            f"# Incident Response Report\n"
            f"Attack: {attack}  |  Model: {GROQ_MODEL}  |  "
            f"Score: {report_eval['overall_score']:.3f}  |  "
            f"Grade: {report_eval['grade']}\n\n"
            + gen["report_text"],
            encoding="utf-8",
        )

        eval_path = EVAL_DIR / f"{run_id}_eval.json"
        _write_json(eval_path, {
            "run_id": run_id,
            "alert": alert,
            "query": query,
            "model_name": GROQ_MODEL,
            "retrieval_time_s": retrieval_time_s,
            "generation_time_s": gen["generation_time_s"],
            "total_pipeline_time_s": total_pipeline_time_s,
            "input_tokens": gen.get("input_tokens"),
            "output_tokens": gen.get("output_tokens"),
            "finish_reason": gen.get("finish_reason"),
            "retrieval_eval": retrieval_eval,
            "report_eval": report_eval,
        })

        print(
            f"[deployment] {idx} attack={attack} "
            f"score={report_eval['overall_score']:.3f} grade={report_eval['grade']}"
        )

if __name__ == "__main__":
    main()