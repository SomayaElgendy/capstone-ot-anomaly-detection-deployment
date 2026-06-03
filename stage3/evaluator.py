import json
import re
from pathlib import Path

REPORT_SECTIONS = [
    "1. Incident Overview",
    "2. Detection Evidence",
    "3. Technical Interpretation",
    "4. Affected Assets and Operational Impact",
    "5. Risk and Severity Assessment",
    "6. Immediate Containment Actions",
    "7. Investigation and Validation Steps",
    "8. Recovery and Hardening Recommendations",
    "9. Analyst Notes and Uncertainty",
]

ICS_VOCABULARY = [
    "ics", "ot", "scada", "plc", "hmi", "dcs", "historian", "modbus",
    "industrial control system", "process control", "field device",
    "water treatment", "pump", "valve", "sensor", "actuator",
    "supervisory control", "telemetry", "physical process", "operator",
]

TECHNICAL_TERMS = [
    "containment", "segmentation", "isolation", "forensics", "packet capture",
    "network traffic", "plc logic", "ladder logic", "firmware", "ioc",
    "incident response", "attack path", "lateral movement", "unauthorized command",
    "malicious traffic", "engineering workstation", "controller", "fieldbus", "modbus traffic",
    "process anomaly", "network anomaly", "asset inventory", "switch port",
    "operating mode","alarm settings","alarm threshold","controller tasking","controller logic",
    "modify parameters","setpoint","setpoints","change operating mode",
    "engineering workstation","plc mode","run mode","program mode",
]

SEVERITY_WORDS = {"critical", "high", "medium", "low", "severe", "moderate", "indeterminate"}

UNCERTAINTY_PHRASES = [
    "may indicate", "suggests", "could be", "unclear", "uncertain",
    "further investigation", "cannot confirm", "appears to", "possible",
    "likely", "potentially", "unconfirmed", "requires validation",
    "unknown", "not confirmed", "not provided", "indeterminate",
]

HALLUCINATION_PATTERNS = [
    r"\bplc[_\-]?\d{2,}\b",
    r"\bhmi[_\-]?\d{2,}\b",
    r"\bworkstation[_\-]?\d+\b",
    r"\bengineering[_\-\s]?workstation[_\-]?\d+\b",
    r"\bscada[_\-]?\d+\b",
]

HALLUCINATION_PHRASES = [
    "operator noticed",
    "operator reported",
    "plant exploded",
    "water was poisoned",
    "found the binary",
    "malware sample confirmed",
    "attacker ip",
    "source ip",
    "confirmed the malware",
    "duplicate arp responses",
    "packet flood observed",
]

PRESUMPTION_PATTERNS = {
    "sector": [
        "water", "chlorine", "coagulant", "chemical dosing", "dosing pump",
        "epa discharge", "treatment plant",
    ],
    "os": [
        "registry", "gpo", "group policy", "active directory", "windows event",
        "sysmon", "autoruns", "run keys", ".exe", "event id 4624", "event id 4625",
    ],
    "vendor": [
        "siemens", "schneider", "rockwell", "abb", "yokogawa",
        "ecostruxure", "app locker",
    ],
}

BENIGN_EXPLANATION_TERMS = [
    "false positive", "benign", "maintenance", "backup", "compression",
    "failover", "sensor drift", "network lag", "baseline noise",
    "mirrored port", "port-mirror", "diagnostics", "software update",
    "redundant gateway", "legitimate bulk file operations",
    "hmi polling", "plc mode change", "rtu reconnect",
]

SEVERITY_TERMS = [
    "severity", "overall severity", "risk", "likelihood",
    "critical", "high", "medium", "low", "indeterminate",
]

CURRENT_IMPACT_TERMS = [
    "current impact", "no physical impact", "no process deviation",
    "current state", "none observed",
]

POTENTIAL_IMPACT_TERMS = [
    "potential impact", "possible impact", "future impact",
    "could lead to", "may lead to", "risk of future",
    "worst-case potential",
]

FINAL_ASSESSMENT_TERMS = [
    "overall severity", "severity:", "severity is",
    "rated as", "classified as", "overall risk", "indeterminate",
]

