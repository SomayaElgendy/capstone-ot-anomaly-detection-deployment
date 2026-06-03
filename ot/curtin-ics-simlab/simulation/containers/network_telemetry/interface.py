#!/usr/bin/env python3
import os
import re
import logging

logger = logging.getLogger(__name__)


def get_interfaces(interface_pattern):
    """
    Get list of network interfaces from /sys/class/net
    """
    interfaces = []
    pattern = interface_pattern.replace('*', '.*')
    
    try:
        if os.path.exists('/sys/class/net'):
            for iface in os.listdir('/sys/class/net'):
                if iface == 'lo':
                    continue
                if re.match(pattern, iface):
                    interfaces.append(iface)
            
            if interfaces:
                logger.info(f"Found {len(interfaces)} interfaces matching '{interface_pattern}'")
                return interfaces
            
            # If no matching, return all physical interfaces
            all_ifaces = [iface for iface in os.listdir('/sys/class/net') if iface != 'lo']
            if all_ifaces:
                logger.info(f"No matching interfaces, using all {len(all_ifaces)} interfaces")
                return all_ifaces
        
        logger.warning("No interfaces found, capturing on all")
        return []
        
    except Exception as e:
        logger.error(f"Error getting interfaces: {e}")
        return []
