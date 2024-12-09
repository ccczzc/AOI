import socket
import time
from sensor import Sensor, SensorData
import sys
import select

class WiFreshSource:
    def __init__(self, listen_port, destination_address):
        self.listen_port = listen_port
        self.destination_address = destination_address
        self.lcfs_queue: list[SensorData] = []  # LCFS queue
        self.fcfs_queue: list[SensorData] = []  # FCFS fragment queue
        self.sensor = Sensor(listen_port)  # Sensor instance
        self.packet_header_size = 20  # Packet header size
        self.max_packet_size = self.get_max_packet_size() - self.packet_header_size  # Max packet size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.generation_rate = 7000  # Generation rate
        self.clock_offset = 0.0  # Clock offset between source and destination
        self.sync_interval = 5  # Clock synchronization interval in seconds
        self.last_sync_time = time.time()
        self.sync_rounds = 5  # Number of synchronization messages per sync
        self.alpha = 0.02  # Smoothing factor for clock offset adjustment (0 < alpha <= 1)

    def get_max_packet_size(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_packet_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        sock.close()
        print(f"Max packet size: {max_packet_size}")
        return max_packet_size

    def start(self):
        print(f"WiFresh source started on port {self.listen_port}")
        self.run()

    def run(self):
        self.sock.setblocking(False)
        start_transmission = False
        last_generation_time = time.time()
        generation_interval = 1.0 / self.generation_rate
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
                    if not start_transmission:
                        start_transmission = True
                    self.process_poll()
                elif data_str.startswith('TIME_RESPONSE'):
                    # Handle time synchronization response
                    parts = data_str.split(':')
                    if len(parts) == 3:
                        dest_time = float(parts[1])
                        t1 = float(parts[2])
                        t2 = time.time()
                        offset = dest_time - ((t1 + t2) / 2)
                        # Update clock offset using exponential moving average
                        self.clock_offset = self.alpha * offset + (1 - self.alpha) * self.clock_offset
                        print(f"Updated clock offset: {self.clock_offset} seconds")
                else:
                    print(f"Received unknown message from {addr}: {data_str}")
            if start_transmission:
                now = time.time()
                if now - last_generation_time >= generation_interval:
                    # Generate sensor data
                    info_update = self.sensor.generate_data()
                    # Adjust timestamp with clock offset
                    info_update.timestamp += self.clock_offset
                    self.lcfs_queue.append(info_update)
                    last_generation_time = now

    def process_poll(self):
        if self.fcfs_queue:
            fragment = self.fcfs_queue.pop(0)  # Get next fragment from FCFS queue
            self.send_packet(fragment)
        elif self.lcfs_queue:
            info_update = self.lcfs_queue.pop()  # Get update from LCFS queue
            # Adjust timestamp with clock offset
            if len(info_update.data) <= self.max_packet_size:
                self.send_packet(info_update)
            else:
                all_data = info_update.data
                fragments = [
                    all_data[i:i + self.max_packet_size]
                    for i in range(0, len(all_data), self.max_packet_size)
                ]
                for idx, fragment in enumerate(fragments):
                    is_fragmented = idx + 1 != len(fragments)
                    fragment_data = SensorData(
                        is_fragmented=is_fragmented,
                        timestamp=info_update.timestamp,
                        data=fragment
                    )
                    self.fcfs_queue.append(fragment_data)  # Add to FCFS queue
                self.send_packet(self.fcfs_queue.pop(0))  # Send first fragment
        else:
            # Send empty packet with adjusted timestamp
            empty_packet = SensorData(is_fragmented=0, timestamp=time.time() + self.clock_offset, data='')
            self.send_packet(empty_packet)

    def send_packet(self, packet: SensorData):
        bytes_sent = self.sock.sendto(packet.to_str().encode(), self.destination_address)
        # print(f"Sent {bytes_sent} bytes to {self.destination_address}")

    def clock_synchronization(self):
        for _ in range(self.sync_rounds):
            # Send TIME_REQUEST to destination
            current_time = time.time()
            request = f"TIME_REQUEST:{current_time:010.15f}"
            self.sock.sendto(request.encode(), self.destination_address)

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python source.py <listen_port> <destination_host> <destination_port>")
        sys.exit(1)

    listen_port = int(sys.argv[1])
    destination_host = sys.argv[2]
    destination_port = int(sys.argv[3])
    destination_address = (destination_host, destination_port)
    source = WiFreshSource(listen_port, destination_address)
    source.start()