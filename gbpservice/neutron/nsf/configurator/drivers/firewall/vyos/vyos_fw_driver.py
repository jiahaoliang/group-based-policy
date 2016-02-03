# One Convergence, Inc. CONFIDENTIAL
# Copyright (c) 2012-2016, One Convergence, Inc., USA
# All Rights Reserved.
#
# All information contained herein is, and remains the property of
# One Convergence, Inc. and its suppliers, if any. The intellectual and
# technical concepts contained herein are proprietary to One Convergence,
# Inc. and its suppliers.
#
# Dissemination of this information or reproduction of this material is
# strictly forbidden unless prior written permission is obtained from
# One Convergence, Inc., USA

import ast
import json
import requests

from oslo_config import cfg
from oslo_log import log as logging

from neutron import context
from neutron.agent import rpc as agent_rpc

from gbpservice.neutron.nsf.configurator.lib import fw_constants as const
from gbpservice.neutron.nsf.configurator.modules.firewall import FwaasRpcSender

LOG = logging.getLogger(__name__)


class FwGenericConfigDriver(object):
    """
    This class implements requests to configure VYOS generic services.
    """

    def __init__(self):
        self.timeout = cfg.CONF.rest_timeout

    def _configure_interfaces(self,  ev):
        pass

    def _clear_interfaces(self, ev):
        pass

    def _configure_license(self, ev):
        pass

    def _release_license(self, ev):
        pass

    def _configure_source_routes(self, ev):

        vm_mgmt_ip = ev.data.get('vm_mgmt_ip')
        source_cidrs = ev.data.get('source_cidrs')
        destination_cidr = ev.data.get('destination_cidr')
        gateway_ip = ev.data.get('gateway_ip')
        provider_interface_position = ev.data.get(
                                        'provider_interface_position')

        if not (vm_mgmt_ip and source_cidrs and destination_cidr and
                gateway_ip and provider_interface_position):
            msg = ("Parameters missing for FW source route configuration.")
            raise Exception(msg)
        # REVISIT(VK): This was all along bad way, don't know why at all it
        # was done like this.

        url = const.request_url % (vm_mgmt_ip, const.CONFIGURATION_SERVER_PORT,
                                   'add-source-route')
        active_configured = False
        route_info = []
        for source_cidr in source_cidrs:
            route_info.append({'source_cidr': source_cidr,
                               'gateway_ip': gateway_ip})
        data = json.dumps(route_info)
        msg = ("Initiating POST request to configure route of "
               "primary service at: %r" % vm_mgmt_ip)
        LOG.info(msg)
        try:
            resp = requests.post(url, data=data, timeout=60)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to service at: "
                   "%r. ERROR: %r" % (vm_mgmt_ip, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while configuring "
                   "route of service at: %r ERROR: %r" % (
                    vm_mgmt_ip, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)

        if resp.status_code in const.SUCCESS_CODES:
            message = json.loads(resp.text)
            if message.get("status", False):
                msg = ("Route configured successfully for VYOS"
                       " service at: %r" % vm_mgmt_ip)
                LOG.info(msg)
                active_configured = True
            else:
                msg = ("Configure source route failed on service with"
                       " status %s %s"
                       % (resp.status_code, message.get("reason", None)))
                LOG.error(msg)
                raise Exception(msg)

        msg = ("Route configuration status : %r "
               % (active_configured))
        LOG.info(msg)

    def _delete_source_routes(self, ev):

        vm_mgmt_ip = ev.data.get('vm_mgmt_ip')
        source_cidrs = ev.data.get('source_cidrs')
        provider_interface_position = ev.data.get(
                                        'provider_interface_position')

        if not (vm_mgmt_ip and source_cidrs and provider_interface_position):
            msg = ("Parameters missing for FW source routes deletion.")
            raise Exception(msg)
        # REVISIT(VK): This was all along bad way, don't know why at all it
        # was done like this.
        active_configured = False
        url = const.request_url % (vm_mgmt_ip, const.CONFIGURATION_SERVER_PORT,
                                   'delete-source-route')
        route_info = []
        for source_cidr in source_cidrs:
            route_info.append({'source_cidr': source_cidr})
        data = json.dumps(route_info)
        msg = ("Initiating DELETE route request to primary service at: %r"
               % vm_mgmt_ip)
        LOG.info(msg)
        try:
            resp = requests.delete(url, data=data, timeout=self.timeout)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to primary service at: "
                   " %r. ERROR: %r" % (vm_mgmt_ip, err))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while deleting "
                   " route of service at: %r ERROR: %r"
                   % (vm_mgmt_ip,  err))
            LOG.error(msg)
            raise Exception(err)

        if resp.status_code in const.SUCCESS_CODES:
            active_configured = True

        msg = ("Route deletion status : %r "
               % (active_configured))
        LOG.info(msg)

    def _add_persistent_rule(self, ev):

        kwargs = ev.data.get('kwargs')
        if not kwargs:
            msg = ("Parameters missing for FW persistent rule addition.")
            raise Exception(msg)

        rule_info = kwargs['rule_info']

        active_rule_info = dict(
            provider_mac=rule_info['active_provider_mac'],
            stitching_mac=rule_info['active_stitching_mac'])

        active_fip = rule_info['active_fip']

        url = const.request_url % (active_fip,
                                   const.CONFIGURATION_SERVER_PORT, 'add_rule')
        data = json.dumps(active_rule_info)
        msg = ("Initiating POST request to add persistent rule to primary "
               "service with SERVICE ID: %r of tenant: %r at: %r" % (
                    rule_info['service_id'], rule_info['tenant_id'],
                    active_fip))
        LOG.info(msg)
        try:
            resp = requests.post(url, data, timeout=self.timeout)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to primary service at: "
                   "%r of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while adding "
                   "persistent rule of primary service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)

        try:
            result = resp.json()
        except ValueError as err:
            msg = ("Unable to parse response, invalid JSON. URL: "
                   "%r" % (url, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(msg)
        if not result['status']:
            msg = ("Error adding persistent rule. URL: %r" % url)
            LOG.error(msg)
            raise Exception(msg)

        msg = ("Persistent rule successfully added for SERVICE ID: %r"
               " of tenant: %r" % (rule_info['service_id'],
                                   rule_info['tenant_id']))
        LOG.info(msg)

    def _delete_persistent_rule(self, ev):

        kwargs = ev.data.get('kwargs')
        if not kwargs:
            msg = ("Parameters missing for FW persistent rule deletion.")
            raise Exception(msg)

        rule_info = kwargs['rule_info']

        active_rule_info = dict(
            provider_mac=rule_info['provider_mac'],
            stitching_mac=rule_info['stitching_mac'])

        active_fip = rule_info['fip']

        msg = ("Initiating DELETE persistent rule for SERVICE ID: %r of "
               "tenant: %r " %
               (rule_info['service_id'], rule_info['tenant_id']))
        LOG.info(msg)
        url = const.request_url % (active_fip,
                                   const.CONFIGURATION_SERVER_PORT,
                                   'delete_rule')

        try:
            data = json.dumps(active_rule_info)
            resp = requests.delete(url, data=data, timeout=self.timeout)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while deleting "
                   "persistent rule of service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)

        try:
            result = resp.json()
        except ValueError as err:
            msg = ("Unable to parse response, invalid JSON. URL: "
                   "%r" % (url, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(msg)
        if not result['status'] or resp.status_code not in [200, 201, 202]:
            msg = ("Error deleting persistent rule. URL: %r" % url)
            LOG.error(msg)
            raise Exception(msg)
        msg = ("Persistent rule successfully deleted for SERVICE ID: %r"
               " of tenant: %r " % (rule_info['service_id'],
                                    rule_info['tenant_id']))
        LOG.info(msg)


class FwaasDriver(object):

    def __init__(self, sc):
        self._sc = sc
        self.timeout = cfg.CONF.rest_timeout
        self.host = cfg.CONF.host
        self.plugin_rpc = FwaasRpcSender(
            const.OC_FW_PLUGIN_TOPIC,
            self.host)
        self.context = context.get_admin_context_without_session()
        self.oc_fwaas_enabled = cfg.CONF.ocfwaas.enabled
        self.agent_state = None
        self.use_call = True
        self.state_rpc = agent_rpc.PluginReportStateAPI(
            const.OC_FW_PLUGIN_TOPIC)
        self.report_interval = cfg.CONF.ocfwaas.oc_report_interval

        if not self.oc_fwaas_enabled:
            msg = ("FWaaS not enabled in configuration file")
            LOG.error(msg)
            raise SystemExit(1)

    def _get_firewall_attribute(self, firewall):
        description = ast.literal_eval(firewall["description"])
        if not description.get('vm_management_ip'):
            raise

        return description['vm_management_ip']

    def _is_firewall_rule_exists(self, fw):
        if not fw['firewall_rule_list']:
            return False
        else:
            return True

    def configure_firewall(self, ev):
        context = ev.data.get('context')
        firewall = ev.data.get('firewall')

        if not (context and firewall):
            msg = ("Parameters missing for firewall configuration.")
            LOG.error(msg)
            raise Exception(msg)

        if not self._is_firewall_rule_exists(firewall):
            msg = ("Firewall status set to ACTIVE")
            LOG.debug(msg)
            '''ENQUEUE: return self.plugin_rpc.set_firewall_status(
                context, firewall['id'], const.STATUS_ACTIVE)'''

        try:
            vm_mgmt_ip = self._get_firewall_attribute(firewall)
            url = const.request_url % (vm_mgmt_ip,
                                       const.CONFIGURATION_SERVER_PORT,
                                       'configure-firewall-rule')
            msg = ("Initiating POST request. URL: %s" % url)
            LOG.info(msg)
            data = json.dumps(firewall)
            try:
                resp = requests.post(url, data, timeout=self.timeout)
            except requests.exceptions.ConnectionError as err:
                msg = ("Error occurred while connecting to service at URL: %r "
                       "for configuring firewall. %s"
                       % (url, str(err).capitalize()))
                LOG.error(msg)
                raise requests.exceptions.ConnectionError(err)
            except requests.exceptions.RequestException as err:
                msg = ("Unexpected error occurred while connecting to service "
                       "at URL: %r for configuring firewall. %s"
                       % (url, str(err).capitalize()))
                LOG.error(msg)
                raise requests.exceptions.RequestException(err)

            if resp.status_code in const.SUCCESS_CODES:
                try:
                    resp_payload = resp.json()
                    if resp_payload['config_success']:
                        msg = ("Configured Firewall successfully. URL: %s"
                               % url)
                        LOG.info(msg)
                        status = const.STATUS_ACTIVE
                    else:
                        msg = ("Firewall configuration NOT successful. URL: %s"
                               % url)
                        LOG.error(msg)
                        status = const.STATUS_ERROR
                except ValueError as err:
                    msg = ("Unable to parse the response. Invalid "
                           "JSON from URL: %r. %s"
                           % (url, str(err).capitalize()))
                    LOG.error(msg)
                    status = const.STATUS_ERROR
                except Exception as err:
                    msg = ("Unexpected error. Firewall not configured. "
                           "URL: %s. %s"
                           % (url, str(err).capitalize()))
                    LOG.error(msg)
                    status = const.STATUS_ERROR
            else:
                msg = ("Firewall not configured. URL: %r. Response "
                       "code from server: %r."
                       % (url, resp.status_code))
                LOG.error(msg)
                status = const.STATUS_ERROR
        except Exception as err:
            self.plugin_rpc.set_firewall_status(
                context, firewall['id'], const.STATUS_ERROR)
            msg = ("Failed to configure Firewall and status is "
                   "changed to ERROR. %s." % str(err).capitalize())
            LOG.error(msg)
        else:
            self.plugin_rpc.set_firewall_status(
                context, firewall['id'], status)
            msg = ("Configured Firewall and status set to %s" % status)
            LOG.info(msg)

    def update_firewall(self, ev):
        context = ev.data.get('context')
        firewall = ev.data.get('firewall')

        if not (context and firewall):
            msg = ("Parameters missing for firewall updation.")
            raise Exception(msg)

        if not self._is_firewall_rule_exists(firewall):
            '''ENQUEUE: return self.plugin_rpc.set_firewall_status(
                context, firewall['id'], const.STATUS_ACTIVE)'''
        try:
            vm_mgmt_ip = self._get_firewall_attribute(firewall)
            url = const.request_url % (vm_mgmt_ip,
                                       const.CONFIGURATION_SERVER_PORT,
                                       'update-firewall-rule')
            msg = ("Initiating UPDATE request. URL: %s" % url)
            LOG.info(msg)
            data = json.dumps(firewall)
            try:
                resp = requests.put(url, data=data, timeout=self.timeout)
            except Exception as err:
                msg = ("Unexpected error occurred while connecting to service"
                       "at URL: %r for updating firewall. %s"
                       % (url, str(err).capitalize()))
                LOG.error(msg)
                raise Exception(err)
            if resp.status_code == 200:
                msg = ("Successful UPDATE request. URL: %s" % url)
                LOG.info(msg)
                status = const.STATUS_ACTIVE
            else:
                msg = ("Failed UPDATE request. URL: %s" % url)
                LOG.info(msg)
                status = const.STATUS_ERROR
        except Exception as err:
            self.plugin_rpc.set_firewall_status(
                        context, firewall['id'], 'ERROR')
            msg = ("Failed to update Firewall and status is "
                   "changed to ERROR. %s." % str(err).capitalize())
            LOG.error(msg)
        else:
            self.plugin_rpc.set_firewall_status(
                            context, firewall['id'], status)
            msg = ("Updated Firewall and status set to %s" % status)
            LOG.info(msg)

    def delete_firewall(self, ev):
        context = ev.data.get('context')
        firewall = ev.data.get('firewall')

        if not (context and firewall):
            msg = ("Parameters missing for firewall deletion.")
            raise Exception(msg)

        if not self._is_firewall_rule_exists(firewall):
            '''ENQUEUE: return self.plugin_rpc.firewall_deleted(context,
                                                          firewall['id'])'''
            msg = ("Deleted Firewall.")
            LOG.emit("info", msg)
        try:
            vm_mgmt_ip = self._get_firewall_attribute(firewall)
            url = const.request_url % (vm_mgmt_ip,
                                       const.CONFIGURATION_SERVER_PORT,
                                       'delete-firewall-rule')
            msg = ("Initiating DELETE request. URL: %s" % url)
            LOG.info(msg)
            data = json.dumps(firewall)
            try:
                resp = requests.delete(url, data=data, timeout=self.timeout)
            except requests.exceptions.ConnectionError as err:
                msg = ("Error occurred while connecting to service at URL: %r "
                       "for deleting firewall. %s"
                       % (url, str(err).capitalize()))
                LOG.error(msg)
                raise requests.exceptions.ConnectionError(err)
            except requests.exceptions.RequestException as err:
                msg = ("Unexpected error occurred while "
                       "deleting firewall. URL: %r. %s"
                       % (url, str(err).capitalize()))
                LOG.error(msg)
                raise requests.exceptions.RequestException(err)

            if resp.status_code in const.SUCCESS_CODES:
                # For now agent only check for ERROR.
                try:
                    resp_payload = resp.json()
                    if resp_payload['delete_success']:
                        msg = ("Deleted Firewall successfully.")
                        LOG.info(msg)
                        status = const.STATUS_DELETED
                    elif not resp_payload['delete_success'] and \
                            resp_payload.get('message', '') == (
                                                const.INTERFACE_NOT_FOUND):
                        # VK: This is a special case.
                        msg = ("Firewall not deleted, as interface is not "
                               "available in firewall. Possibly got detached. "
                               " So marking this delete as success. URL: %r"
                               % url)
                        LOG.error(msg)
                        status = const.STATUS_SUCCESS
                    else:
                        msg = ("Firewall deletion failed. URL: %s"
                               % url)
                        LOG.error(msg)
                        status = const.STATUS_ERROR
                except ValueError as err:
                    msg = ("Unable to parse the response. Invalid "
                           "JSON from URL: %r. %s"
                           % (url, str(err).capitalize()))
                    LOG.error(msg)
                    status = const.STATUS_ERROR
                except Exception as err:
                    msg = ("Unexpected error. Firewall not deleted. URL:%s. %s"
                           % (url, str(err).capitalize()))
                    LOG.error(msg)
                    status = const.STATUS_ERROR
            else:
                msg = ("ERROR happened at server side during deletion of "
                       "URL: %r for firewall. Error code from server: %r."
                       % (url, resp.status_code))
                LOG.error(msg)
                status = const.STATUS_ERROR
        except Exception as err:
            # TODO(Vikash) Is it correct to raise ? As the subsequent
            # attempt to clean will only re-raise the last one.And it
            # can go on and on and may not be ever recovered.
            self.plugin_rpc.set_firewall_status(
                context, firewall['id'], const.STATUS_ERROR)
            msg = ("Failed to delete Firewall and status is "
                   "changed to ERROR. %s." % str(err).capitalize())
            LOG.error(msg)
            # raise(err)
        else:
            if status == const.STATUS_ERROR:
                self.plugin_rpc.set_firewall_status(
                    context, firewall['id'], status)
            else:
                msg = ("Deleted Firewall.")
                LOG.info(msg)
                self.plugin_rpc.firewall_deleted(
                                    context, firewall['id'])
