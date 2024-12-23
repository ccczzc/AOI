# WiFresh APP Reproduction Code Overview

## Introduction
This repository aims to reproduce the core experiments and technical points of the WiFresh paper, implementing and testing various Age of Information (AoI) transmission strategies over wireless networks.

## Reference Paper
[I. Kadota, M. S. Rahman and E. Modiano, "WiFresh: Age-of-Information from Theory to Implementation," 2021 International Conference on Computer Communications and Networks (ICCCN), Athens, Greece, 2021, pp. 1-11, doi: 10.1109/ICCCN52240.2021.9522228.](https://ieeexplore.ieee.org/document/9522228)

## Directory Structure
- `wifi_udp_fcfs_source.py` and `wifi_udp_fcfs_destination.py`: FCFS (First Come, First Served) transmission examples based on UDP  
- `wifi_tcp_fcfs_source.py` and `wifi_tcp_fcfs_destination.py`: FCFS transmission examples based on TCP  
- `wifresh_app_source.py` and `wifresh_app_destination.py`: WiFresh APP tests  
- `wifresh_maf_source.py` and `wifresh_maf_destination.py`: WiFresh MAF (Maximum Age First) strategy tests  
- `AgeControlProtocolPlus`: C++ implementation related to ACP+; refer to research ([T. Shreedhar, S. K. Kaul and R. D. Yates, "ACP+: An Age Control Protocol for the Internet," in IEEE/ACM Transactions on Networking, vol. 32, no. 4, pp. 3253-3268, Aug. 2024, doi: 10.1109/TNET.2024.3380622.](https://ieeexplore.ieee.org/document/10483026)) and the open-source repository [GitHub](https://github.com/tanyashreedhar/AgeControlProtocolPlus)
- `sensor.py` and `SensorData`: Sensor data classes and data generation sensors

## Environment
- Linux OS  
- Python 3.8+  
- C++ (if compiling ACP+-related source files)

## Experimental Network Topology Environment
- Wireless network simulation tool mininet-wifi, open-source repository [GitHub](https://github.com/intrig-unicamp/mininet-wifi)

## Quick Start
1. Clone or download this repository  
2. Go to the corresponding subdirectory and install or check dependencies  
3. Compile or run the corresponding scripts:  
  - Wifresh APP example:  
      on the source node(IP: 10.0.0.2):
      ```bash
      python3 wifresh_app_source.py --listen_port 8080 --destination 10.0.0.1:9999 --sensors POSITION:50:1 INERTIAL_MEASUREMENT:20:100
      ```  
      on the destination node(IP: 10.0.0.1):  
      ```bash
      python3 wifresh_app_destination.py --age_record_dir ./ages2/ages_wifresh_app_1src --sources 10.0.0.2:8080:POSITION 10.0.0.2:8080:INERTIAL_MEASUREMENT
      ```
   - ACP+ example:  
      on the source node(IP: 10.0.0.2):  
      ```bash
      ./client_acp 10.0.0.1 50 1 2 2 49050 8080
      ```
      on the destination node(IP: 10.0.0.1):  
      ```bash
      ./server
      ```
    

## One-Click Network Topology and Experiment
```bash
sudo python3 multi_source_topo.py [source_num]
```