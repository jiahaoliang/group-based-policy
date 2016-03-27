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

from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2
from gbpservice.nfp.config_orchestrator.agent import topics as a_topics
from gbpservice.nfp.config_orchestrator.agent.common import *
from gbpservice.nfp.lib.transport import *


LOG = logging.getLogger(__name__)


class Lbv2Agent(loadbalancer_dbv2.LoadBalancerPluginDbv2):
    RPC_API_VERSION = '1.0'
    _target = target.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        self._conf = conf
        self._sc = sc
        super(Lbv2Agent, self).__init__()

    def _post(self, context, tenant_id, name, **kwargs):
        db = self._context(context, tenant_id)
        context_dict = context.to_dict()
        context_dict.update({'service_info': db})
        kwargs.update({'context': context_dict})
        body = prepare_request_data(name, kwargs, "loadbalancerv2")
        send_request_to_configurator(self._conf, context, body, "CREATE")

    def _delete(self, context, tenant_id, name, **kwargs):
        db = self._context(context, tenant_id)
        context_dict = context.to_dict()
        context_dict.update({'service_info': db})
        kwargs.update({'context': context_dict})
        body = prepare_request_data(name, kwargs, "loadbalancerv2")
        send_request_to_configurator(self._conf, context, body, "DELETE")

    def create_loadbalancer(self, context, loadbalancer, driver_name, allocate_vip=True):
        self._post(
            context, loadbalancer['tenant_id'],
            'loadbalancer', loadbalancer=loadbalancer)

    def delete_loadbalancer(self, context, loadbalancer, delete_vip_port=True):
        self._delete(
            context, loadbalancer['tenant_id'],
            'loadbalancer', loadbalancer=loadbalancer)

    def create_listener(self, context, listener):
        self._post(
            context, listener['tenant_id'],
            'listener', listener=listener)

    def delete_listener(self, context, listener):
        self._delete(
            context, listener['tenant_id'],
            'listener', listener=listener)

    def create_pool(self, context, pool):
        self._post(
            context, pool['tenant_id'],
            'pool', pool=pool)

    def delete_pool(self, context, pool):
        self._delete(
            context, pool['tenant_id'],
            'pool', pool=pool)

    def create_pool_member(self, context, member, pool_id):
        self._post(
            context, member['tenant_id'],
            'member', member=member)

    def delete_pool_member(self, context, member):
        self._delete(
            context, member['tenant_id'],
            'member', member=member)

    def create_healthmonitor_on_pool(self, context, pool_id, healthmonitor):
        self._post(
            context, healthmonitor['tenant_id'],
            'healthmonitor', healthmonitor=healthmonitor)

    def create_healthmonitor(self, context, healthmonitor):
        self._post(
            context, healthmonitor['tenant_id'],
            'healthmonitor', healthmonitor=healthmonitor)

    def delete_healthmonitor(self, context, healthmonitor):
        self._delete(
            context, healthmonitor['tenant_id'],
            'healthmonitor', healthmonitor=healthmonitor)

    # TODO: What's L7policy?
    # disable L7policy
    # def create_l7policy(self, context, l7policy):
    #     self._post(
    #         context, l7policy['tenant_id'],
    #         'l7policy', l7policy=l7policy)
    #
    # def delete_l7policy(self, context, l7policy):
    #     self._delete(
    #         context, l7policy['tenant_id'],
    #         'l7policy', l7policy=l7policy)
    #
    # def create_l7policy_rule(self, context, rule, l7policy_id):
    #     self._post(
    #         context, rule['tenant_id'],
    #         'rule', rule=rule)
    #
    # def delete_l7policy_rule(self, context, rule):
    #     self._delete(
    #         context, rule['tenant_id'],
    #         'rule', rule=rule)

    # def _get_lb_context(self, context, filters):
    #     args = {'context': context, 'filters': filters}
    #     db_data = super(Lbv2Agent, self)
    #     return {'loadbalancers': db_data.get_loadbalancers(**args),
    #             'listeners': db_data.get_listeners(**args),
    #             'pools': db_data.get_pools(**args),
    #             'pool_members': db_data.get_pool_members(**args),
    #             'healthmonitors': db_data.get_healthmonitors(**args),
    #             'l7policies': db_data.get_l7policies(**args),
    #             'l7policy_rules': db_data.get_l7policy_rules(**args)}

    def _to_api_dict(self, objs):
        ret_list = []
        for obj in objs:
            ret_list.append(obj.to_api_dict())
        return ret_list

    def _get_lb_context(self, context, filters):
        args = {'context': context, 'filters': filters}
        db_data = super(Lbv2Agent, self)
        return {'loadbalancers': self._to_api_dict(db_data.get_loadbalancers(**args)),
                'listeners': self._to_api_dict(db_data.get_listeners(**args)),
                'pools': self._to_api_dict(db_data.get_pools(**args)),
                'pool_members': self._to_api_dict(db_data.get_pool_members(**args)),
                'healthmonitors': self._to_api_dict(db_data.get_healthmonitors(**args))}

    def _context(self, context, tenant_id):
        if context.is_admin:
            tenant_id = context.tenant_id
        filters = {'tenant_id': [tenant_id]}
        db = self._get_lb_context(context, filters)
        db.update(self._get_core_context(context, filters))
        return db

    def _get_core_context(self, context, filters):
        core_context_dict = get_core_context(context, filters, self._conf.host)
        del core_context_dict['routers']
        return core_context_dict


