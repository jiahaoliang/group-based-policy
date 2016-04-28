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
import copy
import ast
from oslo_log import log as logging

from neutron_lbaas.drivers import driver_base as n_driver_base

from gbpservice.nfp.common import exceptions
from gbpservice.nfp.configurator.lib import lbv2_constants
from gbpservice.nfp.configurator.drivers.base import base_driver

from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import neutron_lbaas_data_models as n_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.v2.haproxy.octavia_lib.\
    common import data_models as o_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.v2.haproxy.\
    rest_api_driver import HaproxyAmphoraLoadBalancerDriver
from gbpservice.nfp.configurator.drivers.loadbalancer.v2.haproxy.octavia_lib.\
    network import data_models as network_data_models
from gbpservice.nfp.configurator.drivers.loadbalancer.v2.haproxy.octavia_lib.\
    common import constants

# Assume orchestrator already created this amphora
# TODO: This part need to be removed once the ochestartor part is done
# AMP = o_data_models.Amphora(
#     lb_network_ip = "11.0.0.4",
#     id = "121daa13-d64b-4aae-ba4c-6aa001971ed7",
#     status = constants.ACTIVE
# )

DRIVER_NAME = 'loadbalancerv2'

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
    def _get_common_args(self, obj):
        return {
            'id': obj.id,
            'project_id': obj.tenant_id,
            'name': obj.name,
            'description': obj.description,
            'enabled': obj.admin_state_up,
            'operating_status': obj.operating_status,
        }

    # Update Octavia model from dict
    def _update(self, octavia_data_model, update_dict):
        for key, value in update_dict.items():
            setattr(octavia_data_model, key, value)
        return octavia_data_model

    # Translate loadbalancer neutron model dict to octavia model
    def get_loadbalancer_octavia_model(self, loadbalancer_dict):
        loadbalancer = n_data_models.LoadBalancer.from_dict(
            copy.deepcopy(loadbalancer_dict))
        ret = o_data_models.LoadBalancer()
        args = self._get_common_args(loadbalancer)
        vip = o_data_models.Vip(
            load_balancer_id=loadbalancer.id,
            ip_address=loadbalancer.vip_address,
            subnet_id=loadbalancer.vip_subnet_id,
            port_id=loadbalancer.vip_port.id,
            load_balancer=ret
        )
        amphorae = self.driver.get_amphora(loadbalancer.id)
        # TODO: vrrp_group, topology, server_group_id are not included yet
        args.update({
            'vip': vip,
            'amphorae': amphorae,
            'provisioning_status': loadbalancer.provisioning_status,
        })
        if loadbalancer_dict.get('listeners'):
            listeners = []
            pools = []
            for listener_dict in loadbalancer_dict.get('listeners'):
                listener = self.get_listener_octavia_model(listener_dict)
                listener.load_balancer = ret
                listeners.append(listener)
                pools.extend(listener.pools)
                for pool in listener.pools:
                    if pool.id not in [pool.id for pool in pools]:
                        pools.append(pool)
            args.update({
                'listeners': listeners,
                'pools': pools,
            })

        ret = self._update(ret, args)
        return ret

    # Translate listener neutron model dict to octavia model
    def get_listener_octavia_model(self, listener_dict):
        # Must use a copy because from_dict will modify the original dict
        listener = n_data_models.Listener.from_dict(
            copy.deepcopy(listener_dict))
        ret = o_data_models.Listener()
        args = self._get_common_args(listener)
        sni_containers = []
        if listener_dict.get('sni_containers'):
            sni_containers.extend(
                o_data_models.SNI.from_dict(sni_dict)
                for sni_dict in listener_dict.get('sni_containers')
            )
        if listener_dict.get('loadbalancer'):
            loadbalancer = self.get_loadbalancer_octavia_model(
                listener_dict.get('loadbalancer'))
            if listener.id not in [_listener.id for _listener
                                   in loadbalancer.listeners]:
                loadbalancer.listeners.append(ret)
            args.update({
                'load_balancer': loadbalancer,
            })
        if listener_dict.get('default_pool'):
            pool = self.get_pool_octavia_model(
                listener_dict.get('default_pool'))
            if listener.id not in [_listener.id for _listener
                                   in pool.listeners]:
                pool.listeners.append(ret)
            # TODO: In Mitaka, we need to handle multiple pools
            pools = [pool]
            args.update({
                'default_pool': pool,
                'pools': pools,
            })
        args.update({
            'load_balancer_id': listener.loadbalancer_id,
            'protocol': listener.protocol,
            'protocol_port': listener.protocol_port,
            'connection_limit': listener.connection_limit,
            'default_pool_id': listener.default_pool_id,
            'tls_certificate_id': listener.default_tls_container_id,
            'sni_containers': sni_containers,
            'provisioning_status': listener.provisioning_status,
        })
        ret = self._update(ret, args)
        return ret

    # Translate pool neutron model dict to octavia model
    def get_pool_octavia_model(self, pool_dict):
        pool = n_data_models.Pool.from_dict(
            copy.deepcopy(pool_dict)
        )
        ret = o_data_models.Pool()
        args = self._get_common_args(pool)
        # TODO: In Mitaka, instead of pool.listener,
        # there are pool.listeners. We need to handle that
        if pool_dict.get('listener'):
            listener = self.get_listener_octavia_model(
                pool_dict.get('listener'))
            if pool.id not in [_pool.id for _pool in listener.pools]:
                listener.pools.append(ret)
            if (not listener.default_pool) \
                    or (listener.default_pool_id == pool.id):
                listener.default_pool = ret
            listeners = [listener]
            args.update({
                'listeners': listeners,
            })
            if listener.load_balancer:
                if pool.id not in [_pool.id for _pool
                                   in listener.load_balancer.pools]:
                    listener.load_balancer.pools.append(ret)
                args.update({
                    'load_balancer': listener.load_balancer,
                    'load_balancer_id': listener.load_balancer_id,
                })
        if pool_dict.get('members'):
            members = []
            for member_dict in pool_dict.get('members'):
                member = self.get_member_octavia_model(member_dict)
                if not member.pool:
                    member.pool = ret
                members.append(member)
            args.update({
                'members': members
            })

        # TODO: HealthMonitor, L7Policy are not added
        args.update({
            'protocol': pool.protocol,
            'lb_algorithm': pool.lb_algorithm,
            'session_persistence': pool.session_persistence,
        })
        ret = self._update(ret, args)
        return ret

    # Translate member neutron model dict to octavia model
    def get_member_octavia_model(self, member_dict):
        member = n_data_models.Member.from_dict(
            copy.deepcopy(member_dict)
        )
        ret = o_data_models.Member()
        args = {
            'id': member.id,
            'project_id': member.tenant_id,
            'pool_id': member.pool_id,
            'ip_address': member.address,
            'protocol_port': member.protocol_port,
            'weight': member.weight,
            'enable': member.admin_state_up,
            'subnet_id': member.subnet_id,
            'operating_status': member.operating_status,
        }
        if member_dict.get('pool'):
            pool = self.get_pool_octavia_model(member_dict.get('pool'))
            args.update({
                'pool': pool
            })
        ret = self._update(ret, args)
        return ret


