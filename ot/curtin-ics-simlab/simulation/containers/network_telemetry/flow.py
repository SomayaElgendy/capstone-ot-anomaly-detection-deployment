#!/usr/bin/env python3
import time
from packet_parser import ip_to_int
from config import REDIS_FLOW_STATS_KEY


class FlowPacket:
    """Represents a single packet within a flow."""

    def __init__(self, packet, timestamp, is_sender,
                 src_ip, dst_ip, src_port=0, dst_port=0):
        self.timestamp    = timestamp
        self.is_sender    = is_sender
        self.src_ip       = src_ip
        self.dst_ip       = dst_ip
        self.src_port     = src_port
        self.dst_port     = dst_port
        self.size         = len(packet)
        self.payload_size = self._get_payload_size(packet)
        self.ttl          = self._get_ttl(packet)
        self.tcp_flags    = self._get_tcp_flags(packet)
        self.tcp_window   = self._get_tcp_window(packet)
        self.is_fragment  = self._is_fragment(packet)

    def _get_payload_size(self, packet):
        try:
            if packet.haslayer('TCP'): return len(packet['TCP'].payload)
            if packet.haslayer('UDP'): return len(packet['UDP'].payload)
        except Exception:
            pass
        return 0

    def _get_ttl(self, packet):
        if packet.haslayer('IP'):   return packet['IP'].ttl
        if packet.haslayer('IPv6'): return packet['IPv6'].hlim
        return 0

    def _get_tcp_flags(self, packet):
        flags = {'FIN': False, 'SYN': False, 'RST': False,
                 'PSH': False, 'ACK': False, 'URG': False}
        if packet.haslayer('TCP'):
            f = packet['TCP'].flags
            flags['FIN'] = bool(f & 0x01)
            flags['SYN'] = bool(f & 0x02)
            flags['RST'] = bool(f & 0x04)
            flags['PSH'] = bool(f & 0x08)
            flags['ACK'] = bool(f & 0x10)
            flags['URG'] = bool(f & 0x20)
        return flags

    def _get_tcp_window(self, packet):
        return packet['TCP'].window if packet.haslayer('TCP') else 0

    def _is_fragment(self, packet):
        if packet.haslayer('IP'):
            return bool((packet['IP'].flags & 0x01) or packet['IP'].frag > 0)
        return False


