# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy
import time

from heatclient import exc as heat_exc
from keystoneclient import exceptions as k_exceptions
from keystoneclient.v3 import client as keyclientv3
from neutron.common import exceptions as n_exc
from neutron import manager
from neutron.plugins.common import constants as pconst
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import excutils
from oslo_utils._i18n import _
import yaml

from gbpservice.neutron.nsf.lifecycle_manager.openstack.heat_client\
    import HeatClient
from gbpservice.neutron.nsf.lifecycle_manager.openstack.openstack_driver\
    import GBPClient
from gbpservice.neutron.nsf.lifecycle_manager.openstack.openstack_driver\
    import KeystoneClient
from gbpservice.neutron.nsf.lifecycle_manager.openstack.openstack_driver\
    import NeutronClient
from gbpservice.neutron.services.grouppolicy.common import constants as gconst
from gbpservice.neutron.services.servicechain.plugins.ncp import plumber_base


HEAT_DRIVER_OPTS = [
    cfg.StrOpt('svc_management_ptg_name',
               default='svc_management_ptg',
               help=_("Name of the PTG that is associated with the "
                      "service management network")),
    cfg.StrOpt('remote_vpn_client_pool_cidr',
               default='192.168.254.0/24',
               help=_("CIDR pool for remote vpn clients")),
    cfg.StrOpt('heat_uri',
               default='http://localhost:8004/v1',
               help=_("Heat API server address to instantiate services "
                      "specified in the service chain.")),
    cfg.IntOpt('stack_action_wait_time',
               default=120,
               help=_("Seconds to wait for pending stack operation "
                      "to complete")),
    cfg.BoolOpt('is_service_admin_owned',
                help=_("Parameter to indicate whether the Service VM has to "
                       "to be owned by the Admin"),
                default=True),
    cfg.StrOpt('keystone_version',
               default='v3',
               help=_("Parameter to indicate version of keystone "
                       "used by heat_driver")),
]

cfg.CONF.register_opts(HEAT_DRIVER_OPTS,
                       "heat_driver")

SC_METADATA = ('{"sc_instance":"%s", "floating_ip": "%s", '
               '"provider_interface_mac": "%s", '
               '"standby_provider_interface_mac": "%s"}')
SVC_MGMT_PTG_NAME = (
    cfg.CONF.heat_driver.svc_management_ptg_name)

STACK_ACTION_WAIT_TIME = (
    cfg.CONF.heat_driver.stack_action_wait_time)
STACK_ACTION_RETRY_WAIT = 5  # Retry after every 5 seconds
APIC_OWNED_RES = 'apic_owned_res_'

LOG = logging.getLogger(__name__)


class ServiceInfoNotAvailableOnUpdate(n_exc.NeutronException):
    message = _("Service information is not available with Service Manager "
                "on node update")


class StackOperationFailedException(n_exc.NeutronException):
    message = _("Stack : %(stack_name)s %(operation)s failed for tenant : "
                "%(stack_owner)s ")


class StackOperationNotCompletedException(n_exc.NeutronException):
    message = _("Stack : %(stack_name)s %(operation)s did not complete in "
                "%(time)s seconds for tenant : %(stack_owner)s ")


class RequiredRoleNotCreated(n_exc.NeutronException):
    message = _("The role : %(role_name)s is not available in keystone")


class FloatingIPForVPNRemovedManually(n_exc.NeutronException):
    message = _("Floating IP for VPN Service has been disassociated Manually")


class NodeUpdateException(n_exc.NeutronException):
    message = _("Failed to configure node %(node)s of service chain "
                "instance %(instance_id)s of Tenant - %(tenant)s . "
                "%(msg)s ")


class NodeDBUpdateException(n_exc.NeutronException):
    message = _("Failed to Update DB with Stack details - %(msg)s")


