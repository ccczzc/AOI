from io import TextIOWrapper
import os
import socket
import threading
import time
from typing import List, Tuple
from collections import defaultdict
from sensor import Sensor, SensorData

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
        # 删除超过时间周期的数据
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
    def __init__(self, sources_addresses: List[Tuple[str, int]], listen_port=9999, age_record_dir='./ages'):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.poll_interval = 0.3  # 轮询间隔
        self.sources_state: dict[Tuple[str, int], SourceState] = defaultdict(SourceState)
        os.makedirs(age_record_dir, exist_ok=True)
        for source_address in sources_addresses:
            source_file_path = os.path.join(age_record_dir, f"{source_address[0]}:{source_address[1]}.txt")
            with open(source_file_path, 'w'):
                # 以写模式打开文件以清空内容
                pass
            self.sources_state[source_address] = SourceState(output_fd=open(source_file_path, 'a'))
        self.last_poll_time = time.time() - self.poll_interval  # 上次轮询时间
        self.lock: threading.Lock = threading.Lock()  # 定义锁


    def start(self):
        threading.Thread(target=self.poll_sources, daemon=True).start()
        threading.Thread(target=self.receive_response, daemon=True).start()
        # threading.Thread(target=self.clock_synchronization, daemon=True).start()
        print("WiFresh destination started")
        self.record_age()

    def record_age(self):
        while True:
            current_time = time.time()
            with self.lock:
                for source in self.sources_state.values():
                    source.output_fd.write(f"{current_time: .8f}, {current_time - source.last_systime_received: .7f}\n")
            time.sleep(1e-6)
                

    def poll_sources(self):
        while True:
            with self.lock:
                passed_time = time.time() - self.last_poll_time
            if passed_time >= self.poll_interval:
                self.schedule_poll()
            else:
                time.sleep(self.poll_interval - passed_time)

    def schedule_poll(self):
        source_to_poll = self.select_source()
        if source_to_poll:
            self.send_poll(source_to_poll)

    def select_source(self):
        with self.lock:
            if not self.sources_state:
                return None
            for source in self.sources_state.values():
                source.update_weight()
            selected_source = max(self.sources_state, key=lambda k: self.sources_state[k].weight, default=None)
            return selected_source

    def send_poll(self, source_addr):
        self.sock.sendto(b'POLL', source_addr)
        current_time = time.time()
        with self.lock:
            self.last_poll_time = current_time
            source = self.sources_state[source_addr]
            source.time_poll_packets.append(current_time)
        print(f"Sent POLL to source {source_addr}")

    def receive_response(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            print(f"Received data from {addr}: {data.decode()}")
            source_id = addr
            if data.decode().startswith('TIME_RESPONSE'):
                self.process_time_response(data.decode(), source_id)
            else:
                self.process_fragment(data.decode(), source_id)

    def process_time_response(self, response, source_id):
        pass

    def process_fragment(self, fragment: str, source_id):
        fresh_fragment = SensorData.from_str(fragment)
        print(f"Received fragment from source {source_id}: {fresh_fragment}")
        with self.lock:
            source = self.sources_state[source_id]
            source.fragments.append(fresh_fragment.data)
            if fresh_fragment.is_fragmented == 0:
                complete_message = ''.join(source.fragments)
                source.reset_fragments()
                print(f"Received complete message from source {source_id}: {complete_message}")
                if source.last_systime_received < fresh_fragment.timestamp:
                    source.last_systime_received = fresh_fragment.timestamp
                time_received = time.time()
                source.time_received_packets.append(time_received)
                source.approximate_systime_HOL = time_received - source.last_systime_received
        self.schedule_poll()


    def clock_synchronization(self):
        # while True:
        #     for source_id in self.sources_state.keys():
        #         self.sock.sendto(b'TIME_SYNC', ('localhost', source_id))
        #     time.sleep(3600)  # 每小时同步一次
        pass

if __name__ == '__main__':
    sources_addresses=[('10.0.0.2', 8000)]
    destination = WiFreshDestination(sources_addresses=sources_addresses)
    destination.start()
    