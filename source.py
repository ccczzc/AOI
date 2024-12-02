import socket
import threading
import time
from sensor import Sensor, SensorData
import sys

class WiFreshSource:
    def __init__(self, listen_port, destination_address):
        self.listen_port = listen_port
        self.destination_address = destination_address
        self.lcfs_queue: list[SensorData] = []  # LCFS 队列
        self.fcfs_queue: list[SensorData] = []  # FCFS 碎片队列
        self.sensor = Sensor(listen_port)  # 传感器实例
        self.packet_header_size = 20  # 数据包头部大小
        self.max_packet_size = self.get_max_packet_size() - self.packet_header_size  # 获取最大数据包大小
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        # self.lock: threading.Lock = threading.Lock()  # 定义锁
        self.generation_rate = 7000  # 生成速率

    def get_max_packet_size(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_packet_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        sock.close()
        print(f"Max packet size: {max_packet_size}")
        return max_packet_size

    def start(self):
        threading.Thread(target=self.generate_updates).start()
        threading.Thread(target=self.listen_for_requests).start()
        print(f"WiFresh source started on port {self.listen_port}")

    def generate_updates(self):
        while True:
            info_update = self.sensor.generate_data()  # 生成传感器数据
            # print(f"Generated data from Source {self.listen_port}: {info_update}")
            # with self.lock:
            self.lcfs_queue.append(info_update)  # 添加到 LCFS 队列
            time.sleep(1/self.generation_rate)  # 设置lambda

    def listen_for_requests(self):
            while True:
                data, addr = self.sock.recvfrom(1024)
                if data.decode().startswith('POLL'):
                    self.process_poll()
                elif data.decode().startswith('TIME_SYNC'):
                    self.send_time_sync_response(addr)

    def process_poll(self):
        # with self.lock:
        if self.fcfs_queue:
            fragment = self.fcfs_queue.pop(0)  # 从 FCFS 队列获取下一个片段
            self.send_packet(fragment)
            return
        if self.lcfs_queue:
            info_update = self.lcfs_queue.pop()  # 从 LCFS 队列获取更新
            if len(info_update.data) <= self.max_packet_size:
                self.send_packet(info_update)
            else:
                all_data = info_update.data
                fragments = [info_update[i:i + self.max_packet_size] for i in range(0, len(all_data), self.max_packet_size)]
                for idx, fragment in enumerate(fragments):
                    self.fcfs_queue.append(SensorData(is_fragmented=(idx + 1 != len(fragments)), timestamp=info_update.timestamp, data=fragment))  # 添加到 FCFS 队列
                self.send_packet(self.fcfs_queue.pop(0))  # 发送第一个片段
        else:
            self.send_packet(SensorData(is_fragmented=0, timestamp=time.time(), data=''))  # 发送空数据包

    def send_packet(self, packet: SensorData):
        bytes_sent = self.sock.sendto(packet.to_str().encode(), self.destination_address)
        print(f"sent {bytes_sent} bytes to {self.destination_address}")
        print(f"Sent packet from Source {self.listen_port}: {packet}")

    def send_time_sync_response(self, addr):
        current_time = time.time()
        response = f"TIME_RESPONSE{current_time:010.7f}"
        self.sock.sendto(response.encode(), addr)
        print(f"Sent TIME_RESPONSE from Source {self.listen_port}: {current_time}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python source.py <listen_port> <destination_host> <destination_port>")
        sys.exit(1)

    listen_port = int(sys.argv[1])
    destination_host = sys.argv[2]
    destination_port = int(sys.argv[3])
    destination_address = (destination_host, destination_port)
    source1 = WiFreshSource(listen_port, destination_address)
    source1.start()