## Chạy Backend
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
## Khởi tạo DB
Mở phpmyadmin để tạo CSDL weather_station

```SQL
CREATE DATABASE weather_station
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE weather_station;

CREATE TABLE sensor_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    temperature FLOAT NOT NULL,
    humidity FLOAT NOT NULL,
    light VARCHAR(10) NOT NULL,
    status VARCHAR(10) NOT NULL,
    received_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
## Tạo file .env 
DB_HOST=localhost
DB_PORT=3306
DB_NAME=weather_station
DB_USER=root
DB_PASSWORD=