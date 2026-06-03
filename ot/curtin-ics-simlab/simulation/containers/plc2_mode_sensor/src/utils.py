#!/usr/bin/env python3

# -----------------------------------------------------------------------------
# Project: Curtin ICS-SimLab
# File: utils.py
#
# Copyright (c) 2025 Jaxson Brown, Curtin University
#
# Licensed under the MIT License. You may obtain a copy of the License at:
#     https://opensource.org/licenses/MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# This work is supported by a Cross-Campus Cyber Security Research Project
# funded by **Curtin University**
#
# Author: Jaxson Brown
# Organisation: Curtin University
# Last Modified: 2025-08-27
# -----------------------------------------------------------------------------

# FILE PURPOSE: Common functions to be used in all components

import json
import time
import logging
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.server import ModbusTcpServer, ModbusSerialServer
from pymodbus.pdu.diag_message import ForceListenOnlyModeRequest

# GLOBAL VARIABLES
listen_only = False



# FUNCTION: retrieve_configs
# PURPOSE:  Retrieves the JSON configs
def retrieve_configs(filename):
    with open(filename, "r") as config_file:
        content = config_file.read()
        configs = json.loads(content)
    return configs



# FUNCTION: run_tcp_server
# PURPOSE:  An asynchronous function to be used to start a modbus tcp server. Blocks on the server.
async def run_tcp_server(connection, context, identity=None):    
    # bind to all interfaces of the container
    tcp_server = ModbusTcpServer(
        context=context, 
        address=("0.0.0.0", connection["port"]), 
        identity=identity,
    ) 
    logging.info(f"Starting TCP Server. IP: {connection['ip']}, Port: {connection['port']}")
    await tcp_server.serve_forever()



# FUNCTION: run_rtu_slave
# PURPOSE:  An asynchronous function to use for modbus rtu server. Blocks on the server.
async def run_rtu_slave(connection, context, identity=None):
    rtu_slave = ModbusSerialServer(
        context=context, 
        port=connection["comm_port"], 
        baudrate=9600, 
        timeout=1, 
        identity=identity
    )
    logging.info(f"Starting RTU Slave. Port: {connection['comm_port']}")
    await rtu_slave.serve_forever()



# FUNCTION: run_tcp_client
# PURPOSE:  Creates a tcp client
def run_tcp_client(connection):
    tcp_client = ModbusTcpClient(host=connection["ip"], port=connection["port"])
    logging.info(f"Starting TCP Client. IP: {connection['ip']}, Port: {connection['port']}")
    tcp_client.connect()
    return tcp_client



# FUNCTION: run_rtu_master
# PURPOSE:  Create an rtu master connection
def run_rtu_master(connection):
    rtu_master = ModbusSerialClient(port=connection["comm_port"], baudrate=9600, timeout=1)
    logging.info(f"Starting RTU Master. Port: {connection['comm_port']}")
    rtu_master.connect()
    return rtu_master



# FUNCTION: update_register_values
# PURPOSE:  Updates the "register_values" dictionary with the register values of the modbus server,
#           which is in the "registers" dictionary.
def update_register_values(register_values, values):
    while True:
        for register in register_values.values():
            type = register["type"]
            if type == "coil":
                modbus_value = values["co"].getValues(register["address"], register["count"])[0]
                register["value"] = modbus_value
            elif type == "discrete_input":
                modbus_value = values["di"].getValues(register["address"], register["count"])[0]
                register["value"] = modbus_value
            elif type == "holding_register":
                modbus_value = values["hr"].getValues(register["address"], register["count"])[0]
                register["value"] = modbus_value
            elif type == "input_register":
                modbus_value = values["ir"].getValues(register["address"], register["count"])[0]
                register["value"] = modbus_value

        '''
        # create a clone dictionary to hold the "to-be-updated" values
        updated_register_values = register_values.copy()

        # update the cloned copy with the real modbus values
        index = 0
        for co in register_values["coil"]:
            modbus_value = values["co"].getValues(co["address"], co["count"])[0]
            updated_register_values["coil"][index]["value"] = modbus_value
            index += 1
        index = 0
        for di in register_values["discrete_input"]:
            modbus_value = values["di"].getValues(di["address"], di["count"])[0]
            updated_register_values["discrete_input"][index]["value"] = modbus_value
            index += 1
        index = 0
        for hr in register_values["holding_register"]:
            modbus_value = values["hr"].getValues(hr["address"], hr["count"])[0]
            updated_register_values["holding_register"][index]["value"] = modbus_value
            index += 1
        index = 0
        for ir in register_values["input_register"]:
            modbus_value = values["ir"].getValues(ir["address"], ir["count"])[0]
            updated_register_values["input_register"][index]["value"] = modbus_value
            index += 1
        
        # update register values from the cloned copy
        register_values["coil"] = updated_register_values["coil"].copy()
        register_values["discrete_input"] = updated_register_values["discrete_input"].copy()
        register_values["holding_register"] = updated_register_values["holding_register"].copy()
        register_values["input_register"] = updated_register_values["input_register"].copy()
        '''


        time.sleep(0.1)



# FUNCTION: create_register_values_dict
# PURPOSE:  Returns a dictionary that is used to store all register values in the following format:
# {
#   id: 
#   {
#       "type": "coil",
#       "address": 1,
#       "count": 1,
#       "value": 0,
#       "io": "input"
#   }
# }
def create_register_values_dict(configs):
    register_values = {}

    for co in configs["registers"]["coil"]:
        register = {
            "type": "coil",
            "address": co["address"],
            "count": co["count"],
            "value": False
        }
        if "io" in co:
            register["io"] = co["io"]
        if "id" in co:
            register["id"] = co["id"]
            register_values[co["id"]] = register
        elif "physical_value" in co:
            register_values[co["physical_value"]] = register

    for di in configs["registers"]["discrete_input"]:
        register = {
            "type": "discrete_input",
            "address": di["address"],
            "count": di["count"],
            "value": False
        }
        if "io" in di:
            register["io"] = di["io"]
        if "id" in di:
            register["id"] = di["id"]
            register_values[di["id"]] = register
        elif "physical_value" in di:
            register_values[di["physical_value"]] = register

    for hr in configs["registers"]["holding_register"]:
        register = {
            "type": "holding_register",
            "address": hr["address"],
            "count": hr["count"],
            "value": False
        }
        if "io" in hr:
            register["io"] = hr["io"]
        if "id" in hr:
            register["id"] = hr["id"]
            register_values[hr["id"]] = register
        elif "physical_value" in hr:
            register_values[hr["physical_value"]] = register

    for ir in configs["registers"]["input_register"]:
        register = {
            "type": "input_register",
            "address": ir["address"],
            "count": ir["count"],
            "value": False
        }
        if "io" in ir:
            register["io"] = ir["io"]
        if "id" in ir:
            register["id"] = ir["id"]
            register_values[ir["id"]] = register
        elif "physical_value" in ir:
            register_values[ir["physical_value"]] = register

    return register_values