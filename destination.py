import argparse
from io import TextIOWrapper
import os
import select
import socket
import time
from typing import Dict, List, Tuple
from collections import defaultdict
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

    def update_weight(self):
        now_timestamp = time.time()
        # Remove outdated poll packets
        while self.time_poll_packets:
            time_poll = self.time_poll_packets[0]
            if now_timestamp - time_poll > self.time_period:
                self.time_poll_packets.pop(0)
            else:
                break
        while self.time_received_packets:
            time_received = self.time_received_packets[0]
            if now_timestamp - time_received > self.time_period:
                self.time_received_packets.pop(0)
            else:
                break
        p = (len(self.time_received_packets) + 1) / (len(self.time_poll_packets) + 1)
        potential_age_reduction = now_timestamp - self.last_systime_received - self.approximate_systime_HOL
        self.weight = p * potential_age_reduction * potential_age_reduction

    def reset_fragments(self):
        self.fragments = []

class WiFreshDestination:
    def __init__(self, sources_addresses: List[Tuple[str, int]], listen_port=9999, age_record_dir='./ages_multisource'):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.poll_interval = 0.3  # Polling interval
        self.age_record_interval = 1e-4  # Age record interval
        self.sources_state: dict[Tuple[str, int], SourceState] = defaultdict(SourceState)
        os.makedirs(age_record_dir, exist_ok=True)
        for source_address in sources_addresses:
            source_file_path = os.path.join(age_record_dir, f"{source_address[0]}_{source_address[1]}.txt")
            with open(source_file_path, 'w'):
                # Open file in write mode to clear contents
                pass
            self.sources_state[source_address] = SourceState(output_fd=open(source_file_path, 'a'))
        self.last_poll_time = time.time() - self.poll_interval  # Last poll time
        self.last_age_record_time = time.time() - self.age_record_interval

    def start(self):
        print("WiFresh destination started")
        self.run()

    def run(self):
        self.sock.setblocking(False)
        while True:
            self.receive_response()
            if time.time() - self.last_poll_time >= self.poll_interval:
                self.schedule_poll()
            if time.time() - self.last_age_record_time >= self.age_record_interval:
                self.record_age()

    def record_age(self):
        for source in self.sources_state.values():
            current_time = time.time()
            age = current_time - source.last_systime_received
            source.output_fd.write(f"{current_time:.8f}, {age:.7f}\n")
        self.last_age_record_time = time.time()

    def schedule_poll(self):
        source_to_poll = self.select_source()
        if source_to_poll:
            self.send_poll(source_to_poll)

    def select_source(self):
        if not self.sources_state:
            return None
        for source in self.sources_state.values():
            source.update_weight()
        selected_source = max(self.sources_state, key=lambda k: self.sources_state[k].weight, default=None)
        return selected_source

    def send_poll(self, source_addr):
        self.sock.sendto(b'POLL', source_addr)
        print(f"Sent POLL to {source_addr}")
        current_time = time.time()
        self.last_poll_time = current_time
        source = self.sources_state[source_addr]
        source.time_poll_packets.append(current_time)

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
        if fresh_fragment is None:
            return
        source = self.sources_state[source_addr]
        source.fragments.append(fresh_fragment.data)
        if fresh_fragment.is_fragmented == 0:
            complete_message = ''.join(source.fragments)
            source.reset_fragments()
            if source.last_systime_received < fresh_fragment.timestamp:
                source.last_systime_received = fresh_fragment.timestamp
                time_received = time.time()
                source.time_received_packets.append(time_received)
                source.approximate_systime_HOL = time_received - source.last_systime_received
            # Schedule the next poll
            self.schedule_poll()

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