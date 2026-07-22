// AIP Scout — ESP32-S3 micro-ROS firmware.
//
// Publishes:
//   /<ns>/odom         (nav_msgs/Odometry)       ~20 Hz
//   /<ns>/heartbeat    (aip_fleet_msgs/FleetHeartbeat)  2 Hz
//   /<ns>/battery      (sensor_msgs/BatteryState)  1 Hz
// Subscribes:
//   /<ns>/cmd_vel      (geometry_msgs/Twist)
//   /<ns>/estop        (std_msgs/Bool)
//
// The namespace is stored in NVS under key "scout_ns" and defaults to
// DEFAULT_SCOUT_NS at first boot. Use SerialCommand `set_ns scout_2` to
// change it without rebuilding.

#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>

#include <micro_ros_platformio.h>
#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <geometry_msgs/msg/twist.h>
#include <nav_msgs/msg/odometry.h>
#include <sensor_msgs/msg/battery_state.h>
#include <std_msgs/msg/bool.h>
// NOTE: aip_fleet_msgs generates C headers when you build micro-ROS with the
// package in agent_ws; the include path becomes <aip_fleet_msgs/msg/fleet_heartbeat.h>.
#include <aip_fleet_msgs/msg/fleet_heartbeat.h>
#include <rosidl_runtime_c/string_functions.h>

#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) { Serial.printf("RCCHECK fail %d\n", (int)rc); } }

Preferences prefs;
static char g_ns[32] = DEFAULT_SCOUT_NS;

static rcl_publisher_t pub_odom;
static rcl_publisher_t pub_heartbeat;
static rcl_publisher_t pub_battery;
static rcl_subscription_t sub_cmd_vel;
static rcl_subscription_t sub_estop;

static geometry_msgs__msg__Twist cmd_vel_msg;
static std_msgs__msg__Bool estop_msg;
static nav_msgs__msg__Odometry odom_msg;
static aip_fleet_msgs__msg__FleetHeartbeat hb_msg;
static sensor_msgs__msg__BatteryState battery_msg;

static volatile bool g_estop = false;

static void cmd_vel_cb(const void *arg) {
    const auto *msg = static_cast<const geometry_msgs__msg__Twist *>(arg);
    if (g_estop) return;
    // TODO: map msg->linear.x, msg->angular.z → motor PWM via the
    // low-level motor driver (the vehicle-SW teammate owns that).
    Serial.printf("cmd_vel vx=%.2f wz=%.2f\n", msg->linear.x, msg->angular.z);
}

static void estop_cb(const void *arg) {
    const auto *msg = static_cast<const std_msgs__msg__Bool *>(arg);
    g_estop = msg->data;
    if (g_estop) {
        Serial.println("*** ESTOP asserted ***");
        // TODO: hard-kill motor outputs.
    } else {
        Serial.println("ESTOP cleared");
    }
}

static void load_namespace() {
    prefs.begin("aip", true);
    auto n = prefs.getString("scout_ns", DEFAULT_SCOUT_NS);
    n.toCharArray(g_ns, sizeof(g_ns));
    prefs.end();
    Serial.printf("Scout namespace: %s\n", g_ns);
}

// H8: Validate namespace format before writing to NVS.
// Accepts [a-z][a-z0-9_]{0,30} — mirrors ROS2 node name rules.
static bool ns_valid(const String &s) {
    if (s.length() == 0 || s.length() > 31) return false;
    if (!islower((uint8_t)s[0])) return false;
    for (size_t i = 1; i < s.length(); ++i) {
        char c = s[i];
        if (!islower((uint8_t)c) && !isdigit((uint8_t)c) && c != '_') return false;
    }
    return true;
}

static void handle_serial_config() {
    // Hold BOOT + send "set_ns scout_2" over serial within 3 s of power up
    // to rewrite the namespace.
    unsigned long t0 = millis();
    while (millis() - t0 < 3000) {
        if (Serial.available()) {
            String line = Serial.readStringUntil('\n');
            line.trim();
            if (line.startsWith("set_ns ")) {
                String n = line.substring(7);
                if (!ns_valid(n)) {
                    Serial.println("ERROR: namespace must match [a-z][a-z0-9_]{0,30}");
                    continue;
                }
                prefs.begin("aip", false);
                prefs.putString("scout_ns", n);
                prefs.end();
                Serial.printf("Namespace persisted: %s\n", n.c_str());
                ESP.restart();
            }
        }
        delay(50);
    }
}

void setup() {
    Serial.begin(115200);
    delay(300);
    handle_serial_config();
    load_namespace();

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) {
        delay(200);
        Serial.print(".");
    }
    Serial.printf("\nWi-Fi ok, IP=%s\n", WiFi.localIP().toString().c_str());

    IPAddress agent_ip;
    agent_ip.fromString(AGENT_IP);
    set_microros_wifi_transports(WIFI_SSID, WIFI_PASS, agent_ip, AGENT_PORT);
    delay(1000);

    rclc_support_t support;
    rcl_allocator_t allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, nullptr, &allocator));

    rcl_node_t node;
    RCCHECK(rclc_node_init_default(&node, "scout_node", g_ns, &support));

    char topic[64];

    snprintf(topic, sizeof(topic), "/%s/odom", g_ns);
    RCCHECK(rclc_publisher_init_default(
        &pub_odom, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry), topic));

    snprintf(topic, sizeof(topic), "/%s/heartbeat", g_ns);
    RCCHECK(rclc_publisher_init_default(
        &pub_heartbeat, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(aip_fleet_msgs, msg, FleetHeartbeat), topic));

    snprintf(topic, sizeof(topic), "/%s/battery", g_ns);
    RCCHECK(rclc_publisher_init_default(
        &pub_battery, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, BatteryState), topic));

    snprintf(topic, sizeof(topic), "/%s/cmd_vel", g_ns);
    RCCHECK(rclc_subscription_init_default(
        &sub_cmd_vel, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist), topic));

    snprintf(topic, sizeof(topic), "/%s/estop", g_ns);
    RCCHECK(rclc_subscription_init_default(
        &sub_estop, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool), topic));

    rclc_executor_t executor;
    RCCHECK(rclc_executor_init(&executor, &support.context, 2, &allocator));
    RCCHECK(rclc_executor_add_subscription(
        &executor, &sub_cmd_vel, &cmd_vel_msg, &cmd_vel_cb, ON_NEW_DATA));
    RCCHECK(rclc_executor_add_subscription(
        &executor, &sub_estop, &estop_msg, &estop_cb, ON_NEW_DATA));

    unsigned long last_hb = 0;
    unsigned long last_batt = 0;

    while (true) {
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(20));

        unsigned long now = millis();
        if (now - last_hb > 500) {
            last_hb = now;
            rosidl_runtime_c__String__assign(&hb_msg.vehicle_id, g_ns);
            hb_msg.state = g_estop ? 3 /*ESTOP*/ : 1 /*AUTO*/;
            hb_msg.battery_pct = 80.0f;  // TODO: read ADC
            hb_msg.cpu_load = 0.1f;
            rcl_publish(&pub_heartbeat, &hb_msg, nullptr);
        }
        if (now - last_batt > 1000) {
            last_batt = now;
            battery_msg.percentage = 0.80f;
            battery_msg.present = true;
            rcl_publish(&pub_battery, &battery_msg, nullptr);
        }
        // TODO: publish odom from wheel encoders.
    }
}

void loop() {
    // unused — work happens in setup()'s infinite spin.
}
