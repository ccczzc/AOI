from collections import defaultdict
import socket
import time
from typing import List
from sensor import Sensor, SensorData, DataType
import sys
import select

class WiFreshSource:
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
        self.packet_header_size = 20  # Packet header size
        self.max_packet_size = self.get_max_packet_size() - self.packet_header_size  # Max packet size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.sensors: dict[DataType, Sensor] = defaultdict(Sensor)
        for sensor in sensor_list:
            self.sensors[sensor.data_type] = sensor
        self.clock_offset = 0.0  # Clock offset between source and destination
        self.sync_interval = sync_interval  # Clock synchronization interval in seconds
        self.last_sync_time = time.time()
        self.sync_rounds = sync_rounds  # Number of synchronization messages per sync
        self.clock_offset_alpha = clock_offset_alpha  # Smoothing factor for clock offset adjustment (0 < alpha <= 1)

    def get_max_packet_size(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_packet_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        sock.close()
        print(f"Max packet size: {max_packet_size}")
        return max_packet_size

    def start(self):
        print(f"WiFresh APP source started on port {self.listen_port}")
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
                        print(f"Updated clock offset: {self.clock_offset} seconds")
                else:
                    print(f"Received unknown message from {addr}: {data_str}")
            # if start_transmission:
            for sensor in self.sensors.values():
                sensor.generate_data()

    def process_poll(self, sensor_type):
        if sensor_type not in self.sensors:
            print(f"Unknown sensor type: {sensor_type}")
            return
        sensor = self.sensors[sensor_type]
        if sensor.fcfs_queue:
            fragment = sensor.fcfs_queue.pop(0)  # Get next fragment from FCFS queue
            self.send_packet(fragment)
        elif sensor.lcfs_queue:
            info_update = sensor.lcfs_queue.pop()  # Get update from LCFS queue
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
                    sensor.fcfs_queue.append(fragment_data)  # Add to FCFS queue
                self.send_packet(sensor.fcfs_queue.pop(0))  # Send first fragment
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
    if len(sys.argv) != 4:
        print("Usage: python source.py <listen_port> <destination_host> <destination_port>")
        sys.exit(1)

    listen_port = int(sys.argv[1])
    destination_host = sys.argv[2]
    destination_port = int(sys.argv[3])
    destination_address = (destination_host, destination_port)
    source = WiFreshSource(
        listen_port=listen_port, 
        destination_address = destination_address,
        sensor_list=[
            Sensor(DataType.GENERAL, 150, 7000),
        ]
    )
    source.start()