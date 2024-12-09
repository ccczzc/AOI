import argparse
from io import TextIOWrapper
import os
import select
import socket
import time
from typing import List, Tuple
from sensor import SensorData

class SourceState:
    def __init__(self, output_fd: TextIOWrapper):
        self.weight: float = 0
        self.last_systime_received: float = time.time()
        self.approximate_systime_HOL: float = 0
        self.fragments: list[str] = []
        self.time_poll_packets: list[float] = []
        self.time_received_packets: list[float] = []
        self.time_period: str = 0.5
        self.output_fd = output_fd

class WiFreshDestination:
    def __init__(self, sources_addresses: List[Tuple[str, int]], listen_port=9999, age_record_dir='./ages_multisource_wifi'):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.sources_state: dict[Tuple[str, int], SourceState] = {}
        os.makedirs(age_record_dir, exist_ok=True)
        for source_address in sources_addresses:
            source_file_path = os.path.join(age_record_dir, f"{source_address[0]}_{source_address[1]}.txt")
            with open(source_file_path, 'w'):
                pass
            self.sources_state[source_address] = SourceState(output_fd=open(source_file_path, 'a'))
        self.age_record_interval = 1e-5  # Age record interval
        self.last_age_record_time = time.time() - self.age_record_interval

    def start(self):
        print("WiFresh destination_wifi started")
        self.run()

    def run(self):
        self.sock.setblocking(False)
        while True:
            self.receive_response()
            if time.time() - self.last_age_record_time >= self.age_record_interval:
                self.record_age()
                
    def record_age(self):
        for source in self.sources_state.values():
            current_time = time.time()
            source.output_fd.write(f"{current_time: .8f}, {current_time - source.last_systime_received: .7f}\n")
        self.last_age_record_time = time.time()

    def receive_response(self):
        readable, _, _ = select.select([self.sock], [], [], 0)
        if readable:
            data, addr = self.sock.recvfrom(4096)
            if addr not in self.sources_state:
                print(f"Received data from unknown source {addr}: {data.decode()}")
                exit(1)
            data_str = data.decode()
            # print(f"Received data from {addr}: {data_str}")
            if data_str.startswith('TIME_REQUEST'):
                parts = data_str.split(':')
                if len(parts) == 2:
                    source_time = float(parts[1])
                    # Handle time synchronization request
                    current_time = time.time()
                    response = f"TIME_RESPONSE:{current_time:010.15f}:{source_time:010.15f}"
                    self.sock.sendto(response.encode(), addr)
                    print(f"Sent TIME_RESPONSE to {addr}: {current_time}")
            else:
                self.process_fragment(data_str, addr)

    def process_fragment(self, fragment: str, source_addr):
        fresh_fragment = SensorData.from_str(fragment)
        source = self.sources_state[source_addr]
        # Adjust the timestamp
        fragment_timestamp = fresh_fragment.timestamp
        # Update last_systime_received
        if source.last_systime_received < fragment_timestamp < time.time():
            source.last_systime_received = fragment_timestamp

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start WiFreshDestination')
    parser.add_argument('--sources', nargs='+', help='List of source addresses in the format ip:port')
    args = parser.parse_args()

    sources_addresses = []
    if args.sources:
        for src in args.sources:
            ip, port = src.split(':')
            sources_addresses.append((ip, int(port)))
    else:
        print("No sources specified")
        print("Usage: python destination.py --sources <ip:port> <ip:port> ...")
        exit(1)

    destination = WiFreshDestination(sources_addresses=sources_addresses)
    destination.start()