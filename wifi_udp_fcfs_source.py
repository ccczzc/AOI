import argparse
from collections import defaultdict
import select
import socket
import time
from typing import List
from sensor import Sensor, SensorData, DataType

class WiFiUDPFcfsSource:
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
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.sensor_list = sensor_list
        self.clock_offset = 0.0  # Clock offset
        self.sync_interval = sync_interval  # Clock synchronization interval (seconds)
        self.last_sync_time = time.time()
        self.sync_rounds = sync_rounds  # Number of messages per synchronization
        self.clock_offset_alpha = clock_offset_alpha  # Smoothing factor for clock offset adjustment (0 < alpha <= 1)

    def start(self):
        print(f"WiFi UDP FCFS source started on port {self.listen_port}")
        self.sock.setblocking(False)
        while True:
            # Handle received messages
            self.receive_response()
            # Check if clock synchronization is needed
            if time.time() - self.last_sync_time >= self.sync_interval:
                self.clock_synchronization()

            for sensor in self.sensor_list:
                # Try generate sensor data
                sensor.generate_data()
                if sensor.complete_data_queue:
                    # Adjust timestamp using clock offset
                    oldest_data = sensor.complete_data_queue[0]
                    oldest_data.timestamp += self.clock_offset
                    try:
                        self.send_packet(oldest_data)
                        sensor.complete_data_queue.pop(0)
                    except BlockingIOError:
                        print("source run send_packet BlockingIOError")
                        oldest_data.timestamp -= self.clock_offset

    def receive_response(self):
            readable, _, _ = select.select([self.sock], [], [], 0)
            if readable:
                data, addr = self.sock.recvfrom(1024)
                data_str = data.decode()
                if data_str.startswith('TIME_RESPONSE'):
                    # Handle clock synchronization response
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

    def send_packet(self, packet: SensorData):
        bytes_sent = self.sock.sendto(packet.to_bytes(), self.destination_address)
        # print(f"Sent {bytes_sent} bytes to {self.destination_address}")

    def clock_synchronization(self):
        for _ in range(self.sync_rounds):
            # Send TIME_REQUEST to the destination
            try:
                current_time = time.time()
                request = SensorData(is_fragmented=0, data_type=DataType.TIME_REQUEST, timestamp=current_time, data=b'')
                self.sock.sendto(request.to_bytes(), self.destination_address)
            except BlockingIOError:
                print("source clock_synchronization sendto BlockingIOError")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start Source')
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

    source = WiFiUDPFcfsSource(
        listen_port=args.listen_port,
        destination_address=destination_address,
        sensor_list=sensor_list
    )
    source.start()