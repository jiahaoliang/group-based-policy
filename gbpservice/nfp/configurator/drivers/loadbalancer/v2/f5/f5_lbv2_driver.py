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

from neutron._i18n import _LI
from neutron_lbaas.drivers import driver_base as n_driver_base

from f5lbaasdriver.v2.bigip.service_builder import LBaaSv2ServiceBuilder
from f5_openstack_agent.lbaasv2.drivers.bigip import agent_manager as f5_agent
from f5_openstack_agent.lbaasv2.drivers.bigip.icontrol_driver \
    import iControlDriver
from gbpservice.nfp.configurator.drivers.base import base_driver
from gbpservice.nfp.configurator.drivers.loadbalancer.\
    v2.haproxy import neutron_lbaas_data_models as n_data_models
from gbpservice.nfp.configurator.lib import constants as common_const
from gbpservice.nfp.configurator.lib import lb_constants
from gbpservice.nfp.configurator.lib import lbv2_constants
from gbpservice.nfp.core import log as nfp_logging

LOG = nfp_logging.getLogger(__name__)

# Copy from loadbalancer/v1/haproxy/haproxy_lb_driver.py
""" Loadbalancer generic configuration driver for handling device
configuration requests.
"""


class LbGenericConfigDriver(object):
    """
    Driver class for implementing loadbalancer configuration
    requests from Orchestrator.
    """

    def __init__(self):
        pass

    def configure_interfaces(self, context, resource_data):
        """ Configure interfaces for the service VM.
        Calls static IP configuration function and implements
        persistent rule addition in the service VM.
        Issues REST call to service VM for configuration of interfaces.
        :param context: neutron context
        :param resource_data: a dictionary of loadbalancer objects
        send by neutron plugin
        Returns: SUCCESS/Failure message with reason.
        """

        mgmt_ip = resource_data['mgmt_ip']

        try:
            result_log_forward = self._configure_log_forwarding(
                lb_constants.REQUEST_URL, mgmt_ip,
                self.port)
        except Exception as err:
            msg = ("Failed to configure log forwarding for service at %s. "
                   "Error: %s" % (mgmt_ip, err))
            LOG.error(msg)
            return msg
        else:
            if result_log_forward == common_const.UNHANDLED:
                pass
            elif result_log_forward != lb_constants.STATUS_SUCCESS:
                msg = ("Failed to configure log forwarding for service at %s. "
                       % mgmt_ip)
                LOG.error(msg)
                return result_log_forward
            else:
                msg = ("Configured log forwarding for service at %s. "
                       "Result: %s" % (mgmt_ip, result_log_forward))
                LOG.info(msg)

        return lb_constants.STATUS_SUCCESS


# Monkey patching lbaasv2 plugin for f5 service_builder
class MonkeyPatch(object):
    def __init__(self):
        pass


class LoadBalancerPluginv2(object):

    def __init__(self):
        # Instead of getting info from Neutron db
        # we get info from the loadbalancer object
        self.loadbalancer = None

        self.db = MonkeyPatch()
        self.db._core_plugin = MonkeyPatch()

        self.db.get_listeners = self.get_listeners
        self.db.get_pool = self.get_pool
        self.db.get_pool_members = self.get_pool_members
        self.db.get_healthmonitor = self.get_healthmonitor

        self.db._core_plugin.get_ports = self.get_ports
        self.db._core_plugin.get_port = self.get_port
        self.db._core_plugin.get_subnet = self.get_subnet
        self.db._core_plugin.get_network = self.get_network
        self.db._core_plugin.get_agents = self.get_agents

    def get_listeners(self, context, filters=None):
        return self.loadbalancer.listeners

    def get_pool(self, context, id):
        for pool in self.loadbalancer.pools:
            if pool.id == id:
                return pool
        return None

    def get_pool_members(self, context, filters=None):
        pool_id = filters['pool_id'][0]
        for pool in self.loadbalancer.pools:
            if pool.id == id:
                return pool.members
        return None

    def get_healthmonitor(self, context, id):
        for pool in self.loadbalancer.pools:
            if pool.healthmonitor_id == id:
                return pool.healthmonitor
        return None

    def get_ports(self, context, filters=None):
        ports = []
        subnet_id = filter['fixed_ips']['subnet_id'][0]
        ip_address = filter['fixed_ips']['ip_address'][0]
        for port in context['service_info']['ports']:
            if (port['fixed_ips'][0]['subnet_id'] == subnet_id and
                    port['fixed_ips'][0]['ip_address'] == ip_address):
                ports.append(port)
        return ports

    def get_port(self, context, id):
        for port in context['service_info']['ports']:
            if port['id'] == id:
                return port
        return None

    def get_subnet(self, context, id):
        for subnet in context['service_info']['subnets']:
            if subnet['id'] == id:
                return subnet
        return None

    def get_network(self, context, id):
        for network in context['service_info']['networks']:
            if network['id'] == id:
                return network
        return None

    def get_agents(self, context, filters=None):
        # return context['service_info']['agents']
        return []


class F5LoadBalancerDriver(n_driver_base.LoadBalancerBaseDriver,
                           LbGenericConfigDriver,
                           base_driver.BaseDriver):
    service_type = 'loadbalancerv2'
    service_vendor = 'f5networks'

    def __init__(self, plugin_rpc=None, conf=None):
        self.cache = f5_agent.LogicalServiceCache()
        self.lbdriver = iControlDriver(conf)

        # Monkey patching self.plugin for service_builder
        self.plugin = LoadBalancerPluginv2()
        self.service_builder = LBaaSv2ServiceBuilder(self)

        self.load_balancer = F5LoadBalancerManager(self)
        self.listener = F5ListenerManager(self)
        self.pool = F5PoolManager(self)
        self.member = F5MemberManager(self)
        self.health_monitor = F5HealthMonitorManager(self)

    def build_service(self, context, loadbalancer_obj):
        self.plugin.loadbalancer = loadbalancer_obj
        service = self.service_builder.build(context, loadbalancer_obj)
        self.plugin.loadbalancer = None
        return service