class HeatDriver():
    SUPPORTED_SERVICE_TYPES = [pconst.LOADBALANCER, pconst.FIREWALL,
                               pconst.VPN
                               ]
    SUPPORTED_SERVICE_VENDOR_MAPPING = {pconst.LOADBALANCER: ["haproxy"],
                                        pconst.FIREWALL: ["vyos", "asav"],
                                        pconst.VPN: ["vyos", "asav"]
                                        }
    vendor_name = 'oneconvergence'
    required_heat_resources = {
        pconst.LOADBALANCER: ['OS::Neutron::LoadBalancer',
                              'OS::Neutron::Pool'],
        pconst.FIREWALL: ['OS::Neutron::Firewall',
                          'OS::Neutron::FirewallPolicy'],
        pconst.VPN: ['OS::Neutron::VPNService']

    }

    initialized = False

    def __init__(self):
        self._lbaas_plugin = None
        self.keystoneclient = KeystoneClient()
        self.gbp_client = GBPClient()
        self.neutron_client = NeutronClient()
        self.initialized = True
        #self._name = name
        self.resource_owner_tenant_id = None

    @property
    def resource_owner_tenant_id(self):
        if self.resource_owner_tenant_id:
            return self.resource_owner_tenant_id

        if cfg.CONF.heat_driver.is_service_admin_owned:
            self.resource_owner_tenant_id = self._resource_owner_tenant_id()
        else:
            self.resource_owner_tenant_id = None
        return self.resource_owner_tenant_id

    def lbaas_plugin(self):
        if self._lbaas_plugin:
            return self._lbaas_plugin
        self._lbaas_plugin = manager.NeutronManager.get_service_plugins().get(
            pconst.LOADBALANCER)
        return self._lbaas_plugin

    def _resource_owner_tenant_id(self):
        user, pwd, tenant_name, auth_url =\
            self.keystoneclient.get_keystone_creds()
        # keystoneclient = keyclient.Client(username=user, password=pwd,
        #                                  auth_url=auth_url)
        auth_token = self.keystoneclient.get_scoped_keystone_token(
            user, pwd, tenant_name)
        try:
            #tenant = keystoneclient.tenants.find(name=tenant)
            # return tenant.id
            tenant_id = self.keystoneclient.get_tenant_id(
                auth_token, tenant_name)
            return tenant_id
        except k_exceptions.NotFound:
            with excutils.save_and_reraise_exception(reraise=True):
                LOG.error(_('No tenant with name %s exists.'), tenant_name)
        except k_exceptions.NoUniqueMatch:
            with excutils.save_and_reraise_exception(reraise=True):
                LOG.error(
                    _('Multiple tenants matches found for %s'), tenant_name)

    def _get_resource_owner_context(self):
        #auth_token = self.keystoneclient.get_admin_token()
        if cfg.CONF.heat_driver.is_service_admin_owned:
            tenant_id = self.resource_owner_tenant_id
            user, pwd, tenant_name, auth_url =\
                self.keystoneclient.get_keystone_creds()
            # keystoneclient = keyclient.Client(username=user, password=pwd,
            #                                  auth_url=auth_url)
            # auth_token = keystoneclient.get_token(
            #    self.resource_owner_tenant_id)
            auth_token = self.keystoneclient.get_scoped_keystone_token(user,
                pwd, tenant_name, self.resource_owner_tenant_id)
        return auth_token, tenant_id

    def _get_v3_keystone_admin_client(self):
        """ Returns keystone v3 client with admin credentials
            Using this client one can perform CRUD operations over
            keystone resources.
        """
        keystone_conf = cfg.CONF.keystone_authtoken
        v3_auth_url = ('%s://%s:%s/%s/' % (
            keystone_conf.auth_protocol, keystone_conf.auth_host,
            keystone_conf.auth_port, cfg.CONF.heat_driver.keystone_version))
        v3client = keyclientv3.Client(
            username=keystone_conf.admin_user,
            password=keystone_conf.admin_password,
            domain_name="default",  # FIXME(Magesh): Make this config driven
            auth_url=v3_auth_url)
        return v3client

    def _get_role_by_name(self, v3client, name):
        role = v3client.roles.list(name=name)
        if role:
            return role[0]
        else:
            raise RequiredRoleNotCreated(role_name=name)

    def _assign_admin_user_to_project(self, project_id):
        v3client = self._get_v3_keystone_admin_client()
        keystone_conf = cfg.CONF.keystone_authtoken
        admin_id = v3client.users.find(name=keystone_conf.admin_user).id
        admin_role = self._get_role_by_name(v3client, "admin")
        v3client.roles.grant(admin_role.id, user=admin_id, project=project_id)
        heat_role = self._get_role_by_name(v3client, "heat_stack_owner")
        v3client.roles.grant(heat_role.id, user=admin_id, project=project_id)

    def keystone(self, user, pwd, tenant_name, tenant_id=None):
        if tenant_id:
            # return keyclient.Client(
            #    username=user, password=password,
            #    auth_url=auth_url, tenant_id=tenant_id)
            return self.keystoneclient.get_scoped_keystone_token(
                user, pwd, tenant_name, tenant_id)
        else:
            return self.keystoneclient.get_scoped_keystone_token(
                user, pwd, tenant_name)
            # return keyclient.Client(
            #    username=user, password=password,
            #    auth_url=auth_url, tenant_name=tenant)

    def _get_heat_client(self, resource_owner_tenant_id, tenant_id=None):
        user_tenant_id = tenant_id or resource_owner_tenant_id
        # self._assign_admin_user_to_project(user_tenant_id)
        # admin_token = self.keystone(tenant_id=user_tenant_id).get_token(
        #        user_tenant_id)
        user, password, tenant, auth_url =\
            self.keystoneclient.get_keystone_creds()
        admin_token = self.keystone(
            user, password, tenant, tenant_id=user_tenant_id)

        timeout_mins, timeout_seconds = divmod(STACK_ACTION_WAIT_TIME, 60)
        if timeout_seconds:
            timeout_mins = timeout_mins + 1
        return HeatClient(
            user,
            user_tenant_id,
            cfg.CONF.heat_driver.heat_uri,
            password,
            auth_token=admin_token,
            timeout_mins=timeout_mins)

    def _get_tenant_context(self, tenant_id):
        # tenant_token = self.keystone(tenant_id=tenant_id).get_token(
        #        tenant_id)
        user, password, tenant, auth_url =\
            self.keystoneclient.get_keystone_creds()

        auth_token = self.keystone(user, password,
                                   tenant, tenant_id=tenant_id)
        return auth_token, tenant_id

    def _create_pt(self, auth_token, provider_tenant_id,
                   ptg_id, name, port_id=None):
        return self.gbp_client.create_policy_target(
            auth_token, provider_tenant_id, ptg_id, name, port_id)

    def _create_policy_target_for_vip(self, auth_token,
                                      provider_tenant_id, provider):
        provider_subnet = None
        provider_l2p_subnets = self.neutron_client.list_subnets(
            auth_token,
            filters={'id': provider['subnets']})
        for subnet in provider_l2p_subnets:
            if not subnet['name'].startswith(APIC_OWNED_RES):
                provider_subnet = subnet
                break
        if provider_subnet:
            lb_pool_ids = self.lbaas_plugin.get_pools(
                auth_token, provider_tenant_id,
                filters={'subnet_id': [provider_subnet['id']]})
            if lb_pool_ids and lb_pool_ids[0]['vip_id']:
                lb_vip = self.lbaas_plugin.get_vip(
                    auth_token, provider_tenant_id, lb_pool_ids[0]['vip_id'])
                self._create_pt(auth_token, provider_tenant_id, provider['id'],
                                "service_target_vip_pt",
                                port_id=lb_vip['port_id'])

    def _is_service_target(self, policy_target):
        if policy_target['name'] and (policy_target['name'].startswith(
                plumber_base.SERVICE_TARGET_NAME_PREFIX) or
                policy_target['name'].startswith('tscp_endpoint_service') or
                policy_target['name'].startswith('vip_pt')):
            return True
        else:
            return False

    def _get_member_ips(self, auth_token, ptg):
        member_addresses = []
        policy_targets = self.gbp_client.get_policy_targets(
            auth_token,
            filters={'id': ptg.get("policy_targets")})
        for policy_target in policy_targets:
            if not self._is_service_target(policy_target):
                port_id = policy_target.get("port_id")
                if port_id:
                    port = self.neutron_client.get_port(
                        auth_token, port_id)['port']
                    ip_address = port.get('fixed_ips')[0].get("ip_address")
                    member_addresses.append(ip_address)
        return member_addresses

    def _generate_lb_member_template(self, is_template_aws_version,
                                     pool_res_name, member_ip, stack_template):
        type_key = 'Type' if is_template_aws_version else 'type'
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        res_key = 'Ref' if is_template_aws_version else 'get_resource'

        lbaas_pool_key = self._get_heat_resource_key(
            stack_template[resources_key],
            is_template_aws_version,
            "OS::Neutron::Pool")
        lbaas_vip_key = self._get_heat_resource_key(
            stack_template[resources_key],
            is_template_aws_version,
            "OS::Neutron::LoadBalancer")
        vip_port = stack_template[resources_key][lbaas_pool_key][
            properties_key]['vip']['protocol_port']
        member_port = stack_template[resources_key][lbaas_vip_key][
            properties_key].get('protocol_port')
        protocol_port = member_port if member_port else vip_port

        return {type_key: "OS::Neutron::PoolMember",
                properties_key: {
                    "address": member_ip,
                    "admin_state_up": True,
                    "pool_id": {res_key: pool_res_name},
                    "protocol_port": protocol_port,
                    "weight": 1}}

    def _modify_lb_resources_name(self, stack_template, provider_ptg,
                                  is_template_aws_version):
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        type_key = 'Type' if is_template_aws_version else 'type'
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')

        for resource in stack_template[resources_key]:
            if stack_template[resources_key][resource][type_key] == (
                    'OS::Neutron::Pool'):
                # Include provider name in Pool, VIP name.
                ptg_name = '-' + provider_ptg['name']
                stack_template[resources_key][resource][
                    properties_key]['name'] += ptg_name
                stack_template[resources_key][resource][
                    properties_key]['vip']['name'] += ptg_name

    def _generate_pool_members(self, auth_token, stack_template,
                               config_param_values, provider_ptg,
                               is_template_aws_version):
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        self._modify_lb_resources_name(
            stack_template, provider_ptg, is_template_aws_version)
        member_ips = self._get_member_ips(auth_token, provider_ptg)
        if not member_ips:
            return
        pool_res_name = self._get_heat_resource_key(
            stack_template[resources_key],
            is_template_aws_version,
            "OS::Neutron::Pool")
        for member_ip in member_ips:
            member_name = 'mem-' + member_ip
            stack_template[resources_key][member_name] = (
                self._generate_lb_member_template(
                    is_template_aws_version, pool_res_name,
                    member_ip, stack_template))

    def _get_consumers_for_chain(self, auth_token, provider):
        filters = {'id': provider['provided_policy_rule_sets']}
        provided_prs = self.gbp_client.get_policy_rule_sets(
            auth_token, filters=filters)
        redirect_prs = None
        for prs in provided_prs:
            filters = {'id': prs['policy_rules']}
            policy_rules = self.gbp_client.get_policy_rules(
                auth_token, filters=filters)
            for policy_rule in policy_rules:
                filters = {'id': policy_rule['policy_actions'],
                           'action_type': [gconst.GP_ACTION_REDIRECT]}
                policy_actions = self.gbp_client.get_policy_actions(
                    auth_token, filters=filters)
                if policy_actions:
                    redirect_prs = prs
                    break

        if not redirect_prs:
            raise
        return (redirect_prs['consuming_policy_target_groups'],
                redirect_prs['consuming_external_policies'])

    def _append_firewall_rule(self, stack_template, provider_cidr,
                              consumer_cidr, fw_template_properties,
                              consumer_id):
        resources_key = fw_template_properties['resources_key']
        properties_key = fw_template_properties['properties_key']
        fw_rule_keys = fw_template_properties['fw_rule_keys']
        rule_name = "%s_%s" % ("node_driver_rule", consumer_id[:16])
        fw_policy_key = fw_template_properties['fw_policy_key']
        i = 1
        for fw_rule_key in fw_rule_keys:
            fw_rule_name = (rule_name + '_' + str(i))
            stack_template[resources_key][fw_rule_name] = (
                copy.deepcopy(stack_template[resources_key][fw_rule_key]))
            stack_template[resources_key][fw_rule_name][
                properties_key]['destination_ip_address'] = provider_cidr
            # Use user provided Source for N-S
            if consumer_cidr != "0.0.0.0/0":
                stack_template[resources_key][fw_rule_name][
                    properties_key]['source_ip_address'] = consumer_cidr

            if stack_template[resources_key][fw_policy_key][
                    properties_key].get('firewall_rules'):
                stack_template[resources_key][fw_policy_key][
                    properties_key]['firewall_rules'].append({
                        'get_resource': fw_rule_name})
            i += 1

    def _get_heat_resource_key(self, template_resource_dict,
                               is_template_aws_version, resource_name):
        type_key = 'Type' if is_template_aws_version else 'type'
        for key in template_resource_dict:
            if template_resource_dict[key].get(type_key) == resource_name:
                return key

    def _get_all_heat_resource_keys(self, template_resource_dict,
                                    is_template_aws_version, resource_name):
        type_key = 'Type' if is_template_aws_version else 'type'
        resource_keys = []
        for key in template_resource_dict:
            if template_resource_dict[key].get(type_key) == resource_name:
                resource_keys.append(key)
        return resource_keys

    def _update_firewall_template(self, auth_token, provider, stack_template):
        consumer_ptgs, consumer_eps = self._get_consumers_for_chain(
            auth_token, provider)
        is_template_aws_version = stack_template.get(
            'AWSTemplateFormatVersion', False)
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')
        fw_rule_keys = self._get_all_heat_resource_keys(
            stack_template[resources_key], is_template_aws_version,
            'OS::Neutron::FirewallRule')
        fw_policy_key = self._get_all_heat_resource_keys(
            stack_template['resources'], is_template_aws_version,
            'OS::Neutron::FirewallPolicy')[0]

        if consumer_ptgs:
            provider_cidr = None
            filters = {'id': consumer_ptgs}
            consumer_ptgs_details = self.gbp_client.get_policy_target_groups(
                auth_token, filters)
            provider_l2p_subnets = self.neutron_client.list_subnets(
                auth_token,
                filters={'id': provider['subnets']})
            for subnet in provider_l2p_subnets:
                if not subnet['name'].startswith(APIC_OWNED_RES):
                    provider_cidr = subnet['cidr']
                    break
            if not provider_cidr:
                raise  # TODO(Magesh): Raise proper exception class

            fw_template_properties = dict(
                resources_key=resources_key, properties_key=properties_key,
                is_template_aws_version=is_template_aws_version,
                fw_rule_keys=fw_rule_keys,
                fw_policy_key=fw_policy_key)

            # Revisit(Magesh): What is the name updated below ?? FW or Rule?
            # This seems to have no effect in UTs
            for consumer in consumer_ptgs_details:
                if consumer['proxied_group_id']:
                    continue
                fw_template_properties.update({'name': consumer['id'][:3]})
                for subnet_id in consumer['subnets']:
                    subnet = self.neutron_client.get_subnet(
                        auth_token, subnet_id)['subnet']
                    if subnet['name'].startswith(APIC_OWNED_RES):
                        continue

                    consumer_cidr = subnet['cidr']
                    self._append_firewall_rule(
                        stack_template, provider_cidr, consumer_cidr,
                        fw_template_properties, consumer['id'])

            filters = {'id': consumer_eps}
            consumer_eps_details = self.gbp_client.get_external_policies(
                auth_token, filters)
            for consumer_ep in consumer_eps_details:
                fw_template_properties.update({'name': consumer_ep['id'][:3]})
                self._append_firewall_rule(stack_template, provider_cidr,
                                           "0.0.0.0/0", fw_template_properties,
                                           consumer_ep['id'])

        for rule_key in fw_rule_keys:
            del stack_template[resources_key][rule_key]
            stack_template[resources_key][fw_policy_key][
                properties_key]['firewall_rules'].remove(
                    {'get_resource': rule_key})

        return stack_template

    def _modify_fw_resources_name(self, stack_template, provider_ptg,
                                  is_template_aws_version):
        resources_key = 'Resources' if is_template_aws_version else 'resources'
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')
        resource_name = 'OS::Neutron::FirewallPolicy'
        fw_policy_key = self._get_heat_resource_key(
            stack_template[resources_key],
            is_template_aws_version,
            resource_name)
        fw_resource_name = 'OS::Neutron::Firewall'
        fw_key = self._get_heat_resource_key(
            stack_template[resources_key],
            is_template_aws_version,
            fw_resource_name)
        # Include provider name in firewall, firewall policy.
        ptg_name = '-' + provider_ptg['name']
        stack_template[resources_key][fw_policy_key][
            properties_key]['name'] += ptg_name
        stack_template[resources_key][fw_key][
            properties_key]['name'] += ptg_name

    def _get_rvpn_l3_policy(self, auth_token, provider, node_update):
        # For remote vpn - we need to create a implicit l3 policy
        # for client pool cidr, to avoid this cidr being reused.
        # Check for this tenant if this l3 policy is defined.
        # 1) If yes, get the cidr
        # 2) Else Create one for this tenant with the user provided cidr
        rvpn_l3policy_filter = {
            'tenant_id': [provider['tenant_id']],
            'name': ["remote-vpn-client-pool-cidr-l3policy"]}
        rvpn_l3_policy = self.gbp_client.get_l3_policies(
            auth_token,
            rvpn_l3policy_filter)

        if node_update and not rvpn_l3_policy:
            raise

        if not rvpn_l3_policy:
            remote_vpn_client_pool_cidr = (
                cfg.CONF.heat_driver.
                remote_vpn_client_pool_cidr)
            rvpn_l3_policy = {
                'l3_policy': {
                    'name': "remote-vpn-client-pool-cidr-l3policy",
                    'description': ("L3 Policy for remote vpn "
                                    "client pool cidr"),
                    'ip_pool': remote_vpn_client_pool_cidr,
                    'ip_version': 4,
                    'subnet_prefix_length': 24,
                    'proxy_ip_pool': remote_vpn_client_pool_cidr,
                    'proxy_subnet_prefix_length': 24,
                    'external_segments': {},
                    'tenant_id': provider['tenant_id']}}
            rvpn_l3_policy = self.gbp_client.create_l3_policy(
                auth_token, rvpn_l3_policy)
        else:
            rvpn_l3_policy = rvpn_l3_policy[0]
        return rvpn_l3_policy

    def _get_management_gw_ip(self, auth_token):
        filters = {'name': [SVC_MGMT_PTG_NAME]}
        svc_mgmt_ptgs = self.gbp_client.get_policy_target_groups(
            auth_token, filters)
        if not svc_mgmt_ptgs:
            LOG.error(_("Service Management Group is not created by Admin"))
            raise Exception()
        else:
            mgmt_subnet_id = svc_mgmt_ptgs[0]['subnets'][0]
            mgmt_subnet = self.neutron_client.get_subnet(
                auth_token, mgmt_subnet_id)['subnet']
            mgmt_gw_ip = mgmt_subnet['gateway_ip']
            return mgmt_gw_ip

    def _get_site_conn_keys(self, template_resource_dict,
                            is_template_aws_version, resource_name):
        keys = []
        type_key = 'Type' if is_template_aws_version else 'type'
        for key in template_resource_dict:
            if template_resource_dict[key].get(type_key) == resource_name:
                keys.append(key)
        return keys

    def _update_node_config(self, auth_token, tenant_id, service_profile,
                            service_chain_node, service_chain_instance,
                            provider, consumer_port,
                            provider_port, update=False, mgmt_ip=None):
        provider_cidr = provider_subnet = None
        provider_l2p_subnets = self.neutron_client.list_subnets(
            auth_token, filters={'id': provider['subnets']})
        for subnet in provider_l2p_subnets:
            if not subnet['name'].startswith(APIC_OWNED_RES):
                provider_cidr = subnet['cidr']
                provider_subnet = subnet
                break
        if not provider_cidr:
            raise  # Raise proper exception object
        service_type = service_profile['service_type']
        service_vendor = service_profile['service_flavor']

        stack_template = service_chain_node.get('config')
        stack_template = (jsonutils.loads(stack_template) if
                          stack_template.startswith('{') else
                          yaml.load(stack_template))
        config_param_values = service_chain_instance.get(
            'config_param_values', '{}')
        stack_params = {}
        config_param_values = jsonutils.loads(config_param_values)

        is_template_aws_version = stack_template.get(
            'AWSTemplateFormatVersion', False)
        resources_key = ('Resources' if is_template_aws_version
                         else 'resources')
        parameters_key = ('Parameters' if is_template_aws_version
                          else 'parameters')
        properties_key = ('Properties' if is_template_aws_version
                          else 'properties')

        # FIXME(Magesh): Adapt to the new model with HA
        # Is this okay just using the first entry
        provider_port_mac = provider_port['mac_address']
        standby_provider_port_mac = None

        provider_cidr = self.neutron_client.get_subnet(
            auth_token, provider_port['fixed_ips'][0][
                'subnet_id'])['subnet']['cidr']
        service_vendor = service_profile['service_flavor']
        if service_type == pconst.LOADBALANCER:
            self._generate_pool_members(
                auth_token, stack_template, config_param_values,
                provider, is_template_aws_version)
            config_param_values['Subnet'] = provider_subnet['id']
            config_param_values['service_chain_metadata'] = (
                SC_METADATA % (service_chain_instance['id'],
                               mgmt_ip,
                               provider_port_mac,
                               standby_provider_port_mac))
        elif service_type == pconst.FIREWALL:
            stack_template = self._update_firewall_template(
                auth_token, provider, stack_template)
            self._modify_fw_resources_name(
                stack_template, provider, is_template_aws_version)
            firewall_desc = {'vm_management_ip': mgmt_ip,
                             'provider_ptg_info': [provider_port_mac],
                             'provider_cidr': provider_cidr,
                             'service_vendor': service_vendor}

            fw_key = self._get_heat_resource_key(
                stack_template[resources_key],
                is_template_aws_version,
                'OS::Neutron::Firewall')
            stack_template[resources_key][fw_key][properties_key][
                'description'] = str(firewall_desc)
        elif service_type == pconst.VPN:
            rvpn_l3_policy = self._get_rvpn_l3_policy(auth_token, update)
            config_param_values['ClientAddressPoolCidr'] = rvpn_l3_policy[
                'ip_pool']
            config_param_values['Subnet'] = (
                consumer_port['fixed_ips'][0]['subnet_id']
                if consumer_port else None)
            l2p = self.gbp_client.get_l2_policy(
                auth_token, provider['l2_policy_id'])
            l3p = self.gbp_client.get_l3_policy(
                auth_token, l2p['l3_policy_id'])
            config_param_values['RouterId'] = l3p['routers'][0]
            stitching_subnet = self.neutron_client.get_subnet(
                auth_token,
                consumer_port['fixed_ips'][0]['subnet_id'])['subnet']
            stitching_cidr = stitching_subnet['cidr']
            mgmt_gw_ip = self._get_management_gw_ip(auth_token)

            if not update:
                services_nsp = self.gbp_client.get_network_service_policies(
                    auth_token,
                    filters={'name': ['oneconvergence_services_nsp']})
                if not services_nsp:
                    fip_nsp = {
                        'network_service_policy': {
                            'name': 'oneconvergence_services_nsp',
                            'description': 'oneconvergence_implicit_resource',
                            'shared': False,
                            'tenant_id': tenant_id,
                            'network_service_params': [
                                {"type": "ip_pool", "value": "nat_pool",
                                 "name": "vpn_svc_external_access"}]
                        }
                    }
                    nsp = self.gbp_client.create_network_service_policy(
                        auth_token, fip_nsp)
                else:
                    nsp = services_nsp[0]
                stitching_pts = self.gbp_client.get_policy_targets(
                    auth_token,
                    filters={'port_id': [consumer_port['id']]})
                if not stitching_pts:
                    LOG.error(_("Policy target is not created for the "
                                "stitching port"))
                    raise Exception()
                stitching_ptg_id = stitching_pts[0]['policy_target_group_id']
                self.gbp_client.update_policy_target_group(
                    auth_token, stitching_ptg_id,
                    {'policy_target_group': {
                        'network_service_policy_id': nsp['id']}})
            #filters = {'port_id': [consumer_port['id']]}
            # floatingips = self.neutron_client.get_floating_ips(
            #    auth_token, filters=filters)
            floatingips = self.neutron_client.get_floating_ips(
                auth_token, consumer_port['id'])  # Need to test
            if not floatingips:
                raise FloatingIPForVPNRemovedManually()
            stitching_port_fip = floatingips[0]['floating_ip_address']
            desc = ('fip=' + mgmt_ip +
                    ";tunnel_local_cidr=" +
                    provider_cidr + ";user_access_ip=" +
                    stitching_port_fip + ";fixed_ip=" +
                    consumer_port['fixed_ips'][0]['ip_address'] +
                    ';service_vendor=' + service_vendor +
                    ';stitching_cidr=' + stitching_cidr +
                    ';stitching_gateway=' + stitching_subnet['gateway_ip'] +
                    ';mgmt_gw_ip=' + mgmt_gw_ip)
            stack_params['ServiceDescription'] = desc
            siteconn_keys = self._get_site_conn_keys(
                stack_template[resources_key],
                is_template_aws_version,
                'OS::Neutron::IPsecSiteConnection')
            for siteconn_key in siteconn_keys:
                stack_template[resources_key][siteconn_key][properties_key][
                    'description'] = desc

        for parameter in stack_template.get(parameters_key) or []:
            if parameter in config_param_values:
                stack_params[parameter] = config_param_values[parameter]

        LOG.info(_('Final stack_template : %(stack_data)s, '
                 'stack_params : %(params)s') %
                 {'stack_data': stack_template, 'params': stack_params})
        return (stack_template, stack_params)

    def _wait_for_stack_operation_complete(self, heatclient, stack_id, action,
                                           ignore_error=False):
        time_waited = 0
        operation_failed = False
        timeout_mins, timeout_seconds = divmod(STACK_ACTION_WAIT_TIME, 60)
        if timeout_seconds:
            timeout_mins = timeout_mins + 1
        # Heat timeout is in order of minutes. Allow Node driver to wait a
        # little longer than heat timeout
        wait_timeout = timeout_mins * 60 + 30
        while True:
            try:
                stack = heatclient.get(stack_id)
                if stack.stack_status == 'DELETE_FAILED':
                    heatclient.delete(stack_id)
                elif stack.stack_status == 'CREATE_COMPLETE':
                    return
                elif stack.stack_status == 'DELETE_COMPLETE':
                    LOG.info(_("Stack %(stack)s is deleted"),
                             {'stack': stack_id})
                    if action == "delete":
                        return
                    else:
                        operation_failed = True
                elif stack.stack_status == 'CREATE_FAILED':
                    operation_failed = True
                elif stack.stack_status == 'UPDATE_FAILED':
                    operation_failed = True
                elif stack.stack_status not in [
                        'UPDATE_IN_PROGRESS', 'CREATE_IN_PROGRESS',
                        'DELETE_IN_PROGRESS']:
                    return
            except heat_exc.HTTPNotFound:
                LOG.warn(_("Stack %(stack)s created by service chain driver "
                           "is not found while waiting for %(action)s to "
                           "complete"),
                         {'stack': stack_id, 'action': action})
                if action == "create" or action == "update":
                    operation_failed = True
                else:
                    return
            except Exception:
                LOG.exception(_("Retrieving the stack %(stack)s failed."),
                              {'stack': stack_id})
                if action == "create" or action == "update":
                    operation_failed = True
                else:
                    return

            if operation_failed:
                if ignore_error:
                    return
                else:
                    LOG.error(_("Stack %(stack_name)s %(action)s failed for "
                                "tenant %(stack_owner)s"),
                              {'stack_name': stack.stack_name,
                               'stack_owner': stack.stack_owner,
                               'action': action})
                    raise StackOperationFailedException(
                        stack_name=stack.stack_name, operation=action,
                        stack_owner=stack.stack_owner)
            else:
                time.sleep(STACK_ACTION_RETRY_WAIT)
                time_waited = time_waited + STACK_ACTION_RETRY_WAIT
                if time_waited >= wait_timeout:
                    LOG.error(_("Stack %(action)s not completed within "
                                "%(wait)s seconds"),
                              {'action': action,
                               'wait': wait_timeout,
                               'stack': stack_id})
                    # Some times, a second delete request succeeds in cleaning
                    # up the stack when the first request is stuck forever in
                    # Pending state
                    if action == 'delete':
                        try:
                            heatclient.delete(stack_id)
                        except Exception:
                            pass
                        return
                    else:
                        raise StackOperationNotCompletedException(
                            stack_name=stack.stack_name, operation=action,
                            time=wait_timeout,
                            stack_owner=stack.stack_owner)

    def is_config_complete(self, stack_id):
        success_status = "COMPLETED"
        failure_status = "ERROR"
        intermediate_status = "IN_PROGRESS"
        auth_token, resource_owner_tenant_id =\
            self._get_resource_owner_context()
        heatclient = self._get_heat_client(resource_owner_tenant_id)

        try:
            stack = heatclient.get(stack_id)
            if stack.stack_status == 'DELETE_FAILED':
                return failure_status
            elif stack.stack_status == 'CREATE_COMPLETE':
                return success_status
            elif stack.stack_status == 'DELETE_COMPLETE':
                LOG.info(_("Stack %(stack)s is deleted"),
                         {'stack': stack_id})
                return failure_status
            elif stack.stack_status == 'CREATE_FAILED':
                return failure_status
            elif stack.stack_status == 'UPDATE_FAILED':
                return failure_status
            elif stack.stack_status not in [
                    'UPDATE_IN_PROGRESS', 'CREATE_IN_PROGRESS',
                    'DELETE_IN_PROGRESS']:
                return intermediate_status
        except Exception:
            LOG.exception(_("Retrieving the stack %(stack)s failed."),
                          {'stack': stack_id})
            return failure_status

    def is_config_delete_complete(self, stack_id):
        success_status = "COMPLETED"
        failure_status = "ERROR"
        intermediate_status = "IN_PROGRESS"
        auth_token, resource_owner_tenant_id =\
            self._get_resource_owner_context()
        heatclient = self._get_heat_client(resource_owner_tenant_id)

        try:
            stack = heatclient.get(stack_id)
            if stack.stack_status == 'DELETE_FAILED':
                return failure_status
            elif stack.stack_status == 'CREATE_COMPLETE':
                return failure_status
            elif stack.stack_status == 'DELETE_COMPLETE':
                LOG.info(_("Stack %(stack)s is deleted"),
                         {'stack': stack_id})
                return success_status
            elif stack.stack_status == 'CREATE_FAILED':
                return failure_status
            elif stack.stack_status == 'UPDATE_FAILED':
                return failure_status
            elif stack.stack_status not in [
                    'UPDATE_IN_PROGRESS', 'CREATE_IN_PROGRESS',
                    'DELETE_IN_PROGRESS']:
                return intermediate_status
        except Exception:
            LOG.exception(_("Retrieving the stack %(stack)s failed."),
                          {'stack': stack_id})
            return failure_status

    def apply_user_config(self, service_details):
        service_profile = service_details['service_profile']
        service_chain_node = service_details['servicechain_node']
        service_chain_instance = service_details['servicechain_instance']
        provider = service_details['policy_target_group']
        consumer_port = service_details['consumer_port']
        provider_port = service_details['provider_port']
        mgmt_ip = service_details['mgmt_ip']

        auth_token, resource_owner_tenant_id =\
            self._get_resource_owner_context()
        provider_tenant_id = provider['tenant_id']
        heatclient = self._get_heat_client(resource_owner_tenant_id,
                                           tenant_id=provider_tenant_id)
        stack_name = ("stack_" + service_chain_instance['name'] +
                      service_chain_node['name'] +
                      service_chain_instance['id'][:8] +
                      service_chain_node['id'][:8] + '-' +
                      time.strftime("%Y%m%d%H%M%S"))
        # Heat does not accept space in stack name
        stack_name = stack_name.replace(" ", "")
        stack_template, stack_params = self._update_node_config(
            auth_token, provider_tenant_id, service_profile,
            service_chain_node, service_chain_instance, provider,
            consumer_port, provider_port, mgmt_ip=mgmt_ip)

        stack = heatclient.create(stack_name, stack_template, stack_params)
        stack_id = stack['stack']['id']
        LOG.info(_("Created stack with ID %(stack_id)s and name %(stack_name)s"
                   " for provider PTG %(provider)s"),
                 {'stack_id': stack_id, 'stack_name': stack_name,
                  'provider': provider['id']})
        # self._wait_for_stack_operation_complete(heatclient, stack_id,
        #                                         "create")
        if service_profile['service_type'] == pconst.LOADBALANCER:
            auth_token, provider_tenant_id = self._get_tenant_context(
                provider_tenant_id)
             self._create_policy_target_for_vip(auth_token,
                  provider_tenant_id, provider)

        return stack_id

    def delete(self, service_details, stack_id):
        provider = service_details['policy_target_group']
        auth_token, resource_owner_tenant_id =\
            self._get_resource_owner_context()

        provider_tenant_id = provider['tenant_id']
        try:
            heatclient = self._get_heat_client(resource_owner_tenant_id,
                                               tenant_id=provider_tenant_id)
            heatclient.delete(stack_id)
        except Exception:
            # Log the error and continue with VM delete in case of *aas
            # cleanup failure
            LOG.exception(_("Cleaning up the service chain stack failed"))

    def _update(self, auth_token, resource_owner_tenant_id, service_profile,
                service_chain_node, service_chain_instance, provider,
                consumer_port, provider_port, stack_id, mgmt_ip=None,
                pt_added_or_removed=False):
        # If it is not a Node config update or PT change for LB, no op
        # FIXME(Magesh): Why are we invoking heat update for FW and VPN
        # in Phase 1 even when there was no config change ??
        service_type = service_profile['service_type']
        provider_tenant_id = provider['tenant_id']
        heatclient = self._get_heat_client(resource_owner_tenant_id,
                                           tenant_id=provider_tenant_id)

        if not mgmt_ip:
            raise ServiceInfoNotAvailableOnUpdate()

        stack_template, stack_params = self._update_node_config(
            auth_token, provider_tenant_id, service_profile,
            service_chain_node, service_chain_instance, provider,
            consumer_port, provider_port,
            update=True, mgmt_ip=mgmt_ip)
        if stack_id:
            # FIXME(Magesh): Fix the update stack issue on Heat/*aas driver
            if service_type == pconst.VPN or service_type == pconst.FIREWALL:
                 heatclient.delete(stack_id)

                try:
                    self._wait_for_stack_operation_complete(heatclient,
                                                            stack_id,
                                                            'delete')
                except Exception as err:
                    LOG.error(_("Stack deletion failed for STACK ID - "
                              "%(stack_id)s for Tenant - %(tenant_id)s . "
                              "ERROR - %(err)") %
                              {'stack_id': stack_id,
                              'tenant_id': provider_tenant_id,
                              'err': str(err)})

                stack_name = ("stack_" + service_chain_instance['name'] +
                              service_chain_node['name'] +
                              service_chain_instance['id'][:8] +
                              service_chain_node['id'][:8] + '-' +
                              time.strftime("%Y%m%d%H%M%S"))
                try:
                     stack = heatclient.create(stack_name, stack_template,
                                              stack_params)
                except Exception as err:
                    msg = ('Fatal error. Heat Stack creation failed while '
                           'update of node. To recover,please delete the '
                           'associated provider of Tenant ID -  %r . Details '
                           '- %r' % (provider_tenant_id, str(err)))
                    raise NodeDBUpdateException(msg=msg)
                try:
                    self._wait_for_stack_operation_complete(
                        heatclient, stack["stack"]["id"], "create")
                    stack_id = stack["stack"]["id"]
                except Exception as err:
                    msg = ('Node update failed. There can be a chance if the '
                           'service is FIREWALL or VPN, the related '
                           'configuration would have been lost. Please check '
                           'with the ADMIN for issue of failure and '
                           're-initiate the update node once again.')
                    LOG.exception(_('%(msg) NODE-ID: %(node_id)s '
                                  'INSTANCE-ID: %(instance_id)s '
                                  'TenantID: %(tenant_id)s . '
                                  'ERROR: %(err)s') %
                                  {'msg': msg,
                                   'node_id': service_chain_node['id'],
                                   'instance_id': service_chain_instance['id'],
                                   'tenant_id': provider_tenant_id,
                                   'err': str(err)})
                    raise NodeUpdateException(
                        node=service_chain_node['id'],
                        instance_id=service_chain_instance['id'],
                        tenant=provider_tenant_id, msg=msg)
            else:
                self._wait_for_stack_operation_complete(
                    heatclient, stack_id, 'update', ignore_error=True)
                heatclient.update(stack_id, stack_template, stack_params)
                self._wait_for_stack_operation_complete(
                    heatclient, stack_id, 'update')
        if not stack_id:
            stack_name = ("stack_" + service_chain_instance['name'] +
                          service_chain_node['name'] +
                          service_chain_instance['id'][:8] +
                          service_chain_node['id'][:8] + '-' +
                          time.strftime("%Y%m%d%H%M%S"))
            try:
                stack = heatclient.create(stack_name, stack_template,
                                          stack_params)
            except Exception as err:
                msg = ('Fatal error. Heat Stack creation failed while '
                       'update of node. To recover,please delete the '
                       'associated provider of Tenant ID -  %r . Details '
                       '- %r' % (provider_tenant_id, str(err)))
                raise NodeDBUpdateException(msg=msg)
            try:
                self._wait_for_stack_operation_complete(
                    heatclient, stack["stack"]["id"], "create")
                stack_id = stack["stack"]["id"]
            except Exception as err:
                msg = ('Node update failed. There can be a chance if the '
                       'service is FIREWALL or VPN, the related '
                       'configuration would have been lost. Please check '
                       'with the ADMIN for issue of failure and '
                       're-initiate the update node once again.')
                LOG.exception(_('%(msg) NODE-ID: %(node_id)  INSTANCE-ID: '
                              '%(instance_id) TenantID: %(tenant_id) . '
                              'ERROR: %(err)') %
                              {'msg': msg, 'node_id': service_chain_node['id'],
                               'instance_id': service_chain_instance['id'],
                               'tenant_id': provider_tenant_id,
                               'err': str(err)})

                raise NodeUpdateException(
                    node=service_chain_node['id'],
                    instance_id=service_chain_instance['id'],
                    tenant=provider_tenant_id, msg=msg)

        return stack_id

    def update(self, service_details, stack_id):
        service_profile = service_details['service_profile']
        service_chain_node = service_details['servicechain_node']
        service_chain_instance = service_details['servicechain_instance']
        provider = service_details['policy_target_group']
        consumer_port = service_details['consumer_port']
        provider_port = service_details['provider_port']
        mgmt_ip = service_details['mgmt_ip']

        auth_token, resource_owner_tenant_id =\
            self._get_resource_owner_context()
        stack_id = self._update(auth_token, resource_owner_tenant_id,
                                service_profile, service_chain_node,
                                service_chain_instance, provider,
                                consumer_port, provider_port,
                                stack_id, mgmt_ip)

        return stack_id

    def handle_policy_target_added(self, service_details, policy_target):
        service_profile = service_details['service_profile']
        service_chain_node = service_details['servicechain_node']
        service_chain_instance = service_details['servicechain_instance']
        provider = service_details['policy_target_group']
        consumer_port = service_details['consumer_port']
        provider_port = service_details['provider_port']
        mgmt_ip = service_details['mgmt_ip']
        stack_id = service_details['heat_stack_id']

        if service_profile['service_type'] == pconst.LOADBALANCER:
            if self._is_service_target(policy_target):
                return
            auth_token, resource_owner_tenant_id =\
                self._get_resource_owner_context()
            stack_id = self._update(auth_token, resource_owner_tenant_id,
                                    service_profile, service_chain_node,
                                    service_chain_instance, provider,
                                    consumer_port, provider_port, stack_id,
                                    mgmt_ip, pt_added_or_removed=True)

        return stack_id

    def handle_policy_target_removed(self, service_details, policy_target):
        service_profile = service_details['service_profile']
        service_chain_node = service_details['servicechain_node']
        service_chain_instance = service_details['servicechain_instance']
        provider = service_details['policy_target_group']
        consumer_port = service_details['consumer_port']
        provider_port = service_details['provider_port']
        mgmt_ip = service_details['mgmt_ip']
        stack_id = service_details['heat_stack_id']

        if service_profile['service_type'] == pconst.LOADBALANCER:
            if self._is_service_target(policy_target):
                return
            auth_token, resource_owner_tenant_id =\
                self._get_resource_owner_context()
            try:
                stack_id = self._update(auth_token, resource_owner_tenant_id,
                                        service_profile, service_chain_node,
                                        service_chain_instance, provider,
                                        consumer_port, provider_port, stack_id,
                                        mgmt_ip, pt_added_or_removed=True)
                return stack_id
            except Exception:
                LOG.exception(_("Processing policy target delete failed"))

    def notify_chain_parameters_updated(self, service_details):
        pass  # We are not using the classifier specified in redirect Rule

    def handle_consumer_ptg_added(self, service_details,
                                  policy_target_group):
        service_profile = service_details['service_profile']
        service_chain_node = service_details['servicechain_node']
        service_chain_instance = service_details['servicechain_instance']
        provider = service_details['policy_target_group']
        consumer_port = service_details['consumer_port']
        provider_port = service_details['provider_port']
        mgmt_ip = service_details['mgmt_ip']
        stack_id = service_details['heat_stack_id']

        if service_profile['service_type'] == pconst.FIREWALL:
            auth_token, resource_owner_tenant_id =\
                self._get_resource_owner_context()
            stack_id = self._update(auth_token, resource_owner_tenant_id,
                                    service_profile, service_chain_node,
                                    service_chain_instance, provider,
                                    consumer_port, provider_port,
                                    stack_id, mgmt_ip)

            return stack_id

    def handle_consumer_ptg_removed(self, service_details,
                                    policy_target_group):
        service_profile = service_details['service_profile']
        service_chain_node = service_details['servicechain_node']
        service_chain_instance = service_details['servicechain_instance']
        provider = service_details['policy_target_group']
        consumer_port = service_details['consumer_port']
        provider_port = service_details['provider_port']
        mgmt_ip = service_details['mgmt_ip']
        stack_id = service_details['heat_stack_id']

        if service_profile['service_type'] == pconst.FIREWALL:
            auth_token, resource_owner_tenant_id =\
                self._get_resource_owner_context()
            stack_id = self._update(auth_token, resource_owner_tenant_id,
                                    service_profile, service_chain_node,
                                    service_chain_instance, provider,
                                    consumer_port, provider_port,
                                    stack_id, mgmt_ip)

            return stack_id
