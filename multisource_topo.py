#!/usr/bin/python

from time import sleep
from mininet.node import Controller,  Host
from mininet.log import setLogLevel, info
from mininet.term import makeTerm
from mininet.link import TCLink
from mn_wifi.net import Mininet_wifi
from mn_wifi.node import Station, OVSKernelAP
from mn_wifi.cli import CLI
from mn_wifi.link import wmediumd
from mn_wifi.wmediumdConnector import interference
from subprocess import call
import random
import math

def myNetwork(num_sources=10):

    net = Mininet_wifi(link=wmediumd,
                       wmediumd_mode=interference,
                       noise_th=-91, fading_cof=3,
                       ipBase='10.0.0.0/8')

    info( '*** Adding controller\n' )
    c0 = net.addController(name='c0',
                           controller=Controller,
                           protocol='tcp',
                           port=6653)

    info( '*** Add switches/APs\n')
    ap1_x, ap1_y = 50.0, 50.0
    ap1 = net.addAccessPoint('ap1', ssid='ap1-ssid', mode='g', channel='1',
                              position=f'{ap1_x},{ap1_y},0')

    info( '*** Add hosts/stations\n')
    destination = net.addHost('dst', cls=Host, ip='10.0.0.1', defaultRoute=None)
    sources = []
    for i in range(num_sources):
        # 随机生成距离和角度
        r = random.uniform(2, 3)
        theta = random.uniform(0, 2 * math.pi)
        # 计算 source 的位置
        x = ap1_x + r * math.cos(theta)
        y = ap1_y + r * math.sin(theta)
        source = net.addStation(f'src{i + 1}', ip=f'10.0.0.{i+2}',
                             position=f'{x},{y},0')
        sources.append(source)

    info("*** Configuring Propagation Model\n")
    net.setPropagationModel(model="logDistance", exp=4.5)

    info("*** Configuring wifi nodes\n")
    net.configureWifiNodes()

    info( '*** Add links\n')
    for source in sources:
        net.addLink(source, ap1)
    ap1dst = {} #{'bw':10,'delay':'3ms','loss':1,'max_queue_size':10000000}
    net.addLink(ap1, destination, cls=TCLink , **ap1dst)

    # net.plotGraph(max_x=100, max_y=100)

    info( '*** Starting network\n')
    net.build()
    info( '*** Starting controllers\n')
    c0.start()

    info( '*** Starting switches/APs\n')
    ap1.start([c0])

    info('*** Adding static flow rules\n')
    ap1.cmd('ovs-ofctl add-flow ap1 "in_port=1,actions=output:2"')
    ap1.cmd('ovs-ofctl add-flow ap1 "in_port=2,actions=output:1"')


    info('*** Running pingall\n')
    sleep(1)
    net.pingAll()

    info('*** Post configure nodes\n')
    info('*** Opening terminals and running commands\n')
    sleep(5)  # 等待10秒
    # sta1.sendCmd('timeout 11m python3 source.py 8000 10.0.0.1 9999')
    # h1.sendCmd('timeout 10m python3 destination.py')
    sources_addresses = []
    for i, source in enumerate(sources):
        listen_port = 8000 + i
        ip = source.IP()
        sources_addresses.append(f"{ip}:{listen_port}")
        makeTerm(source, cmd=f'timeout 11m python3 source_wifi.py {listen_port} 10.0.0.1 9999')
    makeTerm(destination, cmd='timeout 10m python3 destination_wifi.py --sources ' + ' '.join(sources_addresses))
    info('*** Running CLI\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel( 'info' )
    myNetwork()

