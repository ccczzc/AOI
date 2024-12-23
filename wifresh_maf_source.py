import argparse
from collections import defaultdict
import random
import socket
import time
from typing import List
from sensor import Sensor, SensorData, DataType
import sys
import select

class WiFreshMAFSource:
    def __init__(
        self, 
        listen_port, 
        destination_address,
        sensor_list: List[Sensor],
        sync_interval=5,
        sync_rounds=5,
        clock_offset_alpha=0.02
    ):
        self.listen_port = listen_port
        self.destination_address = destination_address
        self.max_packet_size = self.get_max_packet_size() - SensorData.header_size  # Max packet size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.sensors: dict[DataType, Sensor] = defaultdict(Sensor)
        for sensor in sensor_list:
            self.sensors[sensor.data_type] = sensor
        self.clock_offset = 0.0  # Clock offset between source and destination
        self.sync_interval = sync_interval  # Clock synchronization interval in seconds
        self.last_sync_time = time.time() - random.uniform(0, self.sync_interval)  # Randomize initial sync time
        self.sync_rounds = sync_rounds  # Number of synchronization messages per sync
        self.clock_offset_alpha = clock_offset_alpha  # Smoothing factor for clock offset adjustment (0 < alpha <= 1)

    def get_max_packet_size(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_packet_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        sock.close()
        # max_packet_size = 1472
        print(f"Max packet size: {max_packet_size}")
        return max_packet_size

    def start(self):
        print(f"WiFresh MAF source started on port {self.listen_port}")
        self.sock.setblocking(False)
        start_transmission = False
        while True:
            # Check if it's time to synchronize clocks
            if time.time() - self.last_sync_time >= self.sync_interval:
                self.clock_synchronization()
                self.last_sync_time = time.time()

            # Handle incoming messages
            readable, _, _ = select.select([self.sock], [], [], 0)
            if readable:
                data, addr = self.sock.recvfrom(1024)
                data_str = data.decode()
                if data_str.startswith('POLL'):
                    parts = data_str.split(':')
                    if len(parts) == 2:
                        sensor_type = DataType(int(parts[1]))
                        if not start_transmission:
                            start_transmission = True
                        self.process_poll(sensor_type)
                elif data_str.startswith('TIME_RESPONSE'):
                    # Handle time synchronization response
                    parts = data_str.split(':')
                    if len(parts) == 3:
                        dest_time = float(parts[1])
                        t1 = float(parts[2])
                        t2 = time.time()
                        offset = dest_time - ((t1 + t2) / 2)
                        # Update clock offset using exponential moving average
                        self.clock_offset = self.clock_offset_alpha * offset + (1 - self.clock_offset_alpha) * self.clock_offset
                        # print(f"Updated clock offset: {self.clock_offset} seconds")
                else:
                    print(f"Received unknown message from {addr}: {data_str}")
            if start_transmission:
                for sensor in self.sensors.values():
                    sensor.generate_data()

    def process_poll(self, sensor_type):
        if sensor_type not in self.sensors:
            print(f"Unknown sensor type: {sensor_type}")
            return
        sensor = self.sensors[sensor_type]
        if sensor.fragment_data_queue:
            fragment = sensor.fragment_data_queue.pop(0)  # Get next fragment from FCFS queue
            self.send_packet(fragment)
        elif sensor.complete_data_queue:
            info_update = sensor.complete_data_queue.pop()  # Get update from LCFS queue
            sensor.complete_data_queue.clear()  # Clear LCFS queue
            # Adjust timestamp with clock offset
            info_update.timestamp += self.clock_offset
            if len(info_update.data) <= self.max_packet_size:
                self.send_packet(info_update)
            else:
                all_data = info_update.data
                fragments = [
                    all_data[i:i + self.max_packet_size]
                    for i in range(0, len(all_data), self.max_packet_size)
                ]
                for idx, fragment in enumerate(fragments):
                    is_fragmented = ((idx + 1) != len(fragments))
                    fragment_data = SensorData(
                        is_fragmented=is_fragmented,
                        data_type=info_update.data_type,
                        timestamp=info_update.timestamp,
                        data=fragment
                    )
                    sensor.fragment_data_queue.append(fragment_data)  # Add to FCFS queue
                self.send_packet(sensor.fragment_data_queue.pop(0))  # Send first fragment
        else:
            # Send empty packet with adjusted timestamp
            empty_packet = SensorData(is_fragmented=0, data_type=sensor_type, timestamp=time.time() + self.clock_offset, data=b'')
            self.send_packet(empty_packet)

    def send_packet(self, packet: SensorData):
        bytes_sent = self.sock.sendto(packet.to_bytes(), self.destination_address)
        # print(f"Sent {bytes_sent} bytes to {self.destination_address}")

    def clock_synchronization(self):
        for _ in range(self.sync_rounds):
            # Send TIME_REQUEST to destination
            current_time = time.time()
            request = SensorData(is_fragmented=0, data_type=DataType.TIME_REQUEST, timestamp=current_time, data=b'')

            self.sock.sendto(request.to_bytes(), self.destination_address)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start WiFreshSource')
    parser.add_argument('--listen_port', type=int, required=True, help='Port to listen on')
    parser.add_argument('--destination', required=True, help='Destination address in the format ip:port')
    parser.add_argument('--sensors', nargs='+', required=True, help='Sensor configurations in the format type:size:frequency')
    args = parser.parse_args()

    dest_ip, dest_port = args.destination.split(':')
    destination_address = (dest_ip, int(dest_port))

    # Parse sensor configurations
    sensor_list = []
    for sensor_arg in args.sensors:
        sensor_type_str, size_str, frequency_str = sensor_arg.split(':')
        sensor_type = DataType[sensor_type_str.upper()]
        size = int(size_str)
        frequency = float(frequency_str)
        sensor_list.append(Sensor(sensor_type, size, frequency))
        print(f"Added sensor: {sensor_type} - packet size: {size} - frequency: {frequency}")

    source = WiFreshMAFSource(
        listen_port=args.listen_port,
        destination_address=destination_address,
        sensor_list=sensor_list
    )
    source.start()