class HaproxyLoadBalancerDriver(n_driver_base.LoadBalancerBaseDriver,
                                base_driver.BaseDriver):
    service_type = 'loadbalancerv2'
    # TODO(jiahao): store the amphorae info locally, need to remove later
    # amphorae = {"loadbalancer_id": [o_data_models.Amphora(
    #                                 lb_network_ip, id, status)]}
    amphorae = {}

    def __init__(self, plugin=None):
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
        return self.amphorae.get(loadbalancer_id)

    def add_amphora(self, loadbalancer_id,
                    lb_network_ip, amp_id, status=constants.ACTIVE):
        if not self.get_amphora(loadbalancer_id):
            amp = o_data_models.Amphora(lb_network_ip=lb_network_ip,
                                        id=amp_id,
                                        status=status)
            self.amphorae[loadbalancer_id] = [amp]

    def configure_healthmonitor(self, context, kwargs):
        """Overriding BaseDriver's configure_healthmonitor().
           It does netcat to HAPROXY_AGENT_LISTEN_PORT 1234.
           HaProxy agent runs inside service vm..Once agent is up and
           reachable, service vm is assumed to be active.

           :param context - context
           :param kwargs - kwargs coming from orchestrator

           Returns: SUCCESS/FAILED

        """
        ip = kwargs.get('mgmt_ip')
        port = str(lbv2_constants.HAPROXY_AGENT_LISTEN_PORT)
        command = 'nc ' + ip + ' ' + port + ' -z'
        return self._check_vm_health(command)

class HaproxyCommonManager(object):

    def create(self, context, obj):
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, obj['id'])

    def update(self, context, old_obj, obj):
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, obj['id'])

    def delete(self, context, obj):
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, obj['id'])


