import argparse
import socket
import time
import struct
from typing import List
from sensor_for_tcp import Sensor, SensorData, DataType

class WiFiTCPFcfsSource:
    def __init__(
        self, 
        listen_port, 
        destination_address,
        source_id,          # For identifying the source
        sensor_list: List[Sensor],
        sync_interval=5,
        sync_rounds=5,
        clock_offset_alpha=0.02
    ):
        self.listen_port = listen_port
        self.destination_address = destination_address
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.sensor_list = sensor_list
        self.clock_offset = 0.0
        self.sync_interval = sync_interval
        self.last_sync_time = time.time()
        self.sync_rounds = sync_rounds
        self.clock_offset_alpha = clock_offset_alpha
        self.connected = False
        self.recv_buffer = bytearray()
        self.source_id = source_id  # New field

    def connect_to_destination(self):
        while not self.connected:
            try:
                self.sock.connect(self.destination_address)
                self.connected = True
                self.sock.setblocking(False)
                print(f"Connected to destination {self.destination_address} from port {self.listen_port}")
            except ConnectionRefusedError:
                print("Connection refused, retrying...")
                time.sleep(1)
            except OSError as e:
                print(f"Socket error: {e}")
                time.sleep(1)

    def start(self):
        self.connect_to_destination()
        print(f"WiFi TCP FCFS source started on port {self.listen_port}")
        while True:
            self.receive_response()
            if time.time() - self.last_sync_time >= self.sync_interval:
                self.clock_synchronization()
            for sensor in self.sensor_list:
                sensor.generate_data()
                if sensor.complete_data_queue:
                    oldest_data = sensor.complete_data_queue[0]
                    oldest_data.timestamp += self.clock_offset
                    try:
                        self.send_packet(oldest_data)
                        sensor.complete_data_queue.pop(0)
                    except BlockingIOError:
                        # print("BlockingIOError while sending data")
                        oldest_data.timestamp -= self.clock_offset

    def receive_response(self):
        try:
            data = self.sock.recv(4096)
            if data:
                # Add received data to the buffer
                self.recv_buffer.extend(data)
                # Process complete messages in the buffer
                self.process_buffer()
            else:
                print("Received empty data, reconnecting...")
                self.connected = False
                self.connect_to_destination()
        except BlockingIOError:
            pass
        except ConnectionResetError:
            print("Connection reset by peer, reconnecting...")
            self.connected = False
            self.connect_to_destination()

    def process_buffer(self):
        while True:
            if len(self.recv_buffer) < 4:
                # Not enough data to read the length prefix
                break
            total_length = struct.unpack('>I', self.recv_buffer[:4])[0]
            if len(self.recv_buffer) < 4 + total_length:
                # Data not fully received
                break
            # Extract the complete message
            message_bytes = self.recv_buffer[:4 + total_length]
            # Update the buffer, removing the processed message
            self.recv_buffer = self.recv_buffer[4 + total_length:]
            # Process the message
            data_str = message_bytes[4:].decode()
            self.process_time_response(data_str)

    def process_time_response(self, data_str):
        if data_str.startswith('TIME_RESPONSE'):
            parts = data_str.split(':')
            if len(parts) == 3:
                dest_time = float(parts[1])
                t1 = float(parts[2])
                t2 = time.time()
                offset = dest_time - ((t1 + t2) / 2)
                self.clock_offset = self.clock_offset_alpha * offset + (1 - self.clock_offset_alpha) * self.clock_offset
                print(f"Updated clock offset: {self.clock_offset} seconds")
            else:
                print(f"Malformed TIME_RESPONSE message: {data_str}")
        else:
            print(f"Received unknown message: {data_str}")

    def send_packet(self, packet: SensorData):
        packet.source_id = self.source_id  # Set the source_id
        self.sock.sendall(packet.to_bytes())

    def clock_synchronization(self):
        for _ in range(self.sync_rounds):
            try:
                current_time = time.time()
                request = SensorData(
                    is_fragmented=0,
                    data_type=DataType.TIME_REQUEST,
                    timestamp=current_time,
                    source_id=self.source_id,
                    data=b''
                )
                self.sock.sendall(request.to_bytes())
            except BlockingIOError:
                # print("BlockingIOError during clock synchronization")
                pass
        self.last_sync_time = time.time()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start WiFiTCPFcfsSource')
    parser.add_argument('--listen_port', type=int, required=True, help='Port to listen on')
    parser.add_argument('--destination', required=True, help='Destination address in the format ip:port')
    parser.add_argument('--sensors', nargs='+', required=True, help='Sensor configurations in the format type:size:frequency')
    parser.add_argument('--source_id', type=int, required=True, help='Source ID')
    args = parser.parse_args()

    dest_ip, dest_port = args.destination.split(':')
    destination_address = (dest_ip, int(dest_port))
    source_id = args.source_id
    sensor_list = []
    for sensor_arg in args.sensors:
        sensor_type_str, size_str, frequency_str = sensor_arg.split(':')
        sensor_type = DataType[sensor_type_str.upper()]
        size = int(size_str)
        frequency = float(frequency_str)
        sensor_list.append(Sensor(sensor_type, size, frequency, source_id))
        print(f"Added sensor: {sensor_type} - packet size: {size} - frequency: {frequency}")

    source = WiFiTCPFcfsSource(
        listen_port=args.listen_port,
        destination_address=destination_address,
        source_id=source_id,
        sensor_list=sensor_list
    )
    source.start()