import argparse
from collections import defaultdict
from io import TextIOWrapper
import os
import select
import socket
import time
from typing import List, Tuple
from sensor import DataType, SensorData

class SourceState:
    def __init__(self, output_fd: TextIOWrapper = None):
        self.weight: float = 0
        self.last_systime_received: float = time.time()
        self.output_fd = output_fd
        self.last_recorded_age = 0.0
        self.total_weighted_ages: float = 0.0

class WiFiUDPFcfsDestination:
    def __init__(
        self, 
        sources_addresses: List[Tuple[str, int, DataType]], 
        listen_port=9999, 
        age_record_dir='./ages_wifi_udp_fcfs',
        age_record_interval=1e-4
    ):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.sources_state: dict[Tuple[str, int, DataType], SourceState] = defaultdict(SourceState)
        self.age_record_dir = age_record_dir
        os.makedirs(age_record_dir, exist_ok=True)
        for source_address in sources_addresses:
            # source_file_path = os.path.join(age_record_dir, f"{source_address[0]}_{source_address[1]}.txt")
            # with open(source_file_path, 'w'):
            #     pass
            self.sources_state[source_address] = SourceState()
        self.age_record_interval = age_record_interval  # Age record interval
        self.last_age_record_time = time.time() - self.age_record_interval
        self.start_time = time.time()
        self.running_period = 600.0  # 10 minutes in seconds

    def start(self):
        print("WiFi UDP FCFS destination started")
        self.sock.setblocking(False)
        while True:
            self.receive_response()
            if time.time() - self.last_age_record_time >= self.age_record_interval:
                self.record_age()
            if time.time() - self.start_time >= self.running_period:
                self.save_ages()
                print("WiFi UDP FCFS destination stopped")
                break
            
    def save_ages(self):
        record_file_path = os.path.join(self.age_record_dir, f"ages_{len(self.sources_state)}sources.txt")
        with open(record_file_path, 'w') as record_file:
            mean_ages = []
            for source_address, source in self.sources_state.items():
                mean_age = source.total_weighted_ages / self.running_period
                record_file.write(f"{source_address[0]}_{source_address[1]}_{source_address[2]}: {mean_age}\n")
                mean_ages.append(mean_age)
            record_file.write(f"Mean AOI of all data sources: {sum(mean_ages) / len(mean_ages)}\n")
                    
    def record_age(self):
        for source in self.sources_state.values():
            current_time = time.time()
            age = current_time - source.last_systime_received
            age_area = (age + source.last_recorded_age) * (current_time - self.last_age_record_time) / 2
            source.total_weighted_ages += age_area
            source.last_recorded_age = age
        self.last_age_record_time = time.time()

    def receive_response(self):
        readable, _, _ = select.select([self.sock], [], [], 0)
        if readable:
            data_bytes, addr = self.sock.recvfrom(4096*4096)
            print(f"Received data from {addr}, size {len(data_bytes)}")
            data_structed = SensorData.from_bytes(data_bytes)
            # print(f"Received data from {addr}: {data_structed}")
            if data_structed.data_type == DataType.TIME_REQUEST:
                source_time = data_structed.timestamp
                # Handle time synchronization request
                current_time = time.time()
                response = f"TIME_RESPONSE:{current_time:010.15f}:{source_time:010.15f}"
                self.sock.sendto(response.encode(), addr)
                print(f"Sent TIME_RESPONSE to {addr}: {current_time}")
            else:
                # Assuming the type can be inferred from the data_structed
                source_type = data_structed.data_type
                addr_with_type = (addr[0], addr[1], source_type)
                self.process_fragment(data_structed, addr_with_type)
            

    def process_fragment(self, fresh_data: SensorData, source_addr):
        if fresh_data is None:
            return
        source = self.sources_state[source_addr]
        source = self.sources_state[source_addr]
        # Update last_systime_received
        fresh_data.timestamp = max(fresh_data.timestamp, time.time())
        if source.last_systime_received < fresh_data.timestamp:
            source.last_systime_received = fresh_data.timestamp

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start WiFreshDestination')
    parser.add_argument('--sources', nargs='+', help='List of source addresses in the format ip:port:type')
    parser.add_argument('--listen_port', type=int, default=9999, help='Port to listen on')
    parser.add_argument('--age_record_dir', default='./ages_wifresh_app', help='Directory to store age records')
    args = parser.parse_args()

    sources_addresses = []
    if args.sources:
        for src in args.sources:
            ip, port, type = src.split(':')
            sources_addresses.append((ip, int(port), DataType[type.upper()]))
    else:
        print("No sources specified")
        print("Usage: python destination.py --sources <ip:port:type> <ip:port:type> ...")
        exit(1)

    destination = WiFiUDPFcfsDestination(
        sources_addresses=sources_addresses,
        listen_port=args.listen_port,
        age_record_dir=args.age_record_dir
    )
    destination.start()