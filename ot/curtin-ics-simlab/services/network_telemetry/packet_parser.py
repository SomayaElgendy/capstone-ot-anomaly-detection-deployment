#!/usr/bin/env python3
import ipaddress
from scapy.all import IP, IPv6, TCP, UDP, ARP, ICMP


def ip_to_int(ip):
    try:
        return int(ipaddress.ip_address(ip))
    except:
        return 0


def get_protocol_string(packet):
    """Extract protocol information with Modbus detection"""
    if packet.haslayer(ARP):
        return 'ARP'
    elif packet.haslayer(IP):
        if packet.haslayer(TCP):
            if packet[TCP].sport == 502 or packet[TCP].dport == 502:
                return 'IPV4-ModbusTCP'
            return 'IPV4-TCP'
        elif packet.haslayer(UDP):
            if packet[UDP].sport == 502 or packet[UDP].dport == 502:
                return 'IPV4-ModbusRTU'
            return 'IPV4-UDP'
        elif packet.haslayer(ICMP):
            return 'IPV4-ICMP'
        return 'IPV4-OTHER'
    elif packet.haslayer(IPv6):
        if packet.haslayer(TCP):
            if packet[TCP].sport == 502 or packet[TCP].dport == 502:
                return 'IPV6-ModbusTCP'
            return 'IPV6-TCP'
        elif packet.haslayer(UDP):
            if packet[UDP].sport == 502 or packet[UDP].dport == 502:
                return 'IPV6-ModbusRTU'
            return 'IPV6-UDP'
        return 'IPV6-OTHER'
    return 'OTHER'


def extract_packet_info(packet):
    """Extract IP addresses and ports from packet"""
    src_ip = None
    dst_ip = None
    src_port = 0
    dst_port = 0
    
    if packet.haslayer(IP):
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        
        if packet.haslayer(TCP):
            src_port = packet[TCP].sport
            dst_port = packet[TCP].dport
        elif packet.haslayer(UDP):
            src_port = packet[UDP].sport
            dst_port = packet[UDP].dport
            
    elif packet.haslayer(IPv6):
        src_ip = packet[IPv6].src
        dst_ip = packet[IPv6].dst
        
        if packet.haslayer(TCP):
            src_port = packet[TCP].sport
            dst_port = packet[TCP].dport
        elif packet.haslayer(UDP):
            src_port = packet[UDP].sport
            dst_port = packet[UDP].dport
            
    elif packet.haslayer(ARP):
        src_ip = packet[ARP].psrc
        dst_ip = packet[ARP].pdst
        
    return src_ip, dst_ip, src_port, dst_port
