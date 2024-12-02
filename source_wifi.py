import socket
import threading
import time
from sensor import Sensor, SensorData
import sys

class WiFreshSource:
    def __init__(self, listen_port, destination_address):
        self.listen_port = listen_port
        self.destination_address = destination_address
        self.sensor = Sensor(listen_port)  # 传感器实例
        self.packet_header_size = 20  # 数据包头部大小
        self.max_packet_size = self.get_max_packet_size() - self.packet_header_size  # 获取最大数据包大小
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.generation_rate = 7000  # 生成速率

    def get_max_packet_size(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_packet_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        sock.close()
        print(f"Max packet size: {max_packet_size}")
        return max_packet_size

    def start(self):
        print(f"WiFresh source started on port {self.listen_port}")
        self.send_updates()

    def send_updates(self):
        while True:
            data = self.sensor.generate_data().to_str()  # 获取传感器数据
            bytes_sent = self.sock.sendto(data.encode(), self.destination_address)
            print(f"sent {bytes_sent} bytes to {self.destination_address}")
            print(f"Sent data to {self.destination_address}: {data}")
            time.sleep(1/self.generation_rate)

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python source.py <listen_port> <destination_host> <destination_port>")
        sys.exit(1)

    listen_port = int(sys.argv[1])
    destination_host = sys.argv[2]
    destination_port = int(sys.argv[3])
    destination_address = (destination_host, destination_port)
    source = WiFreshSource(listen_port=8000, destination_address=destination_address)
    source.start()