SUPPORT_TERMS = [
    "confidence", "anomaly", "score", "process", "network",
    "observable", "evidence", "safety", "uncertainty",
    "validation", "corroborated",
]

UNSUPPORTED_CLAIM_TERMS = [
    "operator complaints", "physical damage", "safety incident",
    "confirmed compromise", "confirmed impact",
    "packet capture confirmed", "malware sample confirmed",
    "forensic evidence confirmed", "engineering workstation compromise",
    "historian compromise", "plc logic was modified",
    "unauthorised logic change confirmed", "process disruption confirmed",
    "valve manipulation confirmed", "pump shutdown confirmed",
]

_DEFAULT_CONFIG_PATH = Path("data/raw/env/configuration.json")

def load_environment_reference(config_path=None):
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    if not path.exists():
        return {
            "asset_names": [],
            "asset_ips": [],
            "protocol_markers": [],
            "network_markers": [],
        }

    cfg = json.loads(path.read_text(encoding="utf-8"))

    asset_names = set()
    asset_ips = set()
    protocol_markers = set()
    network_markers = set()

    ui = cfg.get("ui", {})
    if isinstance(ui, dict):
        ui_net = ui.get("network", {})
        if isinstance(ui_net, dict):
            asset_names.add("ui")
            if ui_net.get("ip"):
                asset_ips.add(str(ui_net["ip"]))
            if ui_net.get("port"):
                protocol_markers.add(str(ui_net["port"]))

    for group_name in ["hmis", "plcs", "sensors", "actuators", "hils"]:
        for item in cfg.get(group_name, []):
            name = item.get("name")
            if name:
                asset_names.add(str(name).lower())

            if isinstance(item.get("network"), dict):
                ip = item["network"].get("ip")
                if ip:
                    asset_ips.add(str(ip))

            for conn_key in ["inbound_connections", "outbound_connections"]:
                for conn in item.get(conn_key, []):
                    if conn.get("type"):
                        protocol_markers.add(str(conn["type"]).lower())
                    if conn.get("port"):
                        protocol_markers.add(str(conn["port"]))

    for net in cfg.get("ip_networks", []):
        if net.get("name"):
            network_markers.add(str(net["name"]).lower())
        if net.get("docker_name"):
            network_markers.add(str(net["docker_name"]).lower())
        if net.get("subnet"):
            network_markers.add(str(net["subnet"]).lower())

    if "502" in protocol_markers:
        protocol_markers.add("port 502")
        protocol_markers.add("modbus")
        protocol_markers.add("modbus tcp")

    return {
        "asset_names": sorted(asset_names),
        "asset_ips": sorted(asset_ips),
        "protocol_markers": sorted(protocol_markers),
        "network_markers": sorted(network_markers),
    }


