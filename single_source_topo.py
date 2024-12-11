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


def myNetwork():

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
    ap1 = net.addAccessPoint('ap1', ssid='ap1-ssid', mode='g', channel='1',
                              position='50.0,50.0,0')

    info( '*** Add hosts/stations\n')
    h1 = net.addHost('h1', cls=Host, ip='10.0.0.1', defaultRoute=None)
    sta1 = net.addStation('sta1', ip='10.0.0.2',
                           position='52.5,50.0,0')

    info("*** Configuring Propagation Model\n")
    net.setPropagationModel(model="logDistance", exp=4.5)

    info("*** Configuring wifi nodes\n")
    net.configureWifiNodes()

    info( '*** Add links\n')
    # sta1ap1 = {'delay':'50ms','loss':5,'max_queue_size':1000}
    net.addLink(sta1, ap1)
    ap1h1 = {} #{'bw':10,'delay':'3ms','loss':1,'max_queue_size':10000000}
    net.addLink(ap1, h1, cls=TCLink , **ap1h1)

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
    makeTerm(sta1, cmd='timeout 11m python3 wifresh_app_source.py 8000 10.0.0.1 9999')
    makeTerm(h1, cmd='timeout 10m python3 wifresh_app_destination.py --source 10.0.0.2:8000')
    info('*** Running CLI\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel( 'info' )
    myNetwork()

