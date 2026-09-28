from collections import deque
from datetime import datetime, timezone
from threading import Lock
import json
import os
import time

import mysql.connector
import paho.mqtt.client as mqtt

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS


# ==================================================
# FLASK CONFIGURATION
# ==================================================

app = Flask(__name__)
CORS(app)


# ==================================================
# MYSQL CONFIGURATION
# ==================================================

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "database": os.getenv("DB_NAME", "weather_station"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def get_db_connection():
    """Tạo kết nối đến MySQL."""
    return mysql.connector.connect(**DB_CONFIG)


def save_sensor_data(record):
    """
    Lưu một bản ghi cảm biến vào MySQL.

    Trả về:
        True: Lưu thành công.
        False: Lưu thất bại.
    """

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # received_at được tạo theo UTC.
        # MySQL DATETIME không lưu thông tin timezone,
        # vì vậy lưu thời gian UTC dưới dạng datetime không timezone.
        received_at = (
            datetime.fromisoformat(record["received_at"])
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

        sql = """
            INSERT INTO sensor_data
                (temperature, humidity, light, status, received_at)
            VALUES
                (%s, %s, %s, %s, %s)
        """

        values = (
            record["temperature"],
            record["humidity"],
            record["light"],
            record["status"],
            received_at,
        )

        cursor.execute(sql, values)
        conn.commit()

        print("[MySQL] Sensor data saved successfully")
        return True

    except mysql.connector.Error as error:
        print(f"[MySQL] Save failed: {error}")
        return False

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None and conn.is_connected():
            conn.close()


# ==================================================
# MYSQL SAVE INTERVAL
# ==================================================

# ESP32 có thể gửi MQTT mỗi 2 giây,
# nhưng MySQL chỉ lưu một bản ghi mỗi 30 giây.

DB_SAVE_INTERVAL = 30

# Thời điểm thử lưu MySQL gần nhất.
# Dùng time.monotonic() để đo khoảng thời gian.
last_db_save_time = 0


# ==================================================
# MQTT CONFIGURATION
# Phải trùng với cấu hình trong main.cpp của ESP32
# ==================================================

MQTT_HOST = "test.mosquitto.org"
MQTT_PORT = 1883

MQTT_TOPIC = "iot/esp32/weather/giang0811/data"


# ==================================================
# DATA STORAGE
# ==================================================

# Dữ liệu mới nhất được giữ trong RAM.
latest_data = None

# Lịch sử tạm trong RAM, tối đa 100 bản ghi.
sensor_history = deque(maxlen=100)

data_lock = Lock()


# ==================================================
# MQTT CALLBACKS
# ==================================================

def on_connect(client, userdata, flags, reason_code, properties):
    """Được gọi khi backend kết nối MQTT Broker."""

    if reason_code.is_failure:
        print(f"[MQTT] Connection failed: {reason_code}")
        return

    print("[MQTT] Connected to broker")

    result, message_id = client.subscribe(MQTT_TOPIC)

    if result == mqtt.MQTT_ERR_SUCCESS:
        print(f"[MQTT] Subscribed to: {MQTT_TOPIC}")
    else:
        print(f"[MQTT] Subscribe failed: {result}")


def on_message(client, userdata, msg):
    """Xử lý dữ liệu cảm biến nhận được từ ESP32."""

    global latest_data
    global last_db_save_time

    try:
        # --------------------------------------------------
        # 1. Decode MQTT message
        # --------------------------------------------------

        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        # --------------------------------------------------
        # 2. Validate required fields
        # --------------------------------------------------

        required_fields = [
            "temperature",
            "humidity",
            "light",
            "status",
        ]

        for field in required_fields:
            if field not in data:
                print(f"[MQTT] Missing field: {field}")
                return

        # --------------------------------------------------
        # 3. Normalize sensor data
        # --------------------------------------------------

        record = {
            "temperature": float(data["temperature"]),
            "humidity": float(data["humidity"]),
            "light": str(data["light"]),
            "status": str(data["status"]),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        # --------------------------------------------------
        # 4. Update latest data and RAM history
        # --------------------------------------------------

        with data_lock:
            latest_data = record
            sensor_history.appendleft(record)

        # --------------------------------------------------
        # 5. Save to MySQL every 30 seconds
        # --------------------------------------------------

        now = time.monotonic()

        if now - last_db_save_time >= DB_SAVE_INTERVAL:

            # Cập nhật thời điểm thử lưu.
            # Nếu MySQL lỗi, backend sẽ thử lại sau 30 giây,
            # tránh tạo kết nối MySQL liên tục mỗi 2 giây.
            last_db_save_time = now

            save_sensor_data(record)

        # --------------------------------------------------
        # 6. Print received data
        # --------------------------------------------------

        print("[MQTT] Received sensor data:")
        print(record)

    except (UnicodeDecodeError, json.JSONDecodeError,
            ValueError, TypeError) as error:

        print(f"[MQTT] Invalid message: {error}")

    except Exception as error:
        print(f"[MQTT] Error processing message: {error}")


# ==================================================
# MQTT CLIENT
# ==================================================

mqtt_client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="weather-backend-giang",
)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


# ==================================================
# REST API
# ==================================================

@app.route("/api/health", methods=["GET"])
def health_check():
    """Kiểm tra backend."""

    return jsonify({
        "status": "ok",
        "service": "weather-station-backend",
    })


@app.route("/api/sensor/latest", methods=["GET"])
def get_latest_sensor_data():
    """Lấy dữ liệu cảm biến mới nhất từ RAM."""

    with data_lock:
        data = latest_data

    if data is None:
        return jsonify({
            "message": "Chưa nhận được dữ liệu từ ESP32",
        }), 404

    return jsonify(data)


@app.route("/api/sensor/history", methods=["GET"])
def get_sensor_history():
    """
    Lấy lịch sử cảm biến từ MySQL.

    Ví dụ:
        /api/sensor/history?limit=20
    """

    # --------------------------------------------------
    # 1. Read and validate limit
    # --------------------------------------------------

    try:
        limit = int(request.args.get("limit", 20))

    except ValueError:
        return jsonify({
            "error": "limit phải là số nguyên",
        }), 400

    # Chỉ cho phép lấy từ 1 đến 100 bản ghi.
    limit = max(1, min(limit, 100))

    conn = None
    cursor = None

    try:
        # --------------------------------------------------
        # 2. Connect to MySQL
        # --------------------------------------------------

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --------------------------------------------------
        # 3. Query history
        # --------------------------------------------------

        sql = """
            SELECT
                id,
                temperature,
                humidity,
                light,
                status,
                received_at
            FROM sensor_data
            ORDER BY id DESC
            LIMIT %s
        """

        cursor.execute(sql, (limit,))
        records = cursor.fetchall()

        # --------------------------------------------------
        # 4. Convert datetime to JSON-compatible string
        # --------------------------------------------------

        for record in records:
            if record["received_at"] is not None:
                record["received_at"] = (
                    record["received_at"].isoformat()
                )

        # --------------------------------------------------
        # 5. Return JSON response
        # --------------------------------------------------

        return jsonify({
            "count": len(records),
            "data": records,
        })

    except mysql.connector.Error as error:
        print(f"[MySQL] History query failed: {error}")

        return jsonify({
            "error": "Không thể truy vấn lịch sử dữ liệu",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None and conn.is_connected():
            conn.close()


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    # --------------------------------------------------
    # 1. Test MySQL connection
    # --------------------------------------------------

    print("[MySQL] Testing database connection...")

    try:
        conn = get_db_connection()
        conn.close()

        print("[MySQL] Connected successfully")

    except mysql.connector.Error as error:
        print(f"[MySQL] Connection failed: {error}")

    # --------------------------------------------------
    # 2. Start MQTT connection
    # --------------------------------------------------

    print("[MQTT] Starting connection...")

    mqtt_client.connect_async(
        MQTT_HOST,
        MQTT_PORT,
        keepalive=60,
    )

    mqtt_client.loop_start()

    # --------------------------------------------------
    # 3. Start Flask server
    # --------------------------------------------------

    print("[Flask] Starting backend on port 5000")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )