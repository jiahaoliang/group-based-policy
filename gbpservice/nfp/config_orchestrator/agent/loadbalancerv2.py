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
import ast
import copy

from gbpservice.nfp.common import constants as const
from gbpservice.nfp.config_orchestrator.agent import common
from gbpservice.nfp.config_orchestrator.agent import topics as a_topics
from gbpservice.nfp.core import common as nfp_common
from gbpservice.nfp.lib import transport

from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2

from oslo_log import helpers as log_helpers
from oslo_log import log as oslo_logging
import oslo_messaging as messaging

LOGGER = oslo_logging.getLogger(__name__)
LOG = nfp_common.log

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

    def _filter_service_info_with_resource(self, db):
        updated_db = {'subnets': [],
                      'ports': []}
        for lb in db['loadbalancers']:
            lb_port_id = lb['vip_port_id']
            lb_subnet_id = lb['vip_subnet_id']
            for subnet in db['subnets']:
                if subnet['id'] == lb_subnet_id:
                    updated_db['subnets'].append(subnet)
            for port in db['ports']:
                if port['id'] == lb_port_id:
                    updated_db['ports'].append(port)
        db.update(updated_db)
        return db

    def _to_api_dict(self, objs):
        ret_list = []
        for obj in objs:
            ret_list.append(obj.to_api_dict())
        return ret_list

    def _get_core_context(self, context, filters):
        core_context_dict = common.get_core_context(context,
                                                    filters,
                                                    self._conf.host)
        del core_context_dict['routers']
        return core_context_dict

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
        # TODO(jiahao): _get_lb_context() fails for flavor_id
        db = self._get_lb_context(context, filters)
        db.update(self._get_core_context(context, filters))
        return db

    def _prepare_resource_context_dicts(self, context, tenant_id):
        # Prepare context_dict
        ctx_dict = context.to_dict()
        # Collecting db entry required by configurator.
        # Addind service_info to neutron context and sending
        # dictionary format to the configurator.
        db = self._context(context, tenant_id)
        rsrc_ctx_dict = copy.deepcopy(ctx_dict)
        db = self._filter_service_info_with_resource(db)
        rsrc_ctx_dict.update({'service_info': db})
        return ctx_dict, rsrc_ctx_dict

    def _data_wrapper(self, context, tenant_id, name, reason, **kwargs):
        ctx_dict, rsrc_ctx_dict = self.\
            _prepare_resource_context_dicts(context, tenant_id)
        nfp_context = {'neutron_context': ctx_dict,
                       'requester': 'nas_service'}
        if name.lower() == 'loadbalancer':
            vip_desc = ast.literal_eval(kwargs['loadbalancer']['description'])
            nf_id = vip_desc['network_function_id']
            lb_id = kwargs['loadbalancer']['id']
            nfp_context.update({'network_function_id': nf_id,
                                'loadbalancer': lb_id})
        resource_type = 'loadbalancerv2'
        resource = name
        resource_data = {'neutron_context': rsrc_ctx_dict}
        resource_data.update(**kwargs)
        body = common.prepare_request_data(nfp_context, resource,
                                           resource_type, resource_data)
        return body

    def _post(self, context, tenant_id, name, **kwargs):
        body = self._data_wrapper(context, tenant_id, name,
                                  'CREATE', **kwargs)
        transport.send_request_to_configurator(self._conf,
                                               context, body, "CREATE")

    def _delete(self, context, tenant_id, name, **kwargs):
        body = self._data_wrapper(context, tenant_id, name,
                                  'DELETE', **kwargs)
        transport.send_request_to_configurator(self._conf,
                                               context, body, "DELETE")

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