class F5CommonManager(object):

    def __init__(self, driver):
        self.driver = driver

    def _deploy(self, obj):
        pass

    def create(self, context, obj):
        LOG.info(_LI("LB %(cls_name)s, create %(id)s"),
                 {"cls_name": self.__class__.__name__, "id": obj['id']})

    def update(self, context, old_obj, obj):
        LOG.info(_LI("LB %(cls_name)s, update %(id)s"),
                 {"cls_name": self.__class__.__name__, "id": obj['id']})

    def delete(self, context, obj):
        LOG.info(_LI("LB %(cls_name)s, delete %(id)s"),
                 {"cls_name": self.__class__.__name__, "id": obj['id']})


class F5LoadBalancerManager(F5CommonManager,
                            n_driver_base.BaseLoadBalancerManager):

    def create(self, context, loadbalancer):
        loadbalancer_obj = n_data_models.LoadBalancer.from_dict(loadbalancer)
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.create_loadbalancer(loadbalancer, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, create %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": loadbalancer['id']})

    def update(self, context, old_loadbalancer, loadbalancer):
        loadbalancer_obj = n_data_models.LoadBalancer.from_dict(loadbalancer)
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.update_loadbalancer(loadbalancer, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, update %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": loadbalancer['id']})

    def delete(self, context, loadbalancer):
        loadbalancer_obj = n_data_models.LoadBalancer.from_dict(loadbalancer)
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.delete_loadbalancer(loadbalancer, service)
        self.cache.remove_by_loadbalancer_id(loadbalancer['id'])
        LOG.info(_LI("LB %(cls_name)s, delete %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": loadbalancer['id']})

    @property
    def allocates_vip(self):
        LOG.info(_LI('allocates_vip queried'))
        return False

    def create_and_allocate_vip(self, context, obj):
        LOG.info(_LI("LB %(cls_name)s, create_and_allocate_vip %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": obj['id']})
        self.create(context, obj)

    def refresh(self, context, obj):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        LOG.info(_LI("LB pool refresh %s"), obj['id'])

    def stats(self, context, lb_obj):
        LOG.info(_LI("LB stats %s"), lb_obj['id'])
        return {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0
        }


class F5ListenerManager(F5CommonManager,
                        n_driver_base.BaseListenerManager):

    def create(self, context, listener):
        listener_obj = n_data_models.Listener.from_dict(listener)
        loadbalancer_obj = listener_obj.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.create_listener(listener, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, create %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": listener['id']})

    def update(self, context, old_listener, listener):
        listener_obj = n_data_models.Listener.from_dict(listener)
        loadbalancer_obj = listener_obj.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.update_listener(listener, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, update %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": listener['id']})

    def delete(self, context, listener):
        listener_obj = n_data_models.Listener.from_dict(listener)
        loadbalancer_obj = listener_obj.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.delete_listener(listener, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, delete %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": listener['id']})


class F5PoolManager(F5CommonManager,
                    n_driver_base.BasePoolManager):

    def create(self, context, pool):
        pool_obj = n_data_models.Pool.from_dict(pool)
        loadbalancer_obj = pool_obj.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.create_pool(pool, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, create %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": pool['id']})

    def update(self, context, old_pool, pool):
        pool_obj = n_data_models.Pool.from_dict(pool)
        loadbalancer_obj = pool_obj.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.update_pool(pool, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, update %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": pool['id']})

    def delete(self, context, pool):
        pool_obj = n_data_models.Pool.from_dict(pool)
        loadbalancer_obj = pool_obj.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.delete_pool(pool, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, delete %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": pool['id']})

class F5MemberManager(F5CommonManager,
                      n_driver_base.BaseMemberManager):

    def create(self, context, member):
        member_obj = n_data_models.Member.from_dict(member)
        loadbalancer_obj = member_obj.pool.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.create_member(member, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, create %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": member['id']})

    def update(self, context, old_member, member):
        member_obj = n_data_models.Member.from_dict(member)
        loadbalancer_obj = member_obj.pool.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.update_member(member, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, update %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": member['id']})

    def delete(self, context, member):
        member_obj = n_data_models.Member.from_dict(member)
        loadbalancer_obj = member_obj.pool.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.delete_member(member, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, delete %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": member['id']})


class F5HealthMonitorManager(F5CommonManager,
                             n_driver_base.BaseHealthMonitorManager):

    def create(self, context, health_monitor):
        hm_obj = n_data_models.HealthMonitor.from_dict(health_monitor)
        loadbalancer_obj = hm_obj.pool.listener.loadbalancer
        sservice = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.create_health_monitor(health_monitor, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, create %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": health_monitor['id']})

    def update(self, context, old_health_monitor, health_monitor):
        hm_obj = n_data_models.HealthMonitor.from_dict(health_monitor)
        loadbalancer_obj = hm_obj.pool.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.update_health_monitor(health_monitor, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, update %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": health_monitor['id']})

    def delete(self, context, health_monitor):
        hm_obj = n_data_models.HealthMonitor.from_dict(health_monitor)
        loadbalancer_obj = hm_obj.pool.listener.loadbalancer
        service = self.driver.build_service(context, loadbalancer_obj)
        self.driver.lbdriver.delete_health_monitor(health_monitor, service)
        self.driver.cache.put(service, agent_host="default")
        LOG.info(_LI("LB %(cls_name)s, delete %(id)s"),
                 {"cls_name": self.__class__.__name__,
                  "id": health_monitor['id']})
