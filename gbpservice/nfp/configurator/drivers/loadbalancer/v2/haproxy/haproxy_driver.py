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

from neutron_lbaas.drivers import driver_base as n_driver_base

from gbpservice.nfp.common import exceptions
from gbpservice.nfp.configurator.drivers.base import base_driver

from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import neutron_lbaas_data_models as n_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import octavia_data_models as o_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy.rest_api_driver import HaproxyAmphoraLoadBalancerDriver
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import data_models

from octavia.common import constants
# Assume orchestrator already created this amphora
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


# As we use the rest client and amphora image from Octavia,
# we need to have a helper class to simulate Octavia DB operation
# in order to get Octavia data models from Neutron-lbaas data models
class OctaviaDataModelBuilder(object):

    def __init__(self, driver=None):
        self.driver = driver

    # All Octavia data models have these attributes
    def _get_common_args(self, dict):
        return {
            'id': dict['id'],
            'project_id': dict['tenant_id'],
            'name': dict['name'],
            'description': dict['description'],
            'enabled': dict['admin_state_up']
        }

    # Translate loadbalancer neutron model dict to octavia model
    def get_loadbalancer_octavia_model(self, loadbalancer_dict):
        ret = o_data_models.LoadBalancer()
        args = self._get_common_args(loadbalancer_dict)
        vip = o_data_models.Vip(
            load_balancer_id=loadbalancer_dict['id'],
            ip_address=loadbalancer_dict['vip_address'],
            subnet_id=loadbalancer_dict['vip_subnet_id'],
            port_id=loadbalancer_dict['vip_port.id'],
            load_balancer=ret
        )
        amphorae = self.driver.get_amphora(loadbalancer.id)
        # TODO: vrrp_group, topology, server_group_id are not included yet
        args.update(
            vip=vip,
            amphorae=amphorae
        )
        ret.update(args)
        return ret

    # Translate listener neutron model dict to octavia model
    def get_listener_octavia_model(self,listener_dict):
        args = self._get_common_args(listener_dict)
        sni_container_ids = [tls_container_id
                             for tls_container_id
                             in listener_dict['sni_container_refs']]
        sni_containers = [{'listener_id': listener_dict['id'],
                           'tls_container_id': tls_container_id}
                          for tls_container_id in sni_container_ids]
        args.update({
            'load_balancer_id': listener_dict['loadbalancer']['id'],
            'protocol': listener_dict['protocol'],
            'protocol_port': listener_dict['protocol_port'],
            'connection_limit': listener_dict['connection_limit'],
            'default_pool_id': listener_dict['default_pool_id'],
            'tls_certificate_id': listener_dict['default_tls_container_ref'],
            'sni_containers': sni_containers,
            'provisioning_status': constants.PENDING_CREATE,
            'operating_status': constants.OFFLINE
        })
        ret = o_data_models.Listener.from_dict(args)
        return ret

    def associate_listerner_loadbalancer(self, context, listener_o_obj):
        if listener_o_obj.load_balancer_id is not None:
            for dict in context['service_info']['loadbalancers']:
                if dict['id'] == listener_o_obj.load_balancer_id:
                    lb_dict = dict
                    break
            if lb_dict is not None:
                lb = self.get_loadbalancer_octavia_model(lb_dict)
            if lb_dict is None or lb is None:
                raise exceptions.IncompleteData(
                    "Loadbalancer information is not found")
            lb.listeners.append(listener_o_obj)
            lb.pools = listener_o_obj.pools
            listener_o_obj.load_balancer = lb
        return listener_o_obj


class HaproxyLoadBalancerDriver(n_driver_base.LoadBalancerBaseDriver,
                                base_driver.BaseDriver):
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
        self.o_models_builder = OctaviaDataModelBuilder(self)

    # Get Amphora object given the loadbalancer_id
    def get_amphora(self, loadbalancer_id):
        return [AMP]

class HaproxyCommonManager(object):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyLoadBalancerManager(HaproxyCommonManager,
                                 n_driver_base.BaseLoadBalancerManager):

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
                break
        if vip_port is None:
            raise  exceptions.IncompleteData(
                "VIP port information is not found")

        # Get vrrp_port
        for port_dict in context['service_info']['ports']:
            if port_dict['device_id'] == amp.compute_id:
                for fix_ip in port_dict['fixed_ips']:
                    if fix_ip['subnet_id']== loadbalancer_obj.vip_subnet_id:
                        vrrp_port = n_data_models.Port.from_dict(port_dict)
                        break
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
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, loadbalancer['id'])

    def delete(self, context, loadbalancer):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, loadbalancer['id'])

    @property
    def allocates_vip(self):
        LOG.info('allocates_vip queried')
        return False

    def create_and_allocate_vip(self, context, obj):
        ForkedPdb().set_trace()
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
                             n_driver_base.BaseListenerManager):

    def create(self, context, listener):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, listener['id'])
        listener_o_obj = self.driver.o_models_builder.\
            get_listener_octavia_model(listener)
        self.driver.o_models_builder.\
            associate_listerner_loadbalancer(context, listener_o_obj)
        self.driver.amphora_driver.update(listener_o_obj,
                                          listener_o_obj.load_balancer.vip)

    def update(self, context, old_listener, listener):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, listener['id'])

    def delete(self, context, listener):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, listener['id'])


class HaproxyPoolManager(HaproxyCommonManager,
                         n_driver_base.BasePoolManager):

    def create(self, context, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyMemberManager(HaproxyCommonManager,
                           n_driver_base.BaseMemberManager):

    def create(self, context, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyHealthMonitorManager(HaproxyCommonManager,
                                  n_driver_base.BaseHealthMonitorManager):

    def create(self, context, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])
