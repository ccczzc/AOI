import select
import socket
import threading
import time
from sensor import Sensor, SensorData
import sys

class WiFreshSource:
    def __init__(self, listen_port, destination_address):
        self.listen_port = listen_port
        self.destination_address = destination_address
        self.fcfs_queue: list[SensorData] = []  # FCFS fragment queue
        self.sensor = Sensor(listen_port)  # 传感器实例
        self.packet_header_size = 20  # 数据包头部大小
        self.max_packet_size = self.get_max_packet_size() - self.packet_header_size  # 获取最大数据包大小
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.generation_rate = 7000  # 生成速率
        self.clock_offset = 0.0  # 时钟偏移
        self.sync_interval = 5  # 时钟同步间隔（秒）
        self.last_sync_time = time.time()
        self.sync_rounds = 5  # 每次同步的消息数量
        self.alpha = 0.02  # 时钟偏移调整的平滑因子（0 < alpha <= 1）

    def get_max_packet_size(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_packet_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        sock.close()
        return max_packet_size

    def start(self):
        print(f"WiFresh source started on port {self.listen_port}")
        self.run()

    def run(self):
        self.sock.setblocking(False)
        last_generation_time = time.time()
        generation_interval = 1.0 / self.generation_rate
        while True:
            # 检查是否需要进行时钟同步
            if time.time() - self.last_sync_time >= self.sync_interval:
                self.clock_synchronization()
                self.last_sync_time = time.time()

            # 处理接收的消息
            readable, _, _ = select.select([self.sock], [], [], 0)
            if readable:
                data, addr = self.sock.recvfrom(1024)
                data_str = data.decode()
                if data_str.startswith('TIME_RESPONSE'):
                    # 处理时钟同步响应
                    parts = data_str.split(':')
                    if len(parts) == 3:
                        dest_time = float(parts[1])
                        t1 = float(parts[2])
                        t2 = time.time()
                        offset = dest_time - ((t1 + t2) / 2)
                        # 使用指数移动平均更新时钟偏移
                        self.clock_offset = self.alpha * offset + (1 - self.alpha) * self.clock_offset
                        print(f"Updated clock offset: {self.clock_offset} seconds")
                else:
                    print(f"Received unknown message from {addr}: {data_str}")
                    
            now = time.time()
            if now - last_generation_time >= generation_interval:
                # 生成传感器数据
                info_update = self.sensor.generate_data()
                # 使用时钟偏移调整时间戳
                info_update.timestamp += self.clock_offset
                self.fcfs_queue.append(info_update)
                try:
                    self.send_packet(self.fcfs_queue[0])
                    self.fcfs_queue.pop(0)
                except BlockingIOError:
                    print("source run send_packet BlockingIOError")
                last_generation_time = now

    def send_packet(self, packet: SensorData):
        bytes_sent = self.sock.sendto(packet.to_str().encode(), self.destination_address)
        # print(f"Sent {bytes_sent} bytes to {self.destination_address}")

    def clock_synchronization(self):
        for _ in range(self.sync_rounds):
            # 发送 TIME_REQUEST 到目的地
            current_time = time.time()
            request = f"TIME_REQUEST:{current_time:010.15f}"
            try:
                self.sock.sendto(request.encode(), self.destination_address)
            except BlockingIOError:
                print("source clock_synchronization sendto BlockingIOError")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python source.py <listen_port> <destination_host> <destination_port>")
        sys.exit(1)

    listen_port = int(sys.argv[1])
    destination_host = sys.argv[2]
    destination_port = int(sys.argv[3])
    destination_address = (destination_host, destination_port)
    source = WiFreshSource(listen_port=listen_port, destination_address=destination_address)
    source.start()