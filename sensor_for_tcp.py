# sensor_for_tcp.py
import random
import struct
from enum import Enum
import time

class DataType(Enum):
    TIME_REQUEST = 0
    GENERAL = 1
    POSITION = 2
    INERTIAL_MEASUREMENT = 3
    IMAGE = 4

class SensorData:
    header_size = 11  # is_fragmented (1 byte) + data_type (1 byte) + source_id (1 byte) + timestamp (8 bytes)

    def __init__(
        self,
        is_fragmented,
        data_type: DataType,
        timestamp: float,
        source_id: int,
        data: bytes
    ):
        self.is_fragmented = is_fragmented
        self.data_type = data_type
        self.timestamp = timestamp
        self.source_id = source_id
        self.data = data

    def to_bytes(self):
        # 构建消息体（头部 + 数据）
        header = struct.pack('>BBBd', self.is_fragmented, self.data_type.value, self.source_id, self.timestamp)
        payload = header + self.data
        # 计算总长度（不包括长度前缀）
        total_length = len(payload)
        # 添加 4 字节的长度前缀
        length_prefix = struct.pack('>I', total_length)
        # 返回完整的消息
        return length_prefix + payload

    @staticmethod
    def from_bytes(data_bytes):
        # 检查是否有足够的数据读取长度前缀
        if len(data_bytes) < 4:
            return None, data_bytes  # 数据不足，等待更多数据
        # 读取长度前缀
        total_length = struct.unpack('>I', data_bytes[:4])[0]
        if len(data_bytes) < 4 + total_length:
            return None, data_bytes  # 数据未接收完整，等待更多数据
        # 提取消息体
        payload = data_bytes[4:4+total_length]
        header = payload[:SensorData.header_size]
        data = payload[SensorData.header_size:]
        # 解析头部
        is_fragmented, data_type_value, source_id, timestamp = struct.unpack('>BBBd', header)
        data_type = DataType(data_type_value)
        # 创建 SensorData 实例
        sensor_data = SensorData(is_fragmented, data_type, timestamp, source_id, data)
        # 返回解析得到的 SensorData 对象和剩余的数据
        remaining_bytes = data_bytes[4+total_length:]
        return sensor_data, remaining_bytes

    def __len__(self):
        return len(self.to_bytes())

    def __str__(self):
        return f"SensorData(is_fragmented={self.is_fragmented}, type={self.data_type}, timestamp={self.timestamp}, source_id={self.source_id}, data_length={len(self.data)})"
class Sensor:
    def __init__(
        self,
        data_type: DataType,
        packet_size: int,
        generation_rate: float,
        source_id: int  # New field
    ):
        self.data_type = data_type
        self.packet_size = packet_size  # 增加packet_size属性
        self.data_size = packet_size - SensorData.header_size  # 计算数据部分大小
        self.generation_interval = 1.0 / generation_rate
        self.last_generation_time = time.time() - self.generation_interval
        self.complete_data_queue: list[SensorData] = []
        self.fragment_data_queue: list[SensorData] = []  # FCFS fragment queue
        self.source_id = source_id

    def generate_data(self):
        if time.time() - self.last_generation_time < self.generation_interval:
            return
        # 模拟传感器数据生成
        sensor_data = SensorData(
            is_fragmented=0,
            data_type=self.data_type,  # 示例类型
            timestamp=time.time(),
            source_id=self.source_id,  # New field
            data=bytes(random.getrandbits(8) for _ in range(self.data_size))
        )
        self.last_generation_time = time.time()
        self.complete_data_queue.append(sensor_data)