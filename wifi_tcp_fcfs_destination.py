import argparse
import socket
import select
import time
import os
import struct
from typing import List, Tuple
from sensor_for_tcp import DataType, SensorData

class SourceState:
    def __init__(self):
        self.weight: float = 0
        self.last_systime_received: float = time.time()
        self.last_recorded_age = 0.0
        self.total_weighted_ages: float = 0.0

class WiFiTCPFcfsDestination:
    def __init__(
        self, 
        sources_addresses: List[Tuple[int, DataType]],  # Changed to use source_id
        listen_port=9999, 
        age_record_dir='./ages_wifi_tcp_fcfs',
        age_record_interval=1e-4
    ):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.sock.listen()
        self.sources_state: dict[Tuple[int, DataType], SourceState] = {}
        self.age_record_dir = age_record_dir
        os.makedirs(age_record_dir, exist_ok=True)
        for source_id, data_type in sources_addresses:
            self.sources_state[(source_id, data_type)] = SourceState()
            print(f"Added source {source_id} {data_type}")
        self.age_record_interval = age_record_interval
        self.last_age_record_time = time.time() - self.age_record_interval
        self.start_time = time.time()
        self.running_period = 600.0
        self.client_sockets = []
        self.recv_buffers = {}  # Key: socket, Value: bytearray

    def start(self):
        print("WiFi TCP FCFS destination started")
        self.sock.setblocking(False)
        while True:
            self.accept_connections()
            self.receive_data()
            if time.time() - self.last_age_record_time >= self.age_record_interval:
                self.record_age()
            if time.time() - self.start_time >= self.running_period:
                self.save_ages()
                print("WiFi TCP FCFS destination stopped")
                break

    def accept_connections(self):
        try:
            conn, addr = self.sock.accept()
            conn.setblocking(False)
            self.client_sockets.append(conn)
            self.recv_buffers[conn] = bytearray()
            print(f"Accepted connection from {addr}")
        except BlockingIOError:
            pass

    def save_ages(self):
        record_file_path = os.path.join(self.age_record_dir, f"ages_{len(self.sources_state)}sources.txt")
        with open(record_file_path, 'w') as record_file:
            mean_ages = []
            for source_address, source in self.sources_state.items():
                mean_age = source.total_weighted_ages / self.running_period
                record_file.write(f"{source_address[0]}_{source_address[1]}: {mean_age}\n")
                mean_ages.append(mean_age)
            if mean_ages:
                record_file.write(f"Mean AOI of all data sources: {sum(mean_ages) / len(mean_ages)}\n")

    def record_age(self):
        for source in self.sources_state.values():
            current_time = time.time()
            age = current_time - source.last_systime_received
            age_area = (age + source.last_recorded_age) * (current_time - self.last_age_record_time) / 2
            source.total_weighted_ages += age_area
            source.last_recorded_age = age
        self.last_age_record_time = time.time()

    def receive_data(self):
        if not self.client_sockets:
            return
        readable, _, exceptional = select.select(self.client_sockets, [], self.client_sockets, 0)
        for sock in readable:
            try:
                data_bytes = sock.recv(4096)
                if not data_bytes:
                    self.close_connection(sock)
                    continue
                # 将接收到的数据添加到缓冲区
                self.recv_buffers[sock].extend(data_bytes)
                # 处理缓冲区中的完整消息
                self.process_buffer(sock)
            except ConnectionResetError:
                self.close_connection(sock)
        for sock in exceptional:
            self.close_connection(sock)

    def process_buffer(self, sock):
        buffer = self.recv_buffers[sock]
        while True:
            if len(buffer) < 4:
                break
            try:
                total_length = struct.unpack('>I', buffer[:4])[0]
            except struct.error as e:
                print(f"Error unpacking length prefix: {e}")
                buffer.pop(0)
                continue
            if len(buffer) < 4 + total_length:
                break
            message_bytes = buffer[:4 + total_length]
            buffer[:4 + total_length] = []
            try:
                data_structed, _ = SensorData.from_bytes(message_bytes)
                if data_structed is None:
                    print("Failed to parse SensorData from bytes")
                    continue
                if data_structed.data_type == DataType.TIME_REQUEST:
                    self.handle_time_request(sock, data_structed)
                else:
                    self.process_fragment(data_structed)
            except Exception as e:
                print(f"Error parsing message: {e}")
                continue

    def close_connection(self, sock):
        print(f"Closing connection to {sock.getpeername()}")
        self.client_sockets.remove(sock)
        del self.recv_buffers[sock]
        sock.close()

    def handle_time_request(self, sock, data_structed):
        source_time = data_structed.timestamp
        current_time = time.time()
        response = f"TIME_RESPONSE:{current_time:010.15f}:{source_time:010.15f}"
        response_bytes = response.encode()
        total_length = len(response_bytes)
        length_prefix = struct.pack('>I', total_length)
        response_message = length_prefix + response_bytes
        try:
            sock.sendall(response_message)
            print(f"Sent TIME_RESPONSE to {sock.getpeername()}: {current_time}")
        except BrokenPipeError:
            self.close_connection(sock)
            print(f"Error sending TIME_RESPONSE to {sock.getpeername()}")

    def process_fragment(self, fresh_data: SensorData):
        if fresh_data is None:
            return
        source_key = (fresh_data.source_id, fresh_data.data_type)
        source = self.sources_state.get(source_key)
        if source:
            fresh_data.timestamp = max(fresh_data.timestamp, time.time())
            if source.last_systime_received < fresh_data.timestamp:
                source.last_systime_received = fresh_data.timestamp
        else:
            print(f"Received data from unknown source ID: {fresh_data.source_id} {fresh_data.data_type}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start WiFiTCPFcfsDestination')
    parser.add_argument('--sources', nargs='+', help='List of source addresses in the format ip:port:type')
    parser.add_argument('--listen_port', type=int, default=9999, help='Port to listen on')
    parser.add_argument('--age_record_dir', default='./ages_wifresh_app', help='Directory to store age records')
    args = parser.parse_args()

    sources_addresses = []
    if args.sources:
        for src in args.sources:
            source_id_str, type_str = src.split(':')
            source_id = int(source_id_str)  # Convert to integer
            sources_addresses.append((source_id, DataType[type_str.upper()]))
            print(f"Added source {source_id} {DataType[type_str.upper()]}")
    else:
        print("No sources specified")
        print("Usage: python destination.py --sources <source_id:type> <source_id:type> ...")
        exit(1)

    destination = WiFiTCPFcfsDestination(
        sources_addresses=sources_addresses,
        listen_port=args.listen_port,
        age_record_dir=args.age_record_dir
    )
    destination.start()