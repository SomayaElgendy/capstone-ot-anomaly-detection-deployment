#!/usr/bin/env python3
import time
import json
import threading
import logging
from scapy.all import sniff
from config import (
    REDIS_HOST, REDIS_PORT,
    FLOW_INTERVAL, IDLE_TIMEOUT, ACTIVE_TIMEOUT, MODBUS_TIMEOUT,
    TARGET_IPS, REDIS_STREAM, REDIS_CHANNEL, REDIS_STATE_KEY,
    REDIS_ACTIVE_FLOWS_KEY, MAX_STREAM_LEN
)
from interface import get_interfaces
from packet_parser import extract_packet_info, get_protocol_string
from flow import Flow, get_flow_key
from schema import SchemaValidator, store_schema_in_redis, verify_schema_in_redis
import redis

logger = logging.getLogger(__name__)


class PacketCapture:
    def __init__(self):
        self.flows        = {}
        self.flows_lock   = threading.Lock()
        self.redis_client = None
        self.running      = True
        self.interfaces   = []
        self.validator    = SchemaValidator()

        logger.info(f"Target IPs: {TARGET_IPS}")

        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT,
                decode_responses=True, socket_connect_timeout=3
            )
            self.redis_client.ping()
            logger.info(f"✓ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            store_schema_in_redis(self.redis_client)
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            logger.warning("Continuing without Redis (flows will not be stored)")
            self.redis_client = None

    # ------------------------------------------------------------------
    # Redis state update  (dashboard only — not flow export)
    # ------------------------------------------------------------------

    def update_redis_state(self):
        if not self.redis_client:
            return
        try:
            current_time = time.time()
            active_flows = []

            with self.flows_lock:
                flows_copy = dict(self.flows)

            for flow_key, flow in flows_copy.items():
                if flow.end_time and (current_time - flow.end_time) < IDLE_TIMEOUT:
                    active_flows.append(flow.get_current_state())

            self.redis_client.set(REDIS_ACTIVE_FLOWS_KEY, json.dumps(active_flows))
            overall_state = {
                'timestamp':         current_time,
                'timestamp_iso':     time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'active_flow_count': len(active_flows),
                'total_packets':     sum(f['total_packets'] for f in active_flows) if active_flows else 0,
                'total_bytes':       sum(f['total_bytes']   for f in active_flows) if active_flows else 0,
                'flows':             active_flows[:10],
            }
            self.redis_client.setex(REDIS_STATE_KEY, 10, json.dumps(overall_state))

        except RuntimeError as e:
            if "dictionary changed size during iteration" in str(e):
                logger.debug("Dictionary changed during iteration, skipping update")
            else:
                logger.error(f"Error updating Redis state: {e}")
        except Exception as e:
            logger.error(f"Error updating Redis state: {e}")

    # ------------------------------------------------------------------
    # Validate and publish a completed flow record
    # ------------------------------------------------------------------

    def validate_and_send_flow(self, flow_data):
        if not self.redis_client:
            return False

        if 'timestamp' not in flow_data or not flow_data['timestamp']:
            flow_data['timestamp'] = time.time()

        flow_data['timestamp_iso']     = time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        flow_data['timestamp_unix_ms'] = int(time.time() * 1000)

        is_valid, errors = self.validator.validate(flow_data)
        flow_data['_validation'] = json.dumps({
            'valid':          is_valid,
            'errors':         errors[:5] if not is_valid else [],
            'schema_version': '1.0',
        })
        if not is_valid:
            logger.warning(f"Flow validation failed: {errors[:3]}")

        try:
            self.redis_client.xadd(
                REDIS_STREAM, flow_data,
                maxlen=MAX_STREAM_LEN, approximate=True
            )
            self.redis_client.publish(REDIS_CHANNEL, json.dumps(flow_data, default=str))
            return True
        except Exception as e:
            logger.error(f"Error sending to Redis: {e}")
            return False

    # ------------------------------------------------------------------
    # Packet handler  (runs in scapy's capture thread)
    # ------------------------------------------------------------------

    def packet_handler(self, packet):
        if not self.running:
            return
        try:
            timestamp = time.time()
            src_ip, dst_ip, src_port, dst_port = extract_packet_info(packet)

            if src_ip is None or dst_ip is None:
                return
            if src_ip not in TARGET_IPS and dst_ip not in TARGET_IPS:
                return

            protocol = get_protocol_string(packet)

            # get_flow_key() returns the same canonical key regardless of
            # which direction the packet is travelling — same logic as
            # LogicForFlow's forward/reverse key lookup.
            flow_key = get_flow_key(src_ip, dst_ip, protocol, src_port, dst_port)

            with self.flows_lock:
                if flow_key not in self.flows:
                    # Canonical src/dst stored in the Flow come from the key
                    # itself; actual sender/receiver is resolved on first packet
                    # inside Flow._determine_sender_receiver().
                    self.flows[flow_key] = Flow(
                        src_ip, dst_ip, protocol, src_port, dst_port
                    )
                flow = self.flows[flow_key]

            flow.add_packet(packet, timestamp, src_ip, dst_ip, src_port, dst_port)

        except Exception as e:
            logger.debug(f"Packet error: {e}")

    # ------------------------------------------------------------------
    # Flow export loop  (runs in a background thread)
    #
    # Logic mirrors LogicForFlow.generate_flows() lines 444-461:
    #   idle  = time since last packet  > IDLE_TIMEOUT   → export + delete
    #   age   = time since flow started > ACTIVE_TIMEOUT → export + delete
    # A new packet after either trigger simply creates a fresh Flow entry
    # in packet_handler, exactly as the PCAP converter does.
    # ------------------------------------------------------------------

    def process_flows(self):
        last_state_update = 0

        while self.running:
            time.sleep(FLOW_INTERVAL)   # 0.05s tick — well below 0.5s idle threshold

            current_time = time.time()

            if current_time - last_state_update >= 1.0:
                self.update_redis_state()
                last_state_update = current_time

            flows_to_send  = []
            completed_keys = []

            with self.flows_lock:
                if not self.flows:
                    continue

                for flow_key, flow in self.flows.items():
                    if not flow.start_time:
                        continue

                    is_modbus      = 'Modbus' in flow.protocol
                    active_timeout = MODBUS_TIMEOUT if is_modbus else ACTIVE_TIMEOUT
                    idle_time      = (current_time - flow.end_time) if flow.end_time else 0
                    flow_age       = current_time - flow.start_time

                    # Exactly mirrors LogicForFlow line 453:
                    # if idle > interval_seconds or active_age > effective_timeout
                    if idle_time > IDLE_TIMEOUT or flow_age > active_timeout:
                        flows_to_send.append(flow.get_features())
                        completed_keys.append(flow_key)

                for key in completed_keys:
                    del self.flows[key]
                    # Note: delete not reset — next arriving packet creates
                    # a fresh Flow object, identical to LogicForFlow line 459

            for flow_data in flows_to_send:
                if self.redis_client:
                    self.validate_and_send_flow(flow_data)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def start_capture(self, interface_pattern):
        self.interfaces = get_interfaces(interface_pattern)

        if self.interfaces:
            logger.info(f"Capturing on interfaces: {self.interfaces}")
        else:
            logger.info("No specific interfaces found, capturing on all")

        logger.info(
            f"Idle timeout: {IDLE_TIMEOUT}s | "
            f"Active timeout: {ACTIVE_TIMEOUT}s | "
            f"Modbus timeout: {MODBUS_TIMEOUT}s | "
            f"Loop tick: {FLOW_INTERVAL}s"
        )

        if self.redis_client:
            verify_schema_in_redis(self.redis_client)

        flow_thread = threading.Thread(target=self.process_flows, daemon=True)
        flow_thread.start()

        try:
            if self.interfaces:
                sniff(iface=self.interfaces, prn=self.packet_handler, store=False)
            else:
                sniff(prn=self.packet_handler, store=False)
        except KeyboardInterrupt:
            logger.info("Capture stopped by user")
        except Exception as e:
            logger.error(f"Capture error: {e}")
        finally:
            self.running = False
