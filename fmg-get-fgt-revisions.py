"""
Script Name: FortiGate Revision Backup Script
Author: Prithvi Mandava
Date: 2025-03-03
Description:
    This script connects to a FortiManager instance and retrieves configuration revisions
    from all FortiGates in all ADOMs. It saves each configuration as a .conf file in 
    directories organized by ADOM. The script supports filtering revisions from a 
    specific start date and securely loads the API key from an external 'config.env' file.
    
Version: 1.0

Requirements:
    - Python 3.x
    - requests library (`pip install requests`)
    - python-dotenv library (`pip install python-dotenv`)
    - Config file: `config.env` containing `FMG_API_KEY=<your_api_key>`
"""

import requests
import json
import os
from datetime import datetime
from configparser import ConfigParser

# Load API key from external config file
config_file = "config.env"
config = ConfigParser()

# Check if the configuration file exists
if not os.path.exists(config_file):
    print(f"Error: Configuration file '{config_file}' not found.")
    exit(1)

# Read the configuration file
config.read(config_file)

# Get the API key from the configuration file
api_key = config.get("DEFAULT", "FMG_API_KEY", fallback=None)
if not api_key:
    print("Error: API key not found in the configuration file.")
    exit(1)

# FortiManager details
fmg_ip = "192.168.1.99"  # Replace with your FortiManager IP address
adom_filter_date = "2025-03-03"  # Replace with your desired start date (YYYY-MM-DD)
adom_filter_datetime = datetime.strptime(adom_filter_date, "%Y-%m-%d")

# Output directory for config files (relative to the script's directory)
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "config_revisions")

# Disable SSL warnings (not recommended for production)
requests.packages.urllib3.disable_warnings()

# Function to send API requests to FortiManager using an API key
def send_request(method, params):
    url = f"https://{fmg_ip}/jsonrpc"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "method": method,
        "params": params,
        "id": 1
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
    
    try:
        response_data = response.json()
        if "result" in response_data:
            return response_data["result"]
        else:
            print(f"Error: No 'result' in response data: {response_data}")
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response: {e}")
        print(f"Raw Response: {response.text}")
    
    return None

# Get all ADOMs
def get_adoms():
    params = [{"url": "/dvmdb/adom"}]
    result = send_request("get", params)
    if result and "data" in result[0]:
        return [adom["name"] for adom in result[0]["data"]]
    print("No ADOM data found.")
    return []

# Get all devices in a given ADOM
def get_devices(adom_name):
    params = [{"url": f"/dvmdb/adom/{adom_name}/device"}]
    result = send_request("get", params)
    if result and "data" in result[0]:
        devices = result[0]["data"]
        print(f"Devices in ADOM '{adom_name}': {[device['name'] for device in devices]}")
        return [device["name"] for device in devices]
    
    print(f"No devices found in ADOM: {adom_name}")
    return []

# Get configuration revisions using the correct API method
def get_config_revisions(adom_name, device_name):
    params = [{
        "url": "/deployment/get/device/revision",
        "data": {
            "adom": adom_name,
            "device": device_name
        }
    }]
    result = send_request("exec", params)
    
    if result and "data" in result[0]:
        revisions = result[0]["data"]
        if "revinfo" in revisions and isinstance(revisions["revinfo"], list):
            filtered_revisions = []
            for rev in revisions["revinfo"]:
                if "instime" in rev:
                    try:
                        rev_date = datetime.strptime(rev["instime"], "%Y-%m-%d %H:%M:%S")
                        if rev_date >= adom_filter_datetime:
                            filtered_revisions.append(rev)
                    except ValueError as e:
                        print(f"Date parsing error for revision: {rev} | Error: {e}")
            return filtered_revisions
        else:
            print(f"Unexpected 'revinfo' format or missing 'revinfo' key in revisions data.")
    
    print(f"No revision data found for device: {device_name} in ADOM: {adom_name}")
    return []

# Download the configuration for a specific revision
def download_config(adom_name, device_name, revision_id, timestamp):
    params = [{
        "url": "/deployment/checkout/revision",
        "data": {
            "adom": adom_name,
            "device": device_name,
            "revision": revision_id
        }
    }]
    result = send_request("exec", params)
    
    if result and "data" in result[0]:
        data = result[0]["data"]
        if "content" in data:
            config_data = data["content"]
            
            # Create directory for ADOM if it doesn't exist
            adom_dir = os.path.join(output_dir, adom_name)
            try:
                os.makedirs(adom_dir, exist_ok=True)
                print(f"Directory created or exists: {adom_dir}")
            except Exception as e:
                print(f"Error creating directory {adom_dir}: {e}")
                return
            
            # Generate the filename and save the config
            filename = f"{device_name}_{timestamp}.conf"
            file_path = os.path.join(adom_dir, filename)
            
            try:
                with open(file_path, "w") as f:
                    f.write(config_data)
                print(f"Configuration saved to {file_path}")
            except Exception as e:
                print(f"Error writing configuration to file {file_path}: {e}")
        else:
            print(f"Error: 'content' key not found in the response data: {data}")
    else:
        print(f"Failed to download configuration for device {device_name}, revision {revision_id}")

# Main function
def main():
    all_revisions = []
    adoms = get_adoms()
    for adom_name in adoms:
        devices = get_devices(adom_name)
        for device_name in devices:
            revisions = get_config_revisions(adom_name, device_name)
            if revisions:
                all_revisions.extend(revisions)
                for rev in revisions:
                    revision_id = rev["revision"]
                    timestamp = rev["instime"].replace(":", "-").replace(" ", "_")
                    download_config(adom_name, device_name, revision_id, timestamp)
    
    if not all_revisions:
        print("No revisions found for the specified date.")

# Run the script
if __name__ == "__main__":
    main()