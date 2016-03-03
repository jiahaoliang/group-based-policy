
import logging
import netifaces

from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
from operations import configOpts
from execformat.executor import session

logger = logging.getLogger(__name__)

COMMAND = "interfaces ethernet %s address %s/%s"

class ProviderIp(configOpts):
    def __init__(self):
        pass

    def configure(self, data):
        try:
            session.setup_config_session()
            map = {}
            provider_ip = data['provider_ip']
            provider_mac = data['provider_mac']
            provider_cidr = data['provider_cidr']
            
            stitching_ip = data['stitching_ip']
            stitching_mac = data['stitching_mac']
            stitching_cidr = data['stitching_cidr']
    
            interfaces = netifaces.interfaces()
            self.provider_ptg_interfaces = list()
            for interface in interfaces:
                physical_interface = netifaces.ifaddresses(
                                                interface).get(AF_LINK)
                if not physical_interface:
                    continue
                mac_addr = netifaces.ifaddresses(
                                        interface)[AF_LINK][0]['addr']
                if 'eth' in interface:
                    map.update({interface: mac_addr})
            
            print map
            
            for (interface, mac_addr) in map.iteritems():
                if provider_mac == mac_addr:
                    set_ip = COMMAND % (interface, provider_ip, provider_cidr)
                elif stitching_mac == mac_addr:
                    set_ip = COMMAND % (interface, stitching_ip, stitching_cidr)
                else:
                    continue
                print set_ip
                result = self.set(set_ip.split())
                logger.debug("Result of add static ip is %s." % result)
            session.commit()
        except Exception as err:
            logger.error("Failed to set provider IP.")
            session.discard()
        

data = {'provider_ip': '192.168.132.210',
        'provider_mac': '52:54:00:90:3f:36',
        'provider_cidr': '24',
        'stitching_ip': '192.168.132.201',
        'stitching_mac': '52:54:00:90:3g:36',
        'stitching_cidr': '24'}
obj = ProviderIp()
obj.configure(data)