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

import pdb
import sys
from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2
from gbpservice.nfp.common import constants as const
from gbpservice.nfp.config_orchestrator.agent import topics as a_topics
from gbpservice.nfp.config_orchestrator.agent import common
from gbpservice.nfp.lib import transport
from oslo_log import helpers as log_helpers
import oslo_messaging as messaging
from oslo_log import log

LOG = log.getLogger(__name__)

# class ForkedPdb(pdb.Pdb):
#     """A Pdb subclass that may be used
#     from a forked multiprocessing child
#
#     """
#     def interaction(self, *args, **kwargs):
#         _stdin = sys.stdin
#         try:
#             sys.stdin = file('/dev/stdin')
#             pdb.Pdb.interaction(self, *args, **kwargs)
#         finally:
#             sys.stdin = _stdin

"""
RPC handler for Loadbalancer service
"""


class Lbv2Agent(loadbalancer_dbv2.LoadBalancerPluginDbv2):
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        self._conf = conf
        self._sc = sc
        super(Lbv2Agent, self).__init__()

    def _post(self, context, tenant_id, name, **kwargs):

        # Collecting db entry required by configurator.
        db = self._context(context, tenant_id)
        # Addind service_info to neutron context and sending
        # dictionary format to the configurator.
        context_dict = context.to_dict()
        context_dict.update({'service_info': db})
        kwargs.update({'context': context_dict})
        body = common.prepare_request_data(name, kwargs, "loadbalancerv2")
        transport.send_request_to_configurator(self._conf,
                                               context, body,
                                               "CREATE")

    def _delete(self, context, tenant_id, name, **kwargs):

        # Collecting db entry required by configurator.
        db = self._context(context, tenant_id)
        # Addind service_info to neutron context and sending
        # dictionary format to the configurator.
        context_dict = context.to_dict()
        context_dict.update({'service_info': db})
        kwargs.update({'context': context_dict})
        body = common.prepare_request_data(name, kwargs, "loadbalancerv2")
        transport.send_request_to_configurator(self._conf,
                                               context, body,
                                               "DELETE")

    #TODO(jiahao): Argument allocate_vip and delete_vip_port are not implememnted.
    @log_helpers.log_method_call
    def create_loadbalancer(self, context, loadbalancer, driver_name, allocate_vip=True):
        self._post(
            context, loadbalancer['tenant_id'],
            'loadbalancer', loadbalancer=loadbalancer, driver_name=driver_name)

    @log_helpers.log_method_call
    def delete_loadbalancer(self, context, loadbalancer, delete_vip_port=True):
        self._delete(
            context, loadbalancer['tenant_id'],
            'loadbalancer', loadbalancer=loadbalancer)

    @log_helpers.log_method_call
    def create_listener(self, context, listener):
        self._post(
            context, listener['tenant_id'],
            'listener', listener=listener)

    @log_helpers.log_method_call
    def delete_listener(self, context, listener):
        self._delete(
            context, listener['tenant_id'],
            'listener', listener=listener)

    @log_helpers.log_method_call
    def create_pool(self, context, pool):
        self._post(
            context, pool['tenant_id'],
            'pool', pool=pool)

    @log_helpers.log_method_call
    def delete_pool(self, context, pool):
        self._delete(
            context, pool['tenant_id'],
            'pool', pool=pool)

    @log_helpers.log_method_call
    def create_member(self, context, member):
        self._post(
            context, member['tenant_id'],
            'member', member=member)

    @log_helpers.log_method_call
    def delete_member(self, context, member):
        self._delete(
            context, member['tenant_id'],
            'member', member=member)

    @log_helpers.log_method_call
    def create_healthmonitor_on_pool(self, context, pool_id, healthmonitor):
        self._post(
            context, healthmonitor['tenant_id'],
            'healthmonitor', healthmonitor=healthmonitor)

    @log_helpers.log_method_call
    def create_healthmonitor(self, context, healthmonitor):
        self._post(
            context, healthmonitor['tenant_id'],
            'healthmonitor', healthmonitor=healthmonitor)

    @log_helpers.log_method_call
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
        core_context_dict = common.get_core_context(context,
                                                    filters,
                                                    self._conf.host)
        del core_context_dict['routers']
        return core_context_dict

    # TODO(jiahao): copy from v1 agent need to review
    # def _prepare_request_data(self, context, vip):
    #     request_data = None
    #     try:
    #         if vip is not None:
    #             vip_desc = ast.literal_eval(vip['description'])
    #             request_data = common.get_network_function_map(
    #                 context, vip_desc['network_function_id'])
    #             # Adding Service Type #
    #             request_data.update({"service_type": "loadbalancer",
    #                                  "vip_id": vip['id']})
    #     except Exception as e:
    #         LOG.error(e)
    #         return request_data
    #     return request_data

    @log_helpers.log_method_call
    def update_status(self, context, **kwargs):
        kwargs = kwargs['kwargs']
        rpcClient = transport.RPCClient(a_topics.LBV2_NFP_PLUGIN_TOPIC)
        rpcClient.cctxt = rpcClient.client.prepare(
            version=const.LOADBALANCER_RPC_API_VERSION)
        msg = ("NCO received LB's update_status API, making an update_status "
               "RPC call to plugin for %s: %s with status %s" % (
                   kwargs['obj_type'], kwargs['obj_id'],
                   kwargs['status']))
        LOG.info(msg)
        lb_p_status = const.ACTIVE
        lb_o_status = None
        obj_p_status = kwargs['provisioning_status']
        obj_o_status = kwargs['operating_status']
        if kwargs['obj_type'] == 'healthmonitor':
                obj_o_status = None

        if kwargs['obj_type'] != 'loadbalancer':
            rpcClient.cctxt.cast(context, 'update_status',
                                 obj_type=kwargs['obj_type'],
                                 obj_id=kwargs['obj_id'],
                                 provisioning_status=obj_p_status,
                                 operating_status=obj_o_status)

        rpcClient.cctxt.cast(context, 'update_status',
                             obj_type='loadbalancer',
                             obj_id=kwargs['root_lb_id'],
                             provisioning_status=lb_p_status,
                             operating_status=lb_o_status)

        # TODO(jiahao): copy from v1 agent need to review
        # if kwargs['obj_type'] == 'vip':
        #     vip = kwargs['vip']
        #     request_data = self._prepare_request_data(context, vip)
        #     LOG.info("%s : %s " % (request_data, vip))
        #     # Sending An Event for visiblity #
        #     data = {'resource': None,
        #             'context': context}
        #     data['resource'] = {'eventtype': 'SERVICE',
        #                         'eventid': 'SERVICE_CREATED',
        #                         'eventdata': request_data}
        #     ev = self._sc.new_event(id='SERVICE_CREATE',
        #                             key='SERVICE_CREATE', data=data)
        #     self._sc.post_event(ev)

    # TODO(jiahao): copy from v1 agent need to review
    # @log_helpers.log_method_call
    # def update_pool_stats(self, context, **kwargs):
    #     kwargs = kwargs['kwargs']
    #     rpcClient = transport.RPCClient(a_topics.LB_NFP_PLUGIN_TOPIC)
    #     rpcClient.cctxt = rpcClient.client.prepare(
    #         version=const.LOADBALANCER_RPC_API_VERSION)
    #     msg = ("NCO received LB's update_pool_stats API, making an "
    #            "update_pool_stats RPC call to plugin for updating"
    #            "pool: %s stats" % (kwargs['obj_id']))
    #     LOG.info(msg)
    #     rpcClient.cctxt.cast(context, 'update_pool_stats',
    #                          pool_id=kwargs['pool_id'],
    #                          stats=kwargs['stats'],
    #                          host=kwargs['host'])
    #
    # @log_helpers.log_method_call
    # def vip_deleted(self, context, **kwargs):
    #     LOG.info(kwargs)
    #     kwargs = kwargs['kwargs']
    #     vip = kwargs['vip']
    #     request_data = self._prepare_request_data(context, vip)
    #     LOG.info("%s : %s " % (request_data, vip))
    #     # Sending An Event for visiblity #
    #     data = {'resource': None,
    #             'context': context}
    #     data['resource'] = {'eventtype': 'SERVICE',
    #                         'eventid': 'SERVICE_DELETED',
    #                         'eventdata': request_data}
    #     ev = self._sc.new_event(id='SERVICE_DELETE',
    #                             key='SERVICE_DELETE', data=data)
    #     self._sc.post_event(ev)