class HaproxyLoadBalancerManager(HaproxyCommonManager,
                                 n_driver_base.BaseLoadBalancerManager):

    def _get_amphorae_network_config(self,
                                     context,
                                     loadbalancer_dict,
                                     loadbalancer_o_obj):
        loadbalancer_n_obj = n_data_models.LoadBalancer.from_dict(
            copy.deepcopy(loadbalancer_dict))

        amphorae_network_config = {}

        for amp in loadbalancer_o_obj.amphorae:
            if amp.status != constants.DELETED:
                # Get vip_subnet
                vip_subnet = None
                for subnet_dict in context['service_info']['subnets']:
                    if subnet_dict['id'] == loadbalancer_n_obj.vip_subnet_id:
                        vip_subnet = n_data_models.Subnet.from_dict(
                            copy.deepcopy(subnet_dict))
                        break
                if vip_subnet is None:
                    raise exceptions.IncompleteData(
                        "VIP subnet information is not found")

                # Get vip_port
                vip_port = None
                for port_dict in context['service_info']['ports']:
                    if port_dict['id'] == loadbalancer_n_obj.vip_port_id:
                        vip_port = n_data_models.Port.from_dict(
                            copy.deepcopy(port_dict))
                        break
                if vip_port is None:
                    raise  exceptions.IncompleteData(
                        "VIP port information is not found")

                # Get vrrp_port
                # vrrp_port = None
                # for port_dict in context['service_info']['ports']:
                #     if port_dict['device_id'] == amp.compute_id:
                #         for fix_ip in port_dict['fixed_ips']:
                #             if fix_ip['subnet_id'] == \
                #                     loadbalancer_n_obj.vip_subnet_id:
                #                 vrrp_port = n_data_models.Port.from_dict(
                #                     copy.deepcopy(port_dict))
                #                 break
                #         if vrrp_port is not None:
                #             break
                sc_metadata = ast.literal_eval(
                    loadbalancer_dict['description'])
                vrrp_port = n_data_models.Port(
                    mac_address=sc_metadata.provider_interface_mac)
                if vrrp_port is None:
                    raise exceptions.IncompleteData(
                        "VRRP port information is not found")

                amphorae_network_config[amp.id] = \
                    network_data_models.AmphoraNetworkConfig(
                        amphora=amp,
                        vip_subnet=vip_subnet,
                        vip_port=vip_port,
                        vrrp_port=vrrp_port
                    )

        return amphorae_network_config

    def create(self, context, loadbalancer):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, loadbalancer['id'])

        # TODO(jiahao): use network_function_id as amphora id
        sc_metadata = ast.literal_eval(loadbalancer['description'])
        self.driver.add_amphora(loadbalancer['id'],
                                sc_metadata['floating_ip'],
                                sc_metadata['network_function_id'])
        loadbalancer_o_obj = self.driver.o_models_builder.\
            get_loadbalancer_octavia_model(loadbalancer)
        amphorae_network_config = self._get_amphorae_network_config(
                                     context, loadbalancer, loadbalancer_o_obj)
        self.driver.amphora_driver.post_vip_plug(
                loadbalancer_o_obj, amphorae_network_config)
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

    def create(self, context, pool):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, pool['id'])
        pool_o_obj = self.driver.o_models_builder.\
            get_pool_octavia_model(pool)
        # For Mitaka, that would be multiple listeners within pool
        listener_o_obj = pool_o_obj.listeners[0]
        load_balancer_o_obj = pool_o_obj.load_balancer
        self.driver.amphora_driver.update(listener_o_obj,
                                          load_balancer_o_obj.vip)

    def update(self, context, old_pool, pool):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, pool['id'])

    def delete(self, context, pool):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, pool['id'])


class HaproxyMemberManager(HaproxyCommonManager,
                           n_driver_base.BaseMemberManager):

    def create(self, context, member):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, create %s", self.__class__.__name__, member['id'])
        member_o_obj = self.driver.o_models_builder.\
            get_member_octavia_model(member)
        listener_o_obj = member_o_obj.pool.listeners[0]
        load_balancer_o_obj = member_o_obj.pool.load_balancer
        self.driver.amphora_driver.update(listener_o_obj,
                                          load_balancer_o_obj.vip)

    def update(self, context, old_member, member):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, update %s", self.__class__.__name__, member['id'])

    def delete(self, context, member):
        ForkedPdb().set_trace()
        LOG.info("LB %s no-op, delete %s", self.__class__.__name__, member['id'])


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