class Flow:
    """
    Bidirectional network flow.

    Sender/receiver determination matches LogicForFlow.py:
      1. TCP SYN (no ACK) -> clear initiator
      2. First packet seen -> treated as initiator
    Packets are stored in lists so that get_features() can compute
    statistics identically to LogicForFlow._calculate_packet_stats().
    """

    def __init__(self, src_ip, dst_ip, protocol, src_port=0, dst_port=0):
        self.src_ip   = src_ip
        self.dst_ip   = dst_ip
        self.protocol = protocol
        self.src_port = src_port
        self.dst_port = dst_port

        self.sender_ip     = None
        self.receiver_ip   = None
        self.sender_port   = None
        self.receiver_port = None
        self.is_determined = False

        # Store packets per direction — same as LogicForFlow
        self.sender_packets   = []
        self.receiver_packets = []

        self.start_time       = None
        self.end_time         = None
        self.last_packet_time = None

        # For get_current_state() dashboard only
        self.total_packets_count = 0
        self.total_bytes_sum     = 0
        self.packet_rate         = 0.0
        self.byte_rate           = 0.0

    # ------------------------------------------------------------------
    # Sender / receiver determination  (mirrors LogicForFlow exactly)
    # ------------------------------------------------------------------

    def _determine_sender_receiver(self, src_ip, src_port, dst_ip, dst_port, packet):
        if self.is_determined:
            return
        if packet.haslayer('TCP'):
            flags  = packet['TCP'].flags
            is_syn = bool(flags & 0x02)
            is_ack = bool(flags & 0x10)
            if is_syn and not is_ack:
                self.sender_ip     = src_ip
                self.sender_port   = src_port
                self.receiver_ip   = dst_ip
                self.receiver_port = dst_port
                self.is_determined = True
                return
        # First-packet fallback
        self.sender_ip     = src_ip
        self.sender_port   = src_port
        self.receiver_ip   = dst_ip
        self.receiver_port = dst_port
        self.is_determined = True

    # ------------------------------------------------------------------
    # Packet ingestion
    # ------------------------------------------------------------------

    def add_packet(self, packet, timestamp, src_ip, dst_ip,
                   src_port=0, dst_port=0):
        if not self.is_determined:
            self._determine_sender_receiver(src_ip, src_port, dst_ip, dst_port, packet)

        is_sender = (src_ip == self.sender_ip and src_port == self.sender_port)
        fp = FlowPacket(packet, timestamp, is_sender,
                        src_ip, dst_ip, src_port, dst_port)

        if is_sender:
            self.sender_packets.append(fp)
        else:
            self.receiver_packets.append(fp)

        if self.start_time is None or timestamp < self.start_time:
            self.start_time = timestamp
        if self.end_time is None or timestamp > self.end_time:
            self.end_time = timestamp
        self.last_packet_time = timestamp

        self.total_packets_count += 1
        self.total_bytes_sum     += fp.size
        self._update_rates(timestamp)

    def _update_rates(self, current_time):
        duration = current_time - self.start_time
        if duration > 0:
            self.packet_rate = self.total_packets_count / duration
            self.byte_rate   = self.total_bytes_sum     / duration

    # ------------------------------------------------------------------
    # Statistics  (mirrors LogicForFlow._calculate_packet_stats exactly)
    # ------------------------------------------------------------------

    def _calculate_packet_stats(self, packets):
        empty = {
            'count': 0,
            'bytes_max': 0, 'bytes_min': 0, 'bytes_avg': 0.0, 'bytes_total': 0,
            'payload_max': 0, 'payload_min': 0, 'payload_avg': 0.0,
            'load_bps': 0.0, 'interpacket_avg': 0.0, 'ttl_avg': 0.0,
            'ack_rate': 0.0, 'fin_rate': 0.0, 'psh_rate': 0.0,
            'rst_rate': 0.0, 'urg_rate': 0.0, 'syn_rate': 0.0,
            'win_avg': 0.0, 'fragment_rate': 0.0,
        }
        if not packets:
            return empty

        sorted_pkts = sorted(packets, key=lambda p: p.timestamp)

        sizes         = [p.size         for p in sorted_pkts]
        payload_sizes = [p.payload_size for p in sorted_pkts]

        interpacket_times = [
            sorted_pkts[i].timestamp - sorted_pkts[i - 1].timestamp
            for i in range(1, len(sorted_pkts))
        ]

        ttls        = [p.ttl for p in sorted_pkts if p.ttl > 0]
        tcp_pkts    = [p for p in sorted_pkts if p.tcp_flags != {'FIN': False, 'SYN': False, 'RST': False, 'PSH': False, 'ACK': False, 'URG': False} or p.tcp_window > 0]
        # More accurate: detect TCP packets by checking if any flag is set OR window>0
        tcp_pkts    = [p for p in sorted_pkts
                       if any(p.tcp_flags.values()) or p.tcp_window > 0]
        tcp_count   = len(tcp_pkts)
        tcp_windows = [p.tcp_window for p in tcp_pkts if p.tcp_window > 0]

        ack_count      = sum(1 for p in tcp_pkts if p.tcp_flags.get('ACK'))
        fin_count      = sum(1 for p in tcp_pkts if p.tcp_flags.get('FIN'))
        psh_count      = sum(1 for p in tcp_pkts if p.tcp_flags.get('PSH'))
        rst_count      = sum(1 for p in tcp_pkts if p.tcp_flags.get('RST'))
        urg_count      = sum(1 for p in tcp_pkts if p.tcp_flags.get('URG'))
        syn_count      = sum(1 for p in tcp_pkts if p.tcp_flags.get('SYN'))
        fragment_count = sum(1 for p in sorted_pkts if p.is_fragment)

        total_bytes = sum(sizes)
        n           = len(sorted_pkts)
        duration    = sorted_pkts[-1].timestamp - sorted_pkts[0].timestamp
        load_bps    = (total_bytes * 8) / duration if duration > 0 else 0

        return {
            'count':           n,
            'bytes_max':       max(sizes),
            'bytes_min':       min(sizes),
            'bytes_avg':       total_bytes / n,
            'bytes_total':     total_bytes,
            'payload_max':     max(payload_sizes) if payload_sizes else 0,
            'payload_min':     min(payload_sizes) if payload_sizes else 0,
            'payload_avg':     sum(payload_sizes) / n if payload_sizes else 0,
            'load_bps':        load_bps,
            'interpacket_avg': sum(interpacket_times) / len(interpacket_times) if interpacket_times else 0,
            'ttl_avg':         sum(ttls) / len(ttls) if ttls else 0,
            'ack_rate':        ack_count / tcp_count if tcp_count else 0,
            'fin_rate':        fin_count / tcp_count if tcp_count else 0,
            'psh_rate':        psh_count / tcp_count if tcp_count else 0,
            'rst_rate':        rst_count / tcp_count if tcp_count else 0,
            'urg_rate':        urg_count / tcp_count if tcp_count else 0,
            'syn_rate':        syn_count / tcp_count if tcp_count else 0,
            'win_avg':         sum(tcp_windows) / len(tcp_windows) if tcp_windows else 0,
            'fragment_rate':   fragment_count / n,
        }

    # ------------------------------------------------------------------
    # Feature export  (mirrors LogicForFlow.get_features exactly)
    # ------------------------------------------------------------------

    def get_features(self):
        s = self._calculate_packet_stats(self.sender_packets)
        r = self._calculate_packet_stats(self.receiver_packets)

        duration = (self.end_time - self.start_time) \
                   if self.start_time and self.end_time else 0

        return {
            'sender_address':   self.sender_ip,
            'receiver_address': self.receiver_ip,
            'protocol':         self.protocol,
            'duration':         duration,
            'timestamp':        self.start_time,

            'sPackets':      s['count'],
            'sBytesMax':     s['bytes_max'],
            'sBytesMin':     s['bytes_min'],
            'sBytesAvg':     s['bytes_avg'],
            'sBytesTotal':   s['bytes_total'],
            'sLoad':         s['load_bps'],
            'sPayloadMax':   s['payload_max'],
            'sPayloadMin':   s['payload_min'],
            'sPayloadAvg':   s['payload_avg'],
            'sInterPacket':  s['interpacket_avg'],
            'sttl':          s['ttl_avg'],
            'sAckRate':      s['ack_rate'],
            'sFinRate':      s['fin_rate'],
            'sPshRate':      s['psh_rate'],
            'sRstRate':      s['rst_rate'],
            'sUrgRate':      s['urg_rate'],
            'sSynRate':      s['syn_rate'],
            'sWin':          s['win_avg'],
            'sFragmentRate': s['fragment_rate'],

            'rPackets':      r['count'],
            'rBytesMax':     r['bytes_max'],
            'rBytesMin':     r['bytes_min'],
            'rBytesAvg':     r['bytes_avg'],
            'rBytesTotal':   r['bytes_total'],
            'rLoad':         r['load_bps'],
            'rPayloadMax':   r['payload_max'],
            'rPayloadMin':   r['payload_min'],
            'rPayloadAvg':   r['payload_avg'],
            'rInterPacket':  r['interpacket_avg'],
            'rttl':          r['ttl_avg'],
            'rAckRate':      r['ack_rate'],
            'rFinRate':      r['fin_rate'],
            'rPshRate':      r['psh_rate'],
            'rRstRate':      r['rst_rate'],
            'rUrgRate':      r['urg_rate'],
            'rSynRate':      r['syn_rate'],
            'rWin':          r['win_avg'],
            'rFragmentRate': r['fragment_rate'],
        }

    # ------------------------------------------------------------------
    # Dashboard state (not part of feature export)
    # ------------------------------------------------------------------

    def get_current_state(self):
        duration = (time.time() - self.start_time) if self.start_time else 0
        return {
            'flow_key':        f"{self.sender_ip}:{self.src_port} -> {self.receiver_ip}:{self.dst_port}",
            'sender_address':  self.sender_ip,
            'receiver_address': self.receiver_ip,
            'sender_port':     self.src_port,
            'receiver_port':   self.dst_port,
            'protocol':        self.protocol,
            'duration':        duration,
            'total_packets':   self.total_packets_count,
            'total_bytes':     self.total_bytes_sum,
            'packet_rate':     round(self.packet_rate, 2),
            'byte_rate':       round(self.byte_rate, 2),
            'last_packet':     self.last_packet_time,
            'active':          True,
        }


# ------------------------------------------------------------------
# Flow key helpers
# ------------------------------------------------------------------

def get_flow_key(src_ip, dst_ip, protocol, src_port=0, dst_port=0):
    """
    Canonical bidirectional key — mirrors LogicForFlow's forward/reverse
    key lookup (lines 431-438). Both directions map to the same key by
    storing (smaller_ip, larger_ip, ...) so a reverse packet always
    finds the existing flow.
    """
    if protocol == 'ARP':
        return (src_ip, dst_ip, protocol)
    # Canonicalize so both directions hash to the same key
    if (src_ip, src_port) < (dst_ip, dst_port):
        return (src_ip, dst_ip, protocol, src_port, dst_port)
    else:
        return (dst_ip, src_ip, protocol, dst_port, src_port)


def get_flow_state_key(flow_key):
    key_str = '_'.join(str(x) for x in flow_key)
    key_str = key_str.replace('.', '_').replace(':', '_')
    return f"{REDIS_FLOW_STATS_KEY}{key_str}"
