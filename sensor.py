import random
import time
import json
import struct
from enum import Enum

class DataType(Enum):
    TIME_REQUEST = 0
    GENERAL = 1
    POSITION = 2
    INERTIAL_MEASUREMENT = 3
    IMAGE = 4

class SensorData:
    header_size = 10  # 静态属性，设为10

    def __init__(
        self, 
        is_fragmented, 
        data_type: DataType, 
        timestamp: float,
        data: bytes
    ):
        self.is_fragmented = is_fragmented  # 1个字节，unsigned char，0或1
        self.data_type = data_type  # 1个字节，unsigned char，最多8类
        self.timestamp = timestamp  # 8个字节，float64
        self.data = data  # 数据

    def to_bytes(self):
        # 打包头部
        header = struct.pack('>BBd', self.is_fragmented, self.data_type.value, self.timestamp)
        return header + self.data

    @staticmethod
    def from_bytes(data_bytes):
        # 解包头部
        header = data_bytes[:SensorData.header_size]
        is_fragmented, data_type, timestamp = struct.unpack('>BBd', header)
        data = data_bytes[SensorData.header_size:]
        return SensorData(is_fragmented, DataType(data_type), timestamp, data)

    def __len__(self):
        return len(self.to_bytes())

    def __str__(self):
        return f"SensorData(is_fragmented={self.is_fragmented}, type={self.data_type}, timestamp={self.timestamp}, data={self.data})"

class Sensor:
    def __init__(
        self,
        data_type: DataType,
        packet_size: int,
        generation_rate: float,
    ):
        self.data_type = data_type
        self.packet_size = packet_size  # 增加packet_size属性
        self.data_size = packet_size - SensorData.header_size  # 计算数据部分大小
        self.generation_interval = 1.0 / generation_rate
        self.last_generation_time = time.time() - self.generation_interval
        self.lcfs_queue: list[SensorData] = []  # LCFS queue
        self.fcfs_queue: list[SensorData] = []  # FCFS fragment queue

    def generate_data(self):
        if time.time() - self.last_generation_time < self.generation_interval:
            return
        # 模拟传感器数据生成
        sensor_data = SensorData(
            is_fragmented=0,
            data_type=self.data_type,  # 示例类型
            timestamp=time.time(),
            data=bytes(random.getrandbits(8) for _ in range(self.data_size))
        )
        self.last_generation_time = time.time()
        self.lcfs_queue.append(sensor_data)