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

import time

from neutron.common import log
from neutron.db import model_base
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants as pconst
from oslo.config import cfg
from oslo.serialization import jsonutils
import sqlalchemy as sa

from gbpservice.neutron.services.servicechain.plugins.ncp import (
                                                    exceptions as exc)
from gbpservice.neutron.services.servicechain.plugins.ncp import driver_base
from gbpservice.neutron.services.servicechain.plugins.ncp.node_drivers import (
                                openstack_heat_api_client as heat_api_client)

LOG = logging.getLogger(__name__)

service_chain_opts = [
    cfg.IntOpt('stack_action_wait_time',
               default=15,
               help=_("Seconds to wait for pending stack operation "
                      "to complete")),
    cfg.StrOpt('heat_uri',
               default='http://localhost:8004/v1',
               help=_("Heat API server address to instantiate services "
                      "specified in the service chain.")),
    cfg.StrOpt('exclude_pool_member_tag',
               default='ExcludePoolMember',
               help=_("Policy Targets created for the LB Pool Members should "
                      "have this tag in their description")),
]

cfg.CONF.register_opts(service_chain_opts, "servicechain")
EXCLUDE_POOL_MEMBER_TAG = cfg.CONF.servicechain.exclude_pool_member_tag
STACK_ACTION_WAIT_TIME = cfg.CONF.servicechain.stack_action_wait_time
STACK_ACTION_RETRY_WAIT = 5  # Retry after every 5 seconds


class ServiceNodeInstanceStack(model_base.BASEV2):
    """ServiceChainInstance stacks owned by the Node driver."""

    __tablename__ = 'node_instance_stacks'
    sc_instance_id = sa.Column(sa.String(36),
                               nullable=False, primary_key=True)
    sc_node_id = sa.Column(sa.String(36),
                           nullable=False, primary_key=True)
    stack_id = sa.Column(sa.String(36),
                         nullable=False, primary_key=True)


class InvalidServiceType(exc.NodeCompositionPluginBadRequest):
    message = _("The Template Node driver only supports the services "
                "Firewall and LB in a Service Chain")


class NodeVendorMismatch(exc.NodeCompositionPluginBadRequest):
    message = _("The reference driver only handles nodes which have service "
                "profile with vendor name %(vendor)s")


class HeatTemplateVersionNotSupported(exc.NodeCompositionPluginBadRequest):
    message = _("The Template Node driver only supports AWS and Hot template "
                "formats for service node config")


class ServiceResourceDefinitionsMissing(exc.NodeCompositionPluginBadRequest):
    message = _("The Service template does not have service resources defined")


class HeatResourceMissing(exc.NodeCompositionPluginBadRequest):
    message = _("The service template requires the Resource %(resource)s for "
                "service type %(servicetype)s")


class ProfileUpdateNotSupported(exc.NodeCompositionPluginBadRequest):
    message = _("The Template Node driver does not allow updating the "
                "service profile used by a Node")


class ServiceTypeUpdateNotSupported(exc.NodeCompositionPluginBadRequest):
    message = _("The Template Node driver does not allow updating the "
                "service type used by a Node")


