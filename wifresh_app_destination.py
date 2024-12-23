import argparse
from io import TextIOWrapper
import os
import select
import socket
import time
from typing import Dict, List, Tuple
from collections import defaultdict
from sensor import SensorData, DataType
import bisect

class SourceState:
    def __init__(self, output_fd: TextIOWrapper = None):
        self.weight: float = 0
        self.last_systime_received: float = time.time()
        self.approximate_systime_HOL: float = 0
        self.fragments: bytes = b''
        self.time_poll_packets: list[float] = []
        self.time_received_packets: list[float] = []
        self.time_period: str = 0.5
        self.output_fd = output_fd
        self.last_recorded_age = 0.0
        self.total_weighted_ages: float = 0.0
        self.last_received_time: float = time.time()

    def update_weight(self):
        now_timestamp = time.time()
        
        # Define expiration time
        expired_time = now_timestamp - self.time_period
        
        # Update time_poll_packets queue
        index = bisect.bisect_right(self.time_poll_packets, expired_time)
        self.time_poll_packets = self.time_poll_packets[index:]
        
        # Update time_received_packets queue
        index = bisect.bisect_right(self.time_received_packets, expired_time)
        self.time_received_packets = self.time_received_packets[index:]
        
        p = (len(self.time_received_packets) + 1) / (len(self.time_poll_packets) + 1)
        potential_age_reduction = now_timestamp - self.last_systime_received - self.approximate_systime_HOL
        self.weight = p * potential_age_reduction * potential_age_reduction

    def reset_fragments(self):
        self.fragments = b''

class WiFreshDestination:
    def __init__(
        self, 
        sources_addresses: List[Tuple[str, int, DataType]], 
        listen_port=9999, 
        age_record_dir='./ages_wifresh_app',
        poll_interval=0.3,
        age_record_interval=1e-4
    ):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.poll_interval = poll_interval  # Polling interval
        self.age_record_interval = age_record_interval  # Age record interval
        self.sources_state: dict[Tuple[str, int, DataType], SourceState] = defaultdict(SourceState)
        self.age_record_dir = age_record_dir
        os.makedirs(age_record_dir, exist_ok=True)
        for source_address in sources_addresses:
            # source_file_path = os.path.join(age_record_dir, f"{source_address[0]}_{source_address[1]}_{source_address[2]}.txt")
            # with open(source_file_path, 'w'):
            #     # Open file in write mode to clear contents
            #     pass
            self.sources_state[source_address] = SourceState()
        self.last_poll_time = time.time() - self.poll_interval  # Last poll time
        self.last_age_record_time = time.time() - self.age_record_interval
        self.start_time = time.time()
        self.running_period = 600.0  # 10 minutes in seconds

    def start(self):
        print("WiFresh APP destination started")
        self.sock.setblocking(False)
        while True:
            self.receive_response()
            if time.time() - self.last_poll_time >= self.poll_interval:
                self.schedule_poll()
            # if time.time() - self.last_age_record_time >= self.age_record_interval:
            #     self.record_age()
            if time.time() - self.start_time >= self.running_period:
                self.save_ages()
                print("WiFresh APP destination stopped")
                break

    def save_ages(self):
        record_file_path = os.path.join(self.age_record_dir, f"ages_{len(self.sources_state)}sources.txt")
        with open(record_file_path, 'w') as record_file:
            mean_ages = []
            for source_address, source in self.sources_state.items():
                last_age_area =  (source.last_recorded_age + time.time() - source.last_systime_received) * (time.time() - source.last_received_time) / 2.0
                source.total_weighted_ages += last_age_area
                mean_age = source.total_weighted_ages / (time.time() - self.start_time)
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

    def schedule_poll(self):
        source_to_poll = self.select_source()
        if source_to_poll:
            self.send_poll(source_to_poll)

    def select_source(self):
        if not self.sources_state:
            return None
        max_weight, selected_source = None, None
        for source_tuple, source in self.sources_state.items():
            source.update_weight()
            if selected_source is None or source.weight > max_weight:
                max_weight = source.weight
                selected_source = source_tuple
        return selected_source

    def send_poll(self, source_tuple):
        ip, port, data_type = source_tuple
        self.sock.sendto(f"POLL:{data_type.value}".encode(), (ip, port))
        # print(f"Sent POLL to {source_tuple}")
        current_time = time.time()
        self.last_poll_time = current_time
        source = self.sources_state[source_tuple]
        source.time_poll_packets.append(current_time)

    def receive_response(self):
        readable, _, _ = select.select([self.sock], [], [], 0)
        if readable:
            data_bytes, addr = self.sock.recvfrom(4096*4096)
            # if addr not in self.sources_state:
            #     print(f"Received data from unknown source {addr}: {data_bytes.decode()}")
            #     exit(1)
            data_structed = SensorData.from_bytes(data_bytes)
            # print(f"Received data from {addr}: {data_structed}")
            if data_structed.data_type == DataType.TIME_REQUEST:
                source_time = data_structed.timestamp
                # Handle time synchronization request
                current_time = time.time()
                response = f"TIME_RESPONSE:{current_time:010.15f}:{source_time:010.15f}"
                self.sock.sendto(response.encode(), addr)
                # print(f"Sent TIME_RESPONSE to {addr}: {current_time}")
            else:
                # Assuming the type can be inferred from the data_structed
                source_type = data_structed.data_type
                addr_with_type = (addr[0], addr[1], source_type)
                self.process_fragment(data_structed, addr_with_type)

    def process_fragment(self, fresh_fragment: SensorData, source_addr):
        if fresh_fragment is None:
            return
        source = self.sources_state[source_addr]
        source.fragments += fresh_fragment.data
        if fresh_fragment.is_fragmented == 0:
            # complete_message = source.fragments
            source.reset_fragments()
            fresh_fragment.timestamp = max(fresh_fragment.timestamp, time.time())
            if source.last_systime_received < fresh_fragment.timestamp:
                time_received = time.time()
                # Record age
                age = time_received - source.last_systime_received
                age_area = (age + source.last_recorded_age) * (time_received - source.last_received_time) / 2
                source.total_weighted_ages += age_area
                source.last_received_time = time_received
                source.last_recorded_age = time_received - fresh_fragment.timestamp
                source.last_systime_received = fresh_fragment.timestamp
                source.time_received_packets.append(time_received)
                source.approximate_systime_HOL = time_received - source.last_systime_received
            # Schedule the next poll
            self.schedule_poll()

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

    destination = WiFreshDestination(
        sources_addresses=sources_addresses,
        listen_port=args.listen_port,
        age_record_dir=args.age_record_dir
    )
    destination.start()