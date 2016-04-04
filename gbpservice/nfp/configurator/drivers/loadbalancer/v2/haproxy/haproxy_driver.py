# Copyright 2014, Doug Wiegley (dougwig), A10 Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import sys
import pdb
from oslo_log import log as logging

from neutron_lbaas.drivers import driver_base

from gbpservice.nfp.common import exceptions

from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import neutron_lbaas_data_models as n_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import octavia_data_models as o_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy.rest_api_driver import HaproxyAmphoraLoadBalancerDriver
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import data_models

from octavia.common import constants
# Assume ochestrator already created this amphora
# TODO: This part need to be removed once the ochestartor part is done
AMP = o_data_models.Amphora(
    lb_network_ip = "10.0.134.4",
    id = "121daa13-d64b-4aae-ba4c-6aa001971ed7",
    status = constants.ACTIVE,
    compute_id = "a1931b26-5635-49b6-917e-4da8f622389e"
)

LOG = logging.getLogger(__name__)

class ForkedPdb(pdb.Pdb):
    """A Pdb subclass that may be used
    from a forked multiprocessing child

    """
    def interaction(self, *args, **kwargs):
        _stdin = sys.stdin
        try:
            sys.stdin = file('/dev/stdin')
            pdb.Pdb.interaction(self, *args, **kwargs)
        finally:
            sys.stdin = _stdin

class HaproxyLoadBalancerDriver(driver_base.LoadBalancerBaseDriver):
    service_type = 'loadbalancerv2'

    def __init__(self, plugin):
        super(HaproxyLoadBalancerDriver, self).__init__(plugin)

        # Each of the major LBaaS objects in the neutron database
        # need a corresponding manager/handler class.
        #
        # Put common things that are shared across the entire driver, like
        # config or a rest client handle, here.
        #
        # This function is executed when neutron-server starts.

        self.amphora_driver = HaproxyAmphoraLoadBalancerDriver()

        self.load_balancer = HaproxyLoadBalancerManager(self)
        self.listener = HaproxyListenerManager(self)
        self.pool = HaproxyPoolManager(self)
        self.member = HaproxyMemberManager(self)
        self.health_monitor = HaproxyHealthMonitorManager(self)


class HaproxyCommonManager(object):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyLoadBalancerManager(HaproxyCommonManager,
                                 driver_base.BaseLoadBalancerManager):

    def create(self, context, loadbalancer, amp=AMP):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, loadbalancer['id'])
        # plug network
        # plug vip
        loadbalancer_obj = n_data_models.LoadBalancer.from_dict(loadbalancer)
        
        # Get vip_subnet
        for subnet_dict in context['service_info']['subnets']:
            if subnet_dict['id'] == loadbalancer_obj.vip_subnet_id:
                vip_subnet = n_data_models.Subnet.from_dict(subnet_dict)
                break
        if vip_subnet is None:
            raise exceptions.IncompleteData(
                "VIP subnet information is not found")

        # Get vip_port
        for port_dict in context['service_info']['ports']:
            if port_dict['id'] == loadbalancer_obj.vip_port_id:
                vip_port = n_data_models.Port.from_dict(port_dict)
        if vip_port is None:
            raise  exceptions.IncompleteData(
                "VIP port information is not found")

        # Get vrrp_port
        for port_dict in context['service_info']['ports']:
            if port_dict['device_id'] == amp.compute_id:
                for fix_ip in port_dict['fixed_ips']:
                    if fix_ip['subnet_id']== loadbalancer_obj.vip_subnet_id:
                        vrrp_port = n_data_models.Port.from_dict(port_dict)
        if vrrp_port is None:
            raise  exceptions.IncompleteData(
                "VRRP port information is not found")

        amphorae_network_config = {}

        amphorae_network_config[amp.id] = data_models.AmphoraNetworkConfig(
            amphora=amp,
            vip_subnet=vip_subnet,
            vip_port=vip_port,
            vrrp_port=vrrp_port
        )

        self.driver.amphora_driver.post_vip_plug(
                loadbalancer_obj, amphorae_network_config)
        LOG.info("Notfied amphora of vip plug")

    def update(self, context, old_loadbalancer, loadbalancer):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, loadbalancer['id'])

    def delete(self, context, loadbalancer):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, loadbalancer['id'])

    @property
    def allocates_vip(self):
        LOG.info('allocates_vip queried')
        return False

    def create_and_allocate_vip(self, context, obj):
        LOG.info("LB %s no-op, create_and_allocate_vip %s",
                  self.__class__.__name__, obj['id'])
        self.create(context, obj)

    def refresh(self, context, obj):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        LOG.info("LB pool refresh %s", obj['id'])

    def stats(self, context, lb_obj):
        LOG.info("LB stats %s", lb_obj['id'])
        return {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0
        }


class HaproxyListenerManager(HaproxyCommonManager,
                             driver_base.BaseListenerManager):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyPoolManager(HaproxyCommonManager,
                         driver_base.BasePoolManager):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyMemberManager(HaproxyCommonManager,
                           driver_base.BaseMemberManager):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyHealthMonitorManager(HaproxyCommonManager,
                                  driver_base.BaseHealthMonitorManager):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])