class LoadbalancerV2Notifier(object):

    def __init__(self, conf, sc):
        self._sc = sc
        self._conf = conf

    # TODO(jiahao): copy from v1 agent need to review
    def _prepare_request_data(self, context, nf_id, lb_id, service_type):
        request_data = None
        try:
            request_data = common.get_network_function_map(
                context, nf_id)
            # Adding Service Type #
            # TODO(jiahao): is the key name "loadbalancer_id" correct?
            request_data.update({"service_type": service_type,
                                 "loadbalancer_id": lb_id})
        except Exception:
            return request_data
        return request_data

    # TODO(jiahao): copy from v1 agent need to review
    def _trigger_service_event(self, context, event_type, event_id,
                               request_data):
        event_data = {'resource': None,
                      'context': context.to_dict()}
        event_data['resource'] = {'eventtype': event_type,
                                  'eventid': event_id,
                                  'eventdata': request_data}
        ev = self._sc.new_event(id=event_id,
                                key=event_id, data=event_data)
        self._sc.post_event(ev)

    def update_status(self, context, notification_data):
        notification = notification_data['notification'][0]
        notification_info = notification_data['info']
        resource_data = notification['data']
        obj_type = resource_data['obj_type']
        obj_id = resource_data['obj_id']
        service_type = notification_info['service_type']

        rpcClient = transport.RPCClient(a_topics.LBV2_NFP_PLUGIN_TOPIC)
        rpcClient.cctxt = rpcClient.client.prepare(
            version=const.LOADBALANCERV2_RPC_API_VERSION)

        lb_p_status = const.ACTIVE
        lb_o_status = None
        obj_p_status = resource_data['provisioning_status']
        obj_o_status = resource_data['operating_status']

        msg = ("NCO received LB's update_status API, making an update_status "
               "RPC call to plugin for %s: %s with status %s" % (
                   obj_type, obj_id, obj_p_status))
        LOG(LOGGER, 'INFO', '%s' % (msg))

        if obj_type == 'healthmonitor':
                obj_o_status = None

        if obj_type != 'loadbalancer':
            rpcClient.cctxt.cast(context, 'update_status',
                                 obj_type=obj_type,
                                 obj_id=obj_id,
                                 provisioning_status=obj_p_status,
                                 operating_status=obj_o_status)
        else:
            lb_o_status = const.ONLINE
            if obj_p_status == const.ERROR:
                lb_p_status = const.ERROR
                lb_o_status = const.OFFLINE

        rpcClient.cctxt.cast(context, 'update_status',
                             obj_type='loadbalancer',
                             obj_id=resource_data['root_lb_id'],
                             provisioning_status=lb_p_status,
                             operating_status=lb_o_status)

        # TODO(jiahao): how to get lb_id?
        if obj_type.lower() == 'loadbalancer':
            nf_id = notification_info['context']['network_function_id']
            lb_id = notification_info['context']['loadbalancer']
            request_data = self._prepare_request_data(context, nf_id,
                                                      lb_id, service_type)
            LOG(LOGGER, 'INFO', "%s : %s " % (request_data, nf_id))

            # Sending An Event for visiblity
            self._trigger_service_event(context, 'SERVICE', 'SERVICE_CREATED',
                                        request_data)

    # TODO(jiahao): copy from v1 agent need to review
    # def update_pool_stats(self, context, notification_data):
    #     notification = notification_data['notification'][0]
    #     resource_data = notification['data']
    #     pool_id = resource_data['pool_id']
    #     stats = resource_data['stats']
    #     host = resource_data['host']
    #
    #     msg = ("NCO received LB's update_pool_stats API, making an "
    #            "update_pool_stats RPC call to plugin for updating"
    #            "pool: %s stats" % (pool_id))
    #     LOG(LOGGER, 'INFO', '%s' % (msg))
    #
    #     # RPC call to plugin to update stats of pool
    #     rpcClient = transport.RPCClient(a_topics.LB_NFP_PLUGIN_TOPIC)
    #     rpcClient.cctxt = rpcClient.client.prepare(
    #         version=const.LOADBALANCER_RPC_API_VERSION)
    #     rpcClient.cctxt.cast(context, 'update_pool_stats',
    #                          pool_id=pool_id,
    #                          stats=stats,
    #                          host=host)
    #
    # def vip_deleted(self, context, notification_data):
    #     notification_info = notification_data['info']
    #     nf_id = notification_info['context']['network_function_id']
    #     vip_id = notification_info['context']['vip_id']
    #     service_type = notification_info['service_type']
    #     request_data = self._prepare_request_data(context, nf_id,
    #                                               vip_id, service_type)
    #     LOG(LOGGER, 'INFO', "%s : %s " % (request_data, nf_id))
    #
    #     # Sending An Event for visiblity
    #     self._trigger_service_event(context, 'SERVICE', 'SERVICE_DELETED',
    #                                 request_data)