class IREvaluator:
    def __init__(self, config_path="data/raw/env/configuration.json"):
        self.env_data = load_environment_reference(config_path)

    def evaluate_retrieval(self, hits, attack_type):
        if not hits:
            return self._empty_retrieval()

        scores = [float(h.get("rrf_score", 0.0)) for h in hits]
        source_orgs = [h.get("source_org", "") for h in hits]
        categories = [h.get("category", "") for h in hits]

        avg_rrf = sum(scores) / len(scores)
        top_rrf = max(scores)
        source_div = len(set(source_orgs)) / max(len(hits), 1)
        cat_div = len(set(categories)) / max(len(hits), 1)

        rrf_norm = min(avg_rrf / 0.025, 1.0)
        score = rrf_norm * 0.45 + source_div * 0.30 + cat_div * 0.25

        return {
            "num_hits": len(hits),
            "avg_rrf_score": round(avg_rrf, 6),
            "top_rrf_score": round(top_rrf, 6),
            "source_diversity": round(source_div, 4),
            "category_diversity": round(cat_div, 4),
            "sources_retrieved": sorted(set(source_orgs)),
            "score": round(score, 4),
            "grade": self._grade(score),
        }

    def evaluate_report(self, report_text, attack_type, retrieved_hits=None, finish_reason=None):
        if not report_text or not report_text.strip():
            return self._empty_report()

        text_lower = report_text.lower()
        section_map = self._locate_sections(report_text)

        sec_score, sec_found, missing = self._score_sections(section_map)
        atk_score = self._score_attack_reference(text_lower, attack_type)
        ics_score, ics_count = self._score_ics_density(text_lower)
        action_score, action_count = self._score_actionability(text_lower)
        sev_present = self._score_severity_presence(text_lower)
        sev_justified = self._score_severity_justification(text_lower)
        length_score, word_count = self._score_length(report_text)
        tech_score = self._score_technical_depth(text_lower)
        lexical_score = self._score_lexical_grounding(text_lower, retrieved_hits)
        src_util = self._score_source_utilisation(text_lower, retrieved_hits)
        unc_score = self._score_uncertainty(text_lower)
        ground_score, hall_count, hall_hits = self._score_groundedness(text_lower)
        benign_score, benign_hits = self._score_benign_alternatives(report_text, section_map)
        trunc, trunc_pen = self._score_truncation(report_text, finish_reason, section_map)
        unsup_pen = self._score_unsupported_claim_penalty(text_lower, retrieved_hits)
        pres_pen, pres_hits = self._score_presumption_penalty(text_lower)
        env_spec_score = self._score_env_specificity(text_lower)
        env_hall_pen = self._score_env_hallucination_penalty(text_lower)

        raw = (
            sec_score * 0.15 +
            atk_score * 0.05 +
            ics_score * 0.08 +
            action_score * 0.15 +
            sev_justified * 0.05 +
            length_score * 0.04 +
            tech_score * 0.08 +
            lexical_score * 0.08 +
            src_util * 0.05 +
            unc_score * 0.05 +
            ground_score * 0.07 +
            benign_score * 0.05 +
            env_spec_score * 0.10
        )

        overall = max(0.0, raw - trunc_pen - (unsup_pen * 0.5) - (pres_pen * 0.5) - env_hall_pen)
        calibration_bonus = 0.06
        if sec_score >= 1.0 and action_score >= 0.8 and ground_score >= 0.8:
            overall += calibration_bonus
        overall = round(min(overall, 1.0), 4)

        return {
            "section_completeness": round(sec_score, 4),
            "sections_found": f"{sec_found}/{len(REPORT_SECTIONS)}",
            "missing_sections": missing,
            "attack_reference_quality": round(atk_score, 4),
            "ics_term_density": round(ics_score, 4),
            "ics_terms_found": ics_count,
            "actionability": round(action_score, 4),
            "action_items_count": action_count,
            "severity_present": sev_present,
            "severity_justified": round(sev_justified, 4),
            "length_quality": round(length_score, 4),
            "word_count": word_count,
            "technical_depth": round(tech_score, 4),
            "lexical_grounding": round(lexical_score, 4),
            "source_utilisation": round(src_util, 4),
            "uncertainty_present": round(unc_score, 4),
            "groundedness": round(ground_score, 4),
            "hallucinations_detected": hall_count,
            "hallucination_hits": hall_hits,
            "benign_alternatives": round(benign_score, 4),
            "benign_alternative_hits": benign_hits,
            "truncated": trunc,
            "truncation_penalty": round(trunc_pen, 4),
            "unsupported_penalty": round(unsup_pen, 4),
            "presumption_penalty": round(pres_pen, 4),
            "presumption_hits": pres_hits,
            "env_specificity": round(env_spec_score, 4),
            "env_hallucination_penalty": round(env_hall_pen, 4),
            "overall_score": overall,
            "grade": self._grade(overall),
        }

    @staticmethod
    def _locate_sections(report_text):
        section_map = {}
        positions = []

        for section in REPORT_SECTIONS:
            pattern = re.compile(
                r"(?:^|\n)\s*(?:#{1,6}\s*)?(?:\*\*)?\s*" + re.escape(section) + r"\s*(?:\*\*)?\s*(?:\n|$)",
                re.IGNORECASE
            )
            m = pattern.search(report_text)
            if m:
                positions.append((m.start(), section))

        positions.sort(key=lambda x: x[0])

        for i, (start, section) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(report_text)
            section_map[section] = (start, end)

        return section_map

    @staticmethod
    def _score_sections(section_map):
        found = [s for s in REPORT_SECTIONS if s in section_map]
        missing = [s for s in REPORT_SECTIONS if s not in section_map]
        return round(len(found) / len(REPORT_SECTIONS), 4), len(found), missing

    @staticmethod
    def _score_attack_reference(text_lower, attack_type):
        if not attack_type or not str(attack_type).strip():
            return 0.0

        attack_text = str(attack_type).lower().strip()
        score = 0.7 if attack_text in text_lower else 0.0

        pieces = [p for p in re.split(r"[_\-\s]+", attack_text) if p]
        if pieces:
            piece_hits = sum(1 for p in pieces if p in text_lower)
            score += min(piece_hits / len(pieces), 1.0) * 0.3

        return round(min(score, 1.0), 4)

    @staticmethod
    def _score_ics_density(text_lower):
        found = sum(1 for term in ICS_VOCABULARY if term in text_lower)
        score = min(found / 10.0, 1.0)
        return round(score, 4), found

    @staticmethod
    def _score_actionability(text_lower):
        patterns = [r"^\s*\d+\.", r"^\s*[-•]\s", r"\bstep\s+\d+\b", r"\baction\s+\d+\b"]
        count = 0

        for line in text_lower.splitlines():
            for p in patterns:
                if re.match(p, line):
                    count += 1
                    break

        return round(min(count / 12.0, 1.0), 4), count

    @staticmethod
    def _score_severity_presence(text_lower):
        return any(word in text_lower for word in SEVERITY_WORDS)

    @staticmethod
    def _score_severity_justification(text_lower):
        if not any(term in text_lower for term in SEVERITY_TERMS):
            return 0.0

        has_current = any(term in text_lower for term in CURRENT_IMPACT_TERMS)
        has_potential = any(term in text_lower for term in POTENTIAL_IMPACT_TERMS)
        has_final = any(term in text_lower for term in FINAL_ASSESSMENT_TERMS)
        has_support = any(term in text_lower for term in SUPPORT_TERMS)

        if has_current and has_potential and has_final and has_support:
            return 1.0
        if has_final and has_support and (has_current or has_potential):
            return 0.75
        if has_final and has_support:
            return 0.5
        return 0.15

    @staticmethod
    def _score_length(report_text):
        words = len(report_text.split())
        if words < 200:
            return round(words / 200.0 * 0.70, 4), words
        if words <= 600:
            return round(0.70 + (words - 200) / 400.0 * 0.30, 4), words
        if words <= 1500:
            return 1.0, words
        if words <= 2000:
            return round(1.0 - (words - 1500) / 500.0 * 0.15, 4), words
        return 0.70, words

    @staticmethod
    def _score_technical_depth(text_lower):
        found = sum(1 for term in TECHNICAL_TERMS if term in text_lower)
        return round(min(found / 8.0, 1.0), 4)

    @staticmethod
    def _score_lexical_grounding(text_lower, hits):
        if not hits:
            return 0.0

        ctx_text = " ".join((h.get("text") or "") for h in hits).lower()
        ctx_tokens = set(re.findall(r"[a-z]{4,}", ctx_text))
        report_tokens = set(re.findall(r"[a-z]{4,}", text_lower))

        if not ctx_tokens or not report_tokens:
            return 0.0

        overlap = len(report_tokens & ctx_tokens)
        return round(min(overlap / max(len(report_tokens) * 0.20, 1), 1.0), 4)

    @staticmethod
    def _score_source_utilisation(text_lower, hits):
        if not hits:
            return 0.0

        report_tokens = set(re.findall(r"[a-z]{5,}", text_lower))
        used = 0

        for h in hits:
            chunk_tokens = set(re.findall(r"[a-z]{5,}", (h.get("text") or "").lower()))
            if chunk_tokens and len(report_tokens & chunk_tokens) >= 2:
                used += 1

        return round(used / max(len(hits), 1), 4)

    @staticmethod
    def _score_uncertainty(text_lower):
        found = sum(1 for phrase in UNCERTAINTY_PHRASES if phrase in text_lower)
        return round(min(found / 3.0, 1.0), 4)

    @staticmethod
    def _score_groundedness(text_lower):
        hits = []

        for pattern in HALLUCINATION_PATTERNS:
            if re.search(pattern, text_lower, flags=re.IGNORECASE):
                hits.append(pattern)

        for phrase in HALLUCINATION_PHRASES:
            if phrase in text_lower:
                hits.append(phrase)

        count = len(hits)

        if count == 0:
            score = 1.0
        elif count == 1:
            score = 0.8
        elif count == 2:
            score = 0.55
        elif count == 3:
            score = 0.3
        else:
            score = 0.1

        return score, count, hits

    def _score_benign_alternatives(self, report_text, section_map):
        section9 = self._extract_section_text(
            report_text, section_map, "9. Analyst Notes and Uncertainty"
        )
        search_text = section9 if section9 else report_text
        text_lower = search_text.lower()

        explicit_items = re.findall(
            r"benign explanation\s*\d+\s*[:\-].+?(?=(?:benign explanation\s*\d+\s*[:\-])|$)",
            text_lower,
            flags=re.DOTALL,
        )

        hedges = [
            "could", "may", "might", "possible", "possibly", "hypothetical",
            "hypothetically", "requires validation", "should be validated",
            "unconfirmed", "not confirmed",
        ]

        qualified = []
        for item in explicit_items:
            if any(h in item for h in hedges):
                qualified.append(item.strip())

        if len(qualified) >= 2:
            return 1.0, ["explicit_benign_explanations"]
        if len(qualified) == 1:
            return 0.6, ["one_explicit_benign_explanation"]

        sentences = re.split(r"(?<=[.!?])\s+", search_text)
        sentence_hits = []
        for sent in sentences:
            sl = sent.lower()
            has_benign = any(term in sl for term in BENIGN_EXPLANATION_TERMS)
            has_hedge = any(h in sl for h in hedges)
            if has_benign and has_hedge:
                sentence_hits.append(sent.strip())

        if len(sentence_hits) >= 2:
            return 1.0, ["qualified_benign_sentences"]
        if len(sentence_hits) == 1:
            return 0.6, ["one_qualified_benign_sentence"]

        plain_hits = sorted(set(t for t in BENIGN_EXPLANATION_TERMS if t in text_lower))
        if len(plain_hits) >= 2:
            return 0.4, plain_hits
        if len(plain_hits) == 1:
            return 0.2, plain_hits
        return 0.0, []

    @staticmethod
    def _score_truncation(report_text, finish_reason, section_map=None):
        if finish_reason in ("length", "max_tokens"):
            return True, 0.10

        text = report_text.strip()
        if not text:
            return False, 0.0

        if section_map and "9. Analyst Notes and Uncertainty" in section_map:
            last_char = text[-1]
            if last_char in ".!?)]\"'":
                return False, 0.0

        bad_endings = (":", ";", "-", "•", ",", "(", "[")
        if len(text.split()) > 300 and text.endswith(bad_endings):
            return True, 0.05

        return False, 0.0

    @staticmethod
    def _score_unsupported_claim_penalty(text_lower, hits):
        context = "" if not hits else " ".join((h.get("text") or "") for h in hits).lower()
        unsupported = sum(1 for claim in UNSUPPORTED_CLAIM_TERMS if claim in text_lower and claim not in context)
        return round(min(unsupported * 0.03, 0.15), 4)

    @staticmethod
    def _score_presumption_penalty(text_lower):
        hits = []
        penalty = 0.0

        for category, phrases in PRESUMPTION_PATTERNS.items():
            for phrase in phrases:
                for m in re.finditer(re.escape(phrase), text_lower):
                    left = text_lower[max(0, m.start() - 40):m.start()]
                    if any(q in left for q in ["if ", "if present", "if applicable", "if confirmed", "e.g.", "for example", "example", "such as", "possible", "may", "might"]):
                        continue
                    hits.append(f"{category}:{phrase}")

        for hit in hits:
            if hit.startswith("vendor:"):
                penalty += 0.05
            elif hit.startswith("sector:"):
                penalty += 0.04
            elif hit.startswith("os:"):
                penalty += 0.035

        return round(min(penalty, 0.18), 4), hits

    def _score_env_specificity(self, text_lower):
        asset_names = [str(a).lower() for a in self.env_data.get("asset_names", [])]
        asset_ips = [str(ip) for ip in self.env_data.get("asset_ips", [])]
        protocol_markers = [str(p).lower() for p in self.env_data.get("protocol_markers", [])]
        network_markers = [str(n).lower() for n in self.env_data.get("network_markers", [])]

        family_terms = [
            "hmi", "hmis", "plc", "plcs", "sensor", "sensors",
            "actuator", "actuators", "ui node", "serial", "rtu",
            "modbus", "modbus/tcp", "tcp", "port 502",
            "communication path", "communication paths",
        ]

        asset_hits = sum(1 for a in asset_names if a and re.search(rf"\b{re.escape(a)}\b", text_lower))
        ip_hits = sum(1 for ip in asset_ips if ip and ip in text_lower)
        proto_hits = sum(1 for p in protocol_markers if p and p in text_lower)
        network_hits = sum(1 for n in network_markers if n and n in text_lower)
        family_hits = sum(1 for term in family_terms if term in text_lower)

        asset_score = min(asset_hits / 3.0, 1.0) * 0.35
        ip_score = min(ip_hits / 2.0, 1.0) * 0.20
        proto_score = min((proto_hits + family_hits) / 4.0, 1.0) * 0.25
        network_score = min(network_hits / 1.0, 1.0) * 0.10

        anchor_bonus = 0.10 if "environment anchors" in text_lower else 0.0

        return round(min(asset_score + ip_score + proto_score + network_score + anchor_bonus, 1.0), 4)

    def _score_env_hallucination_penalty(self, text_lower):
        env_ips = set(str(ip) for ip in self.env_data.get("asset_ips", []))
        if not env_ips:
            return 0.0
        found_ips = set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text_lower))
        foreign_ips = [ip for ip in found_ips if ip not in env_ips]

        return round(min(len(foreign_ips) * 0.03, 0.12), 4)
 
    @staticmethod
    def _extract_section_text(report_text, section_map, section_name):
        span = section_map.get(section_name)
        return None if not span else report_text[span[0]:span[1]]

    @staticmethod
    def _grade(score):
        if score >= 0.80:
            return "EXCELLENT"
        if score >= 0.70:
            return "GOOD"
        if score >= 0.50:
            return "FAIR"
        return "POOR"

    @staticmethod
    def _empty_retrieval():
        return {
            "num_hits": 0,
            "avg_rrf_score": 0.0,
            "top_rrf_score": 0.0,
            "source_diversity": 0.0,
            "category_diversity": 0.0,
            "sources_retrieved": [],
            "score": 0.0,
            "grade": "POOR",
        }

    @staticmethod
    def _empty_report():
        return {
            "section_completeness": 0.0,
            "sections_found": "0/9",
            "missing_sections": list(REPORT_SECTIONS),
            "attack_reference_quality": 0.0,
            "ics_term_density": 0.0,
            "ics_terms_found": 0,
            "actionability": 0.0,
            "action_items_count": 0,
            "severity_present": False,
            "severity_justified": 0.0,
            "length_quality": 0.0,
            "word_count": 0,
            "technical_depth": 0.0,
            "lexical_grounding": 0.0,
            "source_utilisation": 0.0,
            "uncertainty_present": 0.0,
            "groundedness": 0.0,
            "hallucinations_detected": 0,
            "hallucination_hits": [],
            "benign_alternatives": 0.0,
            "benign_alternative_hits": [],
            "truncated": False,
            "truncation_penalty": 0.0,
            "unsupported_penalty": 0.0,
            "presumption_penalty": 0.0,
            "presumption_hits": [],
            "env_specificity": 0.0,
            "env_hallucination_penalty": 0.0,
            "overall_score": 0.0,
            "grade": "POOR",
        }