class TemplateNodeDriver(driver_base.NodeDriverBase):

    sc_supported_type = [pconst.LOADBALANCER, pconst.FIREWALL]
    vendor_name = 'default'
    initialized = False
    required_heat_resources = {pconst.LOADBALANCER: [
                                            'OS::Neutron::LoadBalancer',
                                            'OS::Neutron::Pool'],
                               pconst.FIREWALL: [
                                            'OS::Neutron::Firewall',
                                            'OS::Neutron::FirewallPolicy']}

    @log.log
    def initialize(self, name):
        self.initialized = True
        self._name = name

    @log.log
    def get_plumbing_info(self, context):
        pass

    @log.log
    def validate_create(self, context):
        if context.current_node['service_profile_id'] is None:
            service_type = context.current_node['service_type']
            if service_type not in self.sc_supported_type:
                raise InvalidServiceType()
        else:
            if context.current_profile['vendor'] != self.vendor_name:
                raise NodeVendorMismatch(vendor=self.vendor_name)
            service_type = context.current_profile['service_type']
            if service_type not in self.sc_supported_type:
                raise InvalidServiceType()

        service_template = jsonutils.loads(context.current_node['config'])
        self._validate_service_config(service_template, service_type)
        return True

    @log.log
    def validate_update(self, context):
        if context.current_profile != context.original_profile:
            raise ProfileUpdateNotSupported()
        if (context.current_node['service_type'] !=
            context.original_node['service_type']):
            raise ServiceTypeUpdateNotSupported()
        else:
            service_type = (context.current_node['service_type'] or
                            context.current_profile['service_type'])
            service_template = jsonutils.loads(context.current_node['config'])
            self._validate_service_config(service_template, service_type)
        return True

    def _validate_service_config(self, service_template, service_type):
        if (not service_template.get('AWSTemplateFormatVersion') and
                not service_template.get('heat_template_version')):
                LOG.error(_("The Template Node driver supports only AWS and "
                            "Hot template formats for service node config"))
                raise HeatTemplateVersionNotSupported()
        is_template_aws_version = service_template.get(
                                        'AWSTemplateFormatVersion', False)
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        if not service_template.get(resources_key):
            LOG.error(_("The service template does not have any Resources "
                        "defined"))
            raise ServiceResourceDefinitionsMissing()

        for resource_name in self.required_heat_resources[service_type]:
            param_key = self._get_heat_resource_key(
                            service_template[resources_key],
                            is_template_aws_version,
                            resource_name)
            if not param_key:
                LOG.error(_("The service template requires the Resource "
                            "%(resource)s for service type %(servicetype)s "
                            "available resources: %(available)s"),
                          {'resource': resource_name,
                           'servicetype': service_type,
                           'available': service_template[resources_key]})
                raise HeatResourceMissing(resource=resource_name,
                                          servicetype=service_type)

    @log.log
    def create(self, context):
        heatclient = self._get_heat_client(context.plugin_context)

        stack_template, stack_params = self._fetch_template_and_params(context)

        stack_name = ("stack_" + context.instance['name'] +
                      context.current_node['name'] +
                      context.instance['id'][:8] +
                      context.current_node['id'][:8])
        # Heat does not accept space in stack name
        stack_name = stack_name.replace(" ", "")
        stack = heatclient.create(stack_name, stack_template, stack_params)

        self._insert_node_instance_stack_in_db(
            context.plugin_session, context.current_node['id'],
            context.instance['id'], stack['stack']['id'])

    @log.log
    def delete(self, context):
        stack_ids = self._get_node_instance_stacks(context.plugin_session,
                                                   context.current_node['id'],
                                                   context.instance['id'])
        heatclient = self._get_heat_client(context.plugin_context)

        for stack in stack_ids:
            heatclient.delete(stack.stack_id)
        for stack in stack_ids:
            self._wait_for_stack_operation_complete(
                                heatclient, stack.stack_id, 'delete')
        self._delete_node_instance_stack_in_db(context.plugin_session,
                                               context.current_node['id'],
                                               context.instance['id'])

    @log.log
    def update(self, context):
        heatclient = self._get_heat_client(context.plugin_context)

        stack_template, stack_params = self._fetch_template_and_params(context)

        stack_ids = self._get_node_instance_stacks(context.plugin_session,
                                                   context.current_node['id'],
                                                   context.instance['id'])
        for stack in stack_ids:
            self._wait_for_stack_operation_complete(
                                heatclient, stack.stack_id, 'update')
            heatclient.update(stack.stack_id, stack_template, stack_params)

    @log.log
    def update_policy_target_added(self, context, policy_target):
        if context.current_node['service_profile_id']:
            service_type = context.current_profile['service_type']
        else:
            service_type = context.current_node['service_type']

        if service_type != pconst.LOADBALANCER:
            return

        self.update(context)

    @log.log
    def update_policy_target_removed(self, context, policy_target):
        if context.current_node['service_profile_id']:
            service_type = context.current_profile['service_type']
        else:
            service_type = context.current_node['service_type']

        if service_type != pconst.LOADBALANCER:
            return

        self.update(context)

    @property
    def name(self):
        return self._name

    def _get_heat_client(self, plugin_context):
        return heat_api_client.HeatClient(
                                plugin_context,
                                cfg.CONF.servicechain.heat_uri)

    def _fetch_template_and_params(self, context):
        sc_instance = context.instance
        provider_ptg = context.provider
        # TODO(Magesh): Handle multiple subnets
        provider_ptg_subnet_id = provider_ptg['subnets'][0]
        consumer = context.consumer
        if context.current_node['service_profile_id']:
            service_type = context.current_profile['service_type']
        else:
            service_type = context.current_node['service_type']

        stack_template = context.current_node.get('config')
        stack_template = jsonutils.loads(stack_template)
        config_param_values = sc_instance.get('config_param_values', {})
        stack_params = {}

        if config_param_values:
            config_param_values = jsonutils.loads(config_param_values)

        is_template_aws_version = stack_template.get(
                                        'AWSTemplateFormatVersion', False)

        if service_type == pconst.LOADBALANCER:
            self._generate_pool_members(context, stack_template,
                                        config_param_values,
                                        provider_ptg,
                                        is_template_aws_version)
        else:
            provider_subnet = context.core_plugin.get_subnet(
                                context.plugin_context, provider_ptg_subnet_id)
            if context.is_consumer_external:
                # REVISIT(Magesh): Allowing the first destination which is 0/0
                # Validate and skip adding FW rule in case routes is not set
                es = context.gbp_plugin.get_external_segment(
                    context.plugin_context, consumer['external_segments'][0])
                consumer_cidrs = [x['destination']
                                  for x in es['external_routes']]
            else:
                consumer_subnet = context.core_plugin.get_subnet(
                    context._plugin_context, consumer['subnets'][0])
                consumer_cidrs = [consumer_subnet['cidr']]
            provider_cidr = provider_subnet['cidr']
            self._update_template_with_firewall_rules(
                    context, provider_ptg, provider_cidr, consumer_cidrs,
                    stack_template, is_template_aws_version)

        node_params = (stack_template.get('Parameters')
                       or stack_template.get('parameters')
                       or [])
        for parameter in node_params:
            if parameter == "Subnet":
                stack_params[parameter] = provider_ptg_subnet_id
            elif parameter in config_param_values:
                stack_params[parameter] = config_param_values[parameter]
        return (stack_template, stack_params)

    def _wait_for_stack_operation_complete(self, heatclient, stack_id, action):
        time_waited = 0
        while True:
            try:
                stack = heatclient.get(stack_id)
                if stack.stack_status == 'DELETE_FAILED':
                    heatclient.delete(stack_id)
                elif stack.stack_status not in ['UPDATE_IN_PROGRESS',
                                                'PENDING_DELETE']:
                    return
            except Exception:
                LOG.exception(_("Retrieving the stack %(stack)s failed."),
                              {'stack': stack_id})
                return
            else:
                time.sleep(STACK_ACTION_RETRY_WAIT)
                time_waited = time_waited + STACK_ACTION_RETRY_WAIT
                if time_waited >= STACK_ACTION_WAIT_TIME:
                    LOG.error(_("Stack %(action)s not completed within "
                                "%(wait)s seconds"),
                              {'action': action,
                               'wait': STACK_ACTION_WAIT_TIME,
                               'stack': stack_id})
                    return

    def _delete_node_instance_stack_in_db(self, session, sc_node_id,
                                          sc_instance_id):
        with session.begin(subtransactions=True):
            stacks = (session.query(ServiceNodeInstanceStack).
                      filter_by(sc_node_id=sc_node_id).
                      filter_by(sc_instance_id=sc_instance_id).
                      all())
            for stack in stacks:
                session.delete(stack)

    def _insert_node_instance_stack_in_db(self, session, sc_node_id,
                                          sc_instance_id, stack_id):
        with session.begin(subtransactions=True):
            chainstack = ServiceNodeInstanceStack(
                sc_node_id=sc_node_id,
                sc_instance_id=sc_instance_id,
                stack_id=stack_id)
            session.add(chainstack)

    def _get_node_instance_stacks(self, session, sc_node_id=None,
                                  sc_instance_id=None):
        with session.begin(subtransactions=True):
            query = session.query(ServiceNodeInstanceStack)
            if sc_node_id:
                query = query.filter_by(sc_node_id=sc_node_id)
            if sc_instance_id:
                query = query.filter_by(sc_instance_id=sc_instance_id)
            return query.all()

    def _update_template_with_firewall_rules(self, context, provider_ptg,
                                             provider_cidr, consumer_cidrs,
                                             stack_template,
                                             is_template_aws_version):
        resources_key = ('Resources' if is_template_aws_version
                         else 'resources')
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')
        ref_key = 'Ref' if is_template_aws_version else 'get_resource'

        rule_num = 1
        rule_list = []
        for consumer_cidr in consumer_cidrs:
            rule_name = "Rule_" + str(rule_num)
            rule_num = rule_num + 1
            stack_template[resources_key][rule_name] = (
                self._generate_firewall_rule(
                    is_template_aws_version, context.classifier["protocol"],
                    context.classifier["port_range"],
                    provider_cidr, consumer_cidr))
            rule_list.append({ref_key: rule_name})

        resource_name = 'OS::Neutron::FirewallPolicy'
        fw_policy_key = self._get_heat_resource_key(
                            stack_template[resources_key],
                            is_template_aws_version,
                            resource_name)

        stack_template[resources_key][fw_policy_key][properties_key][
            'firewall_rules'] = rule_list

    def _generate_firewall_rule(self, is_template_aws_version, protocol,
                                destination_port, destination_cidr,
                                source_cidr):
        type_key = 'Type' if is_template_aws_version else 'type'
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')
        return {type_key: "OS::Neutron::FirewallRule",
                properties_key: {
                    "protocol": protocol,
                    "enabled": True,
                    "destination_port": destination_port,
                    "action": "allow",
                    "destination_ip_address": destination_cidr,
                    "source_ip_address": source_cidr
                }
                }

    def _generate_pool_members(self, context, stack_template,
                               config_param_values, provider_ptg,
                               is_template_aws_version):
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        type_key = 'Type' if is_template_aws_version else 'type'
        member_ips = self._get_member_ips(context, provider_ptg)
        if not member_ips:
            return

        pool_res_name = None
        for resource in stack_template[resources_key]:
            if stack_template[resources_key][resource][type_key] == (
                                                    'OS::Neutron::Pool'):
                pool_res_name = resource
                break

        for member_ip in member_ips:
            member_name = 'mem-' + member_ip
            stack_template[resources_key][member_name] = (
                self._generate_pool_member_template(
                    context, is_template_aws_version,
                    pool_res_name, member_ip))

    def _generate_pool_member_template(self, context,
                                       is_template_aws_version,
                                       pool_res_name, member_ip):
        type_key = 'Type' if is_template_aws_version else 'type'
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')
        res_key = 'Ref' if is_template_aws_version else 'get_resource'
        return {type_key: "OS::Neutron::PoolMember",
                properties_key: {
                    "address": member_ip,
                    "admin_state_up": True,
                    "pool_id": {res_key: pool_res_name},
                    # FIXME(Magesh): Need to handle port range
                    "protocol_port": context.classifier["port_range"],
                    "weight": 1}}

    def _get_member_ips(self, context, ptg):
        member_addresses = []
        policy_target_groups = context.gbp_plugin.get_policy_targets(
                context.plugin_context,
                filters={'id': ptg.get("policy_targets")})
        for policy_target in policy_target_groups:
            if EXCLUDE_POOL_MEMBER_TAG not in policy_target['description']:
                port_id = policy_target.get("port_id")
                if port_id:
                    port = context.core_plugin.get_port(
                                        context._plugin_context, port_id)
                    ip = port.get('fixed_ips')[0].get("ip_address")
                    member_addresses.append(ip)
        return member_addresses

    def _get_heat_resource_key(self, template_resource_dict,
                               is_template_aws_version, resource_name):
        type_key = 'Type' if is_template_aws_version else 'type'
        for key in template_resource_dict:
            if template_resource_dict[key].get(type_key) == resource_name:
                return key