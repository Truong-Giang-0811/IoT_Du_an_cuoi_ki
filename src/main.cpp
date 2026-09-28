#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DHT.h"

#include "config.h"

// =========================
// WIFI CONFIGURATION
// =========================

const char* WIFI_SSID = WIFI_SSID_VALUE;
const char* WIFI_PASSWORD = WIFI_PASSWORD_VALUE;

// =========================
// MQTT CONFIGURATION
// =========================

const char* MQTT_SERVER = "test.mosquitto.org";
const int MQTT_PORT = 1883;

// Phải giống topic đang mở bằng mosquitto_sub
const char* MQTT_TOPIC = "iot/esp32/weather/giang0811/data";

// =========================
// PIN CONFIGURATION
// =========================

// DHT11
#define DHT_PIN 27
#define DHT_TYPE DHT11

// LDR
#define LDR_PIN 34

// 3 LED
#define LED_RED    25
#define LED_GREEN  26
#define LED_YELLOW 32

// Buzzer
#define BUZZER_PIN 23

// OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

#define OLED_SDA 21
#define OLED_SCL 22
#define OLED_ADDR 0x3C

// =========================
// OBJECTS
// =========================

DHT dht(DHT_PIN, DHT_TYPE);

Adafruit_SSD1306 display(
  SCREEN_WIDTH,
  SCREEN_HEIGHT,
  &Wire,
  -1
);

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// =========================
// THRESHOLDS
// =========================

const float TEMP_WARNING = 31.3;
const float TEMP_DANGER  = 31.8;

const float HUM_WARNING = 76.0;
const float HUM_DANGER  = 85.0;

// =========================
// MQTT TIMER
// =========================

unsigned long lastPublish = 0;
const unsigned long PUBLISH_INTERVAL = 2000;

// =========================
// LED CONTROL
// =========================

void allLEDOff() {
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_YELLOW, LOW);
}

void ledGreen() {
  allLEDOff();
  digitalWrite(LED_GREEN, HIGH);
}

void ledYellow() {
  allLEDOff();
  digitalWrite(LED_YELLOW, HIGH);
}

void ledRed() {
  allLEDOff();
  digitalWrite(LED_RED, HIGH);
}

// =========================
// BUZZER
// =========================

void buzzerOn() {
  tone(BUZZER_PIN, 2000);
}

void buzzerOff() {
  noTone(BUZZER_PIN);
}

// =========================
// OLED
// =========================

void showOLED(
  float temperature,
  float humidity,
  bool isDark,
  String status
) {
  display.clearDisplay();

  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);

  display.setCursor(0, 0);
  display.print("Temp: ");
  display.print(temperature, 1);
  display.println(" C");

  display.setCursor(0, 15);
  display.print("Hum : ");
  display.print(humidity, 1);
  display.println(" %");

  display.setCursor(0, 30);
  display.print("Light: ");

  if (isDark) {
    display.println("DARK");
  } else {
    display.println("BRIGHT");
  }

  display.setCursor(0, 45);
  display.print("Status: ");
  display.println(status);

  display.display();
}

// =========================
// WIFI
// =========================

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("Connecting to Wi-Fi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connected");

  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

// =========================
// MQTT
// =========================

void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT... ");

    String clientId = "ESP32-Weather-";
    clientId += String(
      (uint32_t)(ESP.getEfuseMac() & 0xFFFFFFFF),
      HEX
    );

    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected");
    } else {
      Serial.print("failed, state = ");
      Serial.println(mqttClient.state());

      delay(3000);
    }
  }
}

void publishMQTT(
  float temperature,
  float humidity,
  bool isDark,
  String status
) {
  if (!mqttClient.connected()) {
    return;
  }

  char payload[200];

  snprintf(
    payload,
    sizeof(payload),
    "{\"temperature\":%.1f,\"humidity\":%.1f,\"light\":\"%s\",\"status\":\"%s\"}",
    temperature,
    humidity,
    isDark ? "DARK" : "BRIGHT",
    status.c_str()
  );

  bool success = mqttClient.publish(MQTT_TOPIC, payload);

  Serial.print("MQTT topic: ");
  Serial.println(MQTT_TOPIC);

  Serial.print("MQTT payload: ");
  Serial.println(payload);

  if (success) {
    Serial.println("MQTT publish success");
  } else {
    Serial.println("MQTT publish failed");
  }
}

// =========================
// SETUP
// =========================

void setup() {
  Serial.begin(115200);

  // DHT11
  dht.begin();

  // 3 LED
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);

  allLEDOff();

  // Buzzer
  pinMode(BUZZER_PIN, OUTPUT);
  buzzerOff();

  // LDR
  pinMode(LDR_PIN, INPUT);

  // OLED
  Wire.begin(OLED_SDA, OLED_SCL);

  if (!display.begin(
        SSD1306_SWITCHCAPVCC,
        OLED_ADDR
      )) {
    Serial.println("OLED ERROR!");

    while (true) {
      delay(100);
    }
  }

  // Starting screen
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);

  display.setCursor(10, 20);
  display.println("WEATHER STATION");

  display.setCursor(20, 40);
  display.println("Starting...");

  display.display();

  // Wi-Fi và MQTT
  connectWiFi();

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setBufferSize(256);

  delay(2000);
}

// =========================
// LOOP
// =========================

void loop() {
  // =========================
  // WIFI AND MQTT CONNECTION
  // =========================

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (!mqttClient.connected()) {
    connectMQTT();
  }

  mqttClient.loop();

  // =========================
  // READ DHT11
  // =========================

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  // =========================
  // CHECK DHT11
  // =========================

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("DHT11 ERROR!");

    allLEDOff();
    buzzerOff();

    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(20, 25);
    display.println("DHT11 ERROR");

    display.display();

    delay(2000);
    return;
  }

  // =========================
  // READ LDR
  // =========================

  int lightState = digitalRead(LDR_PIN);

  // Giữ nguyên logic trong code bạn gửi:
  // HIGH = DARK
  // LOW  = BRIGHT
  bool isDark = (lightState == HIGH);

  // =========================
  // DETERMINE STATUS
  // =========================

  String status;

  if (
    temperature >= TEMP_DANGER ||
    humidity >= HUM_DANGER
  ) {
    status = "DANGER";

    ledRed();
    buzzerOn();
  }
  else if (
    temperature >= TEMP_WARNING ||
    humidity >= HUM_WARNING
  ) {
    status = "WARNING";

    ledYellow();
    buzzerOff();
  }
  else {
    status = "NORMAL";

    ledGreen();
    buzzerOff();
  }

  // =========================
  // OLED
  // =========================

  showOLED(
    temperature,
    humidity,
    isDark,
    status
  );

  // =========================
  // SERIAL MONITOR
  // =========================

  Serial.println("============================");

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" C");

  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");

  Serial.print("Light: ");
  Serial.println(isDark ? "DARK" : "BRIGHT");

  Serial.print("Status: ");
  Serial.println(status);

  // =========================
  // MQTT PUBLISH
  // =========================

  if (millis() - lastPublish >= PUBLISH_INTERVAL) {
    lastPublish = millis();

    publishMQTT(
      temperature,
      humidity,
      isDark,
      status
    );
  }

  Serial.println("============================");

  delay(2000);
}