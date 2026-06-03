#!/usr/bin/env python3

# -----------------------------------------------------------------------------
# Project: Curtin ICS-SimLab
# File: sensor.py
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

# FILE PURPOSE: Simulates a sensor. Takes input from a simulated physical process.

import asyncio
import sqlite3
import logging
import time
import utils
from flask import Flask, jsonify
from threading import Thread
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusDeviceContext, ModbusServerContext

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)

# global values (only used for Flask endpoints)
register_values = {}



# FUNCTION: start_servers
# PURPOSE:  Starts any tcp/rtu servers configured in the config file
async def start_servers(configs, context):
    tasks = []
    for connection in configs["inbound_connections"]:
        if connection["type"] == "tcp":            
            # start tcp server thread
            tasks.append(asyncio.create_task(utils.run_tcp_server(connection, context)))
        elif connection["type"] == "rtu":
            # start rtu slave thread
            tasks.append(asyncio.create_task(utils.run_rtu_slave(connection, context)))        
    for task in tasks:
        await task



# FUNCTION: start_sensor
# PURPOSE:  Starts a process to read sensor data from SQLite specific to this sensor.
#           The column is a TEXT datatype to allow for generic inputs. The input "registers"
#           is a dictonary with ModbusSequentialDataBlock values, corresponding to co
#           di, hr, and ir as keys.
def start_sensor(configs, values):
    # connect to hardware SQLite database
    conn = sqlite3.connect("physical_interactions.db")
    cursor = conn.cursor()
    
    while True:
        # gets values for all value types from the physical databases
        value = ""
        for co in configs["registers"]["coil"]:
            address = co["address"]
            table = co["physical_value"]
            cursor.execute(f"SELECT value FROM {table} ORDER BY timestamp DESC LIMIT 1")
            value = cursor.fetchone()
            conn.commit()

            if value and value[0] not in (None, ""):
                values["co"].setValues(address, int(float(value[0])))
        for di in configs["registers"]["discrete_input"]:
            address = di["address"]
            table = di["physical_value"]
            cursor.execute(f"SELECT value FROM {table} ORDER BY timestamp DESC LIMIT 1")
            value = cursor.fetchone()
            conn.commit()

            if value and value[0] not in (None, ""):
                values["di"].setValues(address, int(float(value[0])))
        for hr in configs["registers"]["holding_register"]:
            address = hr["address"]
            table = hr["physical_value"]
            cursor.execute(f"SELECT value FROM {table} ORDER BY timestamp DESC LIMIT 1")
            value = cursor.fetchone()
            conn.commit()

            if value and value[0] not in (None, ""):
                values["hr"].setValues(address, int(float(value[0])))
        for ir in configs["registers"]["input_register"]:
            address = ir["address"]
            table = ir["physical_value"]
            cursor.execute(f"SELECT value FROM {table} ORDER BY timestamp DESC LIMIT 1")
            value = cursor.fetchone()
            conn.commit()

            if value and value[0] not in (None, ""):
                values["ir"].setValues(address, int(float(value[0])))

        time.sleep(0.1)



# define the flask endpoint
@app.route("/registers", methods=['GET'])
def get_registers_route():
    global register_values
    return jsonify(register_values)

# define function to run flask in another thread
def flask_app(flask_app):
    flask_app.run(host="0.0.0.0", port=1111)

# FUNCTION: main
# PURPOSE:  The main execution
async def main():
    global register_values

    # retrieve configurations from the given JSON (will be in the same directory)
    configs = utils.retrieve_configs("config.json")
    logging.info(f"Starting Sensor")

    # create device context (by default will have all address ranges)
    co = ModbusSequentialDataBlock.create()
    di = ModbusSequentialDataBlock.create()
    hr = ModbusSequentialDataBlock.create()
    ir = ModbusSequentialDataBlock.create()
    device_context = ModbusDeviceContext(co=co, di=di, hr=hr, ir=ir)
    context = ModbusServerContext(devices=device_context, single=True)

    # start any configured servers (tcp, rtu or both) with the same context
    values = {"co": co, "di": di, "hr": hr, "ir": ir}
    server_task = start_servers(configs, context)

    # create a dictionary representing all register values
    register_values = utils.create_register_values_dict(configs)

    # start the sensor reading thread
    sensor_thread = Thread(target=start_sensor, args=(configs, values), daemon=True)
    sensor_thread.start()

    # start a thread to continously update the registers dictionary
    sync_registers = Thread(target=utils.update_register_values, args=(register_values, values), daemon=True)
    sync_registers.start()

    # start the flask endpoint
    flask_thread = Thread(target=flask_app, args=(app,), daemon=True)
    flask_thread.start()

    # await tasks and threads
    await server_task
    sensor_thread.join()
    sync_registers.join()
    flask_thread.join()


if __name__ == "__main__":
    asyncio.run(main())
