import random
import time
import json

class SensorData:
    def __init__(self, is_fragmented, timestamp, data):
        self.is_fragmented = is_fragmented # 是否分片，占用 2 字节, 0 为否，1 为是
        self.timestamp = timestamp # 时间戳，占用 18 字节，精度为 10.7f
        self.data = data # 数据

    def to_str(self):
        # 转换 is_fragmented 为2字节字符串
        fragmented_str = f"{self.is_fragmented:02}"
        # 转换 timestamp 为18字节字符串，保留7位小数
        timestamp_str = f"{self.timestamp:010.7f}".ljust(18)
        # 合并为固定20字节头部
        header = fragmented_str + timestamp_str
        return header + self.data
    
    def __len__(self):
        return len(self.to_str())
    
    def from_str(data_str):
        # 解析头部
        fragmented_str = data_str[:2]
        timestamp_str = data_str[2:20]
        data = data_str[20:]
        # 解析 is_fragmented
        is_fragmented = int(fragmented_str)
        # 解析 timestamp
        timestamp = float(timestamp_str)
        return SensorData(is_fragmented, timestamp, data)
    
    def __str__(self):
        return f"SensorData(is_fragmented={self.is_fragmented}, timestamp={self.timestamp}, data={self.data})"

class Sensor:
    def __init__(self, sensor_id):
        self.sensor_id = sensor_id

    def generate_data(self):
        # 模拟传感器数据生成
        data = {
            "sensor_id": self.sensor_id,
            "temperature": random.uniform(20.0, 30.0),
            "humidity": random.uniform(30.0, 70.0),
            "pressure": random.uniform(950.0, 1050.0),
            "battery_level": random.uniform(0.0, 100.0),
            "status": random.choice(["OK", "WARN", "ERROR"]),
            "wind_speed": random.uniform(0.0, 15.0),
            "wind_direction": random.choice(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]),
            "rainfall": random.uniform(0.0, 50.0),
            "light_intensity": random.uniform(0.0, 1000.0),
            "soil_moisture": random.uniform(0.0, 100.0),
            "CO2_level": random.uniform(300.0, 500.0),
            "noise_level": random.uniform(30.0, 100.0)
        }
        return SensorData(
            is_fragmented=0,
            timestamp=time.time(),
            data=
        json.dumps(data).ljust(130)[:130]
        )