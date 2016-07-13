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

import ast
import copy

from gbpservice.nfp.config_orchestrator.common import common
from gbpservice.nfp.core import log as nfp_logging
from gbpservice.nfp.lib import transport

from neutron_fwaas.db.firewall import firewall_db

from oslo_log import helpers as log_helpers
import oslo_messaging as messaging

LOG = nfp_logging.getLogger(__name__)

"""
RPC handler for Firwrall service
"""


class FwAgent(firewall_db.Firewall_db_mixin):

    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        super(FwAgent, self).__init__()
        self._conf = conf
        self._sc = sc
        self._db_inst = super(FwAgent, self)

    def _get_firewalls(self, context, tenant_id,
                       firewall_policy_id, description):
        filters = {'tenant_id': [tenant_id],
                   'firewall_policy_id': [firewall_policy_id]}
        args = {'context': context, 'filters': filters}
        firewalls = self._db_inst.get_firewalls(**args)
        for firewall in firewalls:
            firewall['description'] = description
        return firewalls

    def _get_firewall_policies(self, context, tenant_id,
                               firewall_policy_id, description):
        filters = {'tenant_id': [tenant_id],
                   'id': [firewall_policy_id]}
        args = {'context': context, 'filters': filters}
        firewall_policies = self._db_inst.get_firewall_policies(**args)
        return firewall_policies

    def _get_firewall_rules(self, context, tenant_id,
                            firewall_policy_id, description):
        filters = {'tenant_id': [tenant_id],
                   'firewall_policy_id': [firewall_policy_id]}
        args = {'context': context, 'filters': filters}
        firewall_rules = self._db_inst.get_firewall_rules(**args)
        return firewall_rules

    def _get_firewall_context(self, **kwargs):
        firewalls = self._get_firewalls(**kwargs)
        firewall_policies = self._get_firewall_policies(**kwargs)
        firewall_rules = self._get_firewall_rules(**kwargs)
        return {'firewalls': firewalls,
                'firewall_policies': firewall_policies,
                'firewall_rules': firewall_rules}

    def _context(self, **kwargs):
        context = kwargs.get('context')
        if context.is_admin:
            kwargs['tenant_id'] = context.tenant_id
        db = self._get_firewall_context(**kwargs)
        return db

    def _prepare_resource_context_dicts(self, **kwargs):
        # Prepare context_dict
        context = kwargs.get('context')
        ctx_dict = context.to_dict()
        # Collecting db entry required by configurator.
        # Addind service_info to neutron context and sending
        # dictionary format to the configurator.
        db = self._context(**kwargs)
        rsrc_ctx_dict = copy.deepcopy(ctx_dict)
        rsrc_ctx_dict.update({'service_info': db})
        return ctx_dict, rsrc_ctx_dict

    def _data_wrapper(self, context, firewall, host, nf, reason):
        # Hardcoding the position for fetching data since we are owning
        # its positional change
        description = ast.literal_eval((nf['description'].split('\n'))[1])
        fw_mac = description['provider_ptg_info'][0]
        firewall.update({'description': str(description)})
        kwargs = {'context': context,
                  'firewall_policy_id': firewall[
                      'firewall_policy_id'],
                  'description': str(description),
                  'tenant_id': firewall['tenant_id']}

        ctx_dict, rsrc_ctx_dict = self._prepare_resource_context_dicts(
            **kwargs)
        nfp_context = {'network_function_id': nf['id'],
                       'neutron_context': ctx_dict,
                       'fw_mac': fw_mac,
                       'requester': 'nas_service',
                       'logging_context': nfp_logging.get_logging_context()}
        resource = resource_type = 'firewall'
        resource_data = {resource: firewall,
                         'host': host,
                         'neutron_context': rsrc_ctx_dict}
        body = common.prepare_request_data(nfp_context, resource,
                                           resource_type, resource_data,
                                           description['service_vendor'])
        return body

    def _fetch_nf_from_resource_desc(self, desc):
        desc_dict = ast.literal_eval(desc)
        nf_id = desc_dict['network_function_id']
        return nf_id

    @log_helpers.log_method_call
    def create_firewall(self, context, firewall, host):
        # Fetch nf_id from description of the resource
        nf_id = self._fetch_nf_from_resource_desc(firewall["description"])
        nfp_logging.store_logging_context(meta_id=nf_id)
        nf = common.get_network_function_details(context, nf_id)
        body = self._data_wrapper(context, firewall, host, nf, 'CREATE')
        transport.send_request_to_configurator(self._conf,
                                               context, body, "CREATE")
        nfp_logging.clear_logging_context()

    @log_helpers.log_method_call
    def delete_firewall(self, context, firewall, host):
        # Fetch nf_id from description of the resource
        nf_id = self._fetch_nf_from_resource_desc(firewall["description"])
        nfp_logging.store_logging_context(meta_id=nf_id)
        nf = common.get_network_function_details(context, nf_id)
        body = self._data_wrapper(context, firewall, host, nf, 'DELETE')
        transport.send_request_to_configurator(self._conf,
                                               context, body, "DELETE")
        nfp_logging.clear_logging_context()
