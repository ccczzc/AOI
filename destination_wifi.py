from io import TextIOWrapper
import os
import socket
import threading
import time
from typing import List, Tuple
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

class WiFreshDestination:
    def __init__(self, sources_addresses: List[Tuple[str, int]], listen_port=9999, age_record_dir='./ages_wifi'):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.sources_state: dict[Tuple[str, int], SourceState] = {}
        os.makedirs(age_record_dir, exist_ok=True)
        for source_address in sources_addresses:
            source_file_path = os.path.join(age_record_dir, f"{source_address[0]}:{source_address[1]}.txt")
            with open(source_file_path, 'w'):
                pass
            self.sources_state[source_address] = SourceState(output_fd=open(source_file_path, 'a'))
        self.lock: threading.Lock = threading.Lock()  # 定义锁

    def start(self):
        threading.Thread(target=self.receive_response, daemon=True).start()
        print("WiFresh destination started")
        self.record_age()

    def record_age(self):
        while True:
            current_time = time.time()
            with self.lock:
                for source in self.sources_state.values():
                    source.output_fd.write(f"{current_time: .8f}, {current_time - source.last_systime_received: .7f}\n")
            time.sleep(1e-6)

    def receive_response(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            print(f"Received data from {addr}: {data.decode()}")
            source_id = addr
            self.process_fragment(data.decode(), source_id)

    def process_fragment(self, fragment: str, source_id):
        fresh_fragment = SensorData.from_str(fragment)
        print(f"Received fragment from source {source_id}: {fresh_fragment}")
        with self.lock:
            source = self.sources_state[source_id]
            source.fragments.append(fresh_fragment.data)
            if source.last_systime_received < fresh_fragment.timestamp:
                    source.last_systime_received = fresh_fragment.timestamp

if __name__ == '__main__':
    sources_addresses = [('10.0.0.2', 8000)]
    destination = WiFreshDestination(sources_addresses=sources_addresses)
    destination.start()