# class Lbv2Agent(agent_manager.LbaasAgentManager):
#
#     def __init__(self, conf, sc):
#         super(Lbv2Agent, self).__init__(conf)
#         self.plugin_rpc = agent_api.LbaasAgentApi(
#             topics.LBv2_NFP_CONFIGAGENT_TOPIC,
#             self.context,
#             self.conf.host
#         )
#
#     def create_loadbalancer(self, context, loadbalancer, driver_name):
#         loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer)
#         if driver_name not in self.device_drivers:
#             LOG.error(_LE('No device driver on agent: %s.'), driver_name)
#             self.plugin_rpc.update_status('loadbalancer', loadbalancer.id,
#                                           provisioning_status=constants.ERROR)
#             return
#         driver = self.device_drivers[driver_name]
#         try:
#             driver.loadbalancer.create(loadbalancer)
#         except Exception:
#             self._handle_failed_driver_call('create', loadbalancer,
#                                             driver.get_name())
#         else:
#             self.instance_mapping[loadbalancer.id] = driver_name
#             self._update_statuses(loadbalancer)
#
#     def update_loadbalancer(self, context, old_loadbalancer, loadbalancer):
#         loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer)
#         old_loadbalancer = data_models.LoadBalancer.from_dict(old_loadbalancer)
#         driver = self._get_driver(loadbalancer.id)
#         try:
#             driver.loadbalancer.update(old_loadbalancer, loadbalancer)
#         except Exception:
#             self._handle_failed_driver_call('update', loadbalancer,
#                                             driver.get_name())
#         else:
#             self._update_statuses(loadbalancer)
#
#     def delete_loadbalancer(self, context, loadbalancer):
#         loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer)
#         driver = self._get_driver(loadbalancer.id)
#         driver.loadbalancer.delete(loadbalancer)
#         del self.instance_mapping[loadbalancer.id]
#
#     def create_listener(self, context, listener):
#         listener = data_models.Listener.from_dict(listener)
#         driver = self._get_driver(listener.loadbalancer.id)
#         try:
#             driver.listener.create(listener)
#         except Exception:
#             self._handle_failed_driver_call('create', listener,
#                                             driver.get_name())
#         else:
#             self._update_statuses(listener)
#
#     def update_listener(self, context, old_listener, listener):
#         listener = data_models.Listener.from_dict(listener)
#         old_listener = data_models.Listener.from_dict(old_listener)
#         driver = self._get_driver(listener.loadbalancer.id)
#         try:
#             driver.listener.update(old_listener, listener)
#         except Exception:
#             self._handle_failed_driver_call('update', listener,
#                                             driver.get_name())
#         else:
#             self._update_statuses(listener)
#
#     def delete_listener(self, context, listener):
#         listener = data_models.Listener.from_dict(listener)
#         driver = self._get_driver(listener.loadbalancer.id)
#         driver.listener.delete(listener)
#
#     def create_pool(self, context, pool):
#         pool = data_models.Pool.from_dict(pool)
#         driver = self._get_driver(pool.listener.loadbalancer.id)
#         try:
#             driver.pool.create(pool)
#         except Exception:
#             self._handle_failed_driver_call('create', pool, driver.get_name())
#         else:
#             self._update_statuses(pool)
#
#     def update_pool(self, context, old_pool, pool):
#         pool = data_models.Pool.from_dict(pool)
#         old_pool = data_models.Pool.from_dict(old_pool)
#         driver = self._get_driver(pool.listener.loadbalancer.id)
#         try:
#             driver.pool.update(old_pool, pool)
#         except Exception:
#             self._handle_failed_driver_call('create', pool, driver.get_name())
#         else:
#             self._update_statuses(pool)
#
#     def delete_pool(self, context, pool):
#         pool = data_models.Pool.from_dict(pool)
#         driver = self._get_driver(pool.listener.loadbalancer.id)
#         driver.pool.delete(pool)
#
#     def create_member(self, context, member):
#         member = data_models.Member.from_dict(member)
#         driver = self._get_driver(member.pool.listener.loadbalancer.id)
#         try:
#             driver.member.create(member)
#         except Exception:
#             self._handle_failed_driver_call('create', member,
#                                             driver.get_name())
#         else:
#             self._update_statuses(member)
#
#     def update_member(self, context, old_member, member):
#         member = data_models.Member.from_dict(member)
#         old_member = data_models.Member.from_dict(old_member)
#         driver = self._get_driver(member.pool.listener.loadbalancer.id)
#         try:
#             driver.member.update(old_member, member)
#         except Exception:
#             self._handle_failed_driver_call('create', member,
#                                             driver.get_name())
#         else:
#             self._update_statuses(member)
#
#     def delete_member(self, context, member):
#         member = data_models.Member.from_dict(member)
#         driver = self._get_driver(member.pool.listener.loadbalancer.id)
#         driver.member.delete(member)
#
#     def create_healthmonitor(self, context, healthmonitor):
#         healthmonitor = data_models.HealthMonitor.from_dict(healthmonitor)
#         driver = self._get_driver(healthmonitor.pool.listener.loadbalancer.id)
#         try:
#             driver.healthmonitor.create(healthmonitor)
#         except Exception:
#             self._handle_failed_driver_call('create', healthmonitor,
#                                             driver.get_name())
#         else:
#             self._update_statuses(healthmonitor)
#
#     def update_healthmonitor(self, context, old_healthmonitor,
#                              healthmonitor):
#         healthmonitor = data_models.HealthMonitor.from_dict(healthmonitor)
#         old_healthmonitor = data_models.HealthMonitor.from_dict(
#             old_healthmonitor)
#         driver = self._get_driver(healthmonitor.pool.listener.loadbalancer.id)
#         try:
#             driver.healthmonitor.update(old_healthmonitor, healthmonitor)
#         except Exception:
#             self._handle_failed_driver_call('create', healthmonitor,
#                                             driver.get_name())
#         else:
#             self._update_statuses(healthmonitor)
#
#     def delete_healthmonitor(self, context, healthmonitor):
#         healthmonitor = data_models.HealthMonitor.from_dict(healthmonitor)
#         driver = self._get_driver(healthmonitor.pool.listener.loadbalancer.id)
#         driver.healthmonitor.delete(healthmonitor)

