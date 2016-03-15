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
from neutron_lbaas.db.loadbalancer import models
from gbpservice.nfp.config_agent.common import *
from gbpservice.nfp.config_agent import RestClientOverUnix as rc

LOG = logging.getLogger(__name__)


# TODO: Why lbaasv1 agent only implement create/delete method
class Lbv2Agent(loadbalancer_dbv2.LoadBalancerPluginDbv2):
    #  TODO: should we increment RPC_API_VERSION?
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
        body = prepare_request_data(name, kwargs, "loadbalancer")
        try:

            # TODO: by default path of rc.post prefix with nfp/v1/ .
            # What does v1 mean?
            resp, content = rc.post(
                'create_network_function_config', body=body)
        except rc.RestClientException as rce:
            LOG.error("create_%s -> request failed. Reason %s" % (
                name, rce))

    def _delete(self, context, tenant_id, name, **kwargs):
        db = self._context(context, tenant_id)
        context_dict = context.to_dict()
        context_dict.update({'service_info': db})
        kwargs.update({'context': context_dict})
        body = prepare_request_data(name, kwargs, "loadbalancer")
        try:
            resp, content = rc.post('delete_network_function_config',
                                    body=body, delete=True)
        except rc.RestClientException as rce:
            LOG.error("delete_%s -> request failed.Reason %s" % (
                name, rce))

    def create_loadbalancer(self, context, loadbalancer, allocate_vip=True):
        print("hit nfp/create_loadbalancer!")
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
    def create_l7policy(self, context, l7policy):
        self._post(
            context, l7policy['tenant_id'],
            'l7policy', l7policy=l7policy)

    def delete_l7policy(self, context, l7policy):
        self._delete(
            context, l7policy['tenant_id'],
            'l7policy', l7policy=l7policy)

    def create_l7policy_rule(self, context, rule, l7policy_id):
        self._post(
            context, rule['tenant_id'],
            'rule', rule=rule)

    def delete_l7policy_rule(self, context, rule):
        self._delete(
            context, rule['tenant_id'],
            'rule', rule=rule)

    def _context(self, context, tenant_id):
        if context.is_admin:
            tenant_id = context.tenant_id
        filters = {'tenant_id': [tenant_id]}
        db = self._get_lb_context(context, filters)
        db.update(self._get_core_context(context, filters))
        return db

    def _get_core_context(self, context, filters):
        args = {'context': context, 'filters': filters}
        core_plugin = self._core_plugin
        return {'subnets': core_plugin.get_subnets(**args),
                'ports': core_plugin.get_ports(**args)}

    def _get_lb_context(self, context, filters):
        args = {'context': context, 'filters': filters}
        db_data = super(Lbv2Agent, self)
        return {'loadbalancers': db_data.get_loadbalancers(**args),
                'listeners': db_data.get_listeners(**args),
                'pools': db_data.get_pools(**args),
                'pool_members': db_data.get_pool_members(**args),
                'healthmonitors': db_data.get_healthmonitors(**args),
                'l7policies': db_data.get_l7policies(**args),
                'l7policy_rules': db_data.get_l7policy_rules(**args)}

