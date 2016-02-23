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

from gbpservice.neutron.nsf.configurator.drivers.base.\
                            base_driver import BaseDriver
from gbpservice.neutron.nsf.configurator.lib import fw_constants as const

LOG = logging.getLogger(__name__)


class FwGenericConfigDriver(object):
    """
    Driver class for implementing firewall configuration
    requests from Orchestrator.
    """

    def __init__(self):
        self.timeout = cfg.CONF.rest_timeout

    def configure_interfaces(self,  context, kwargs):
        rule_info = kwargs.get('rule_info')

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
            return msg
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while adding "
                   "persistent rule of primary service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            return msg

        try:
            result = resp.json()
        except ValueError as err:
            msg = ("Unable to parse response, invalid JSON. URL: "
                   "%r. %r" % (url, str(err).capitalize()))
            LOG.error(msg)
            return msg
        if not result['status']:
            msg = ("Error adding persistent rule. URL: %r" % url)
            LOG.error(msg)
            return msg

        msg = ("Persistent rule successfully added for SERVICE ID: %r"
               " of tenant: %r" % (rule_info['service_id'],
                                   rule_info['tenant_id']))
        LOG.info(msg)
        return const.STATUS_SUCCESS

    def clear_interfaces(self, context, kwargs):
        rule_info = kwargs.get('rule_info')

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
                   "%r. %r" % (url, str(err).capitalize()))
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
        return const.STATUS_SUCCESS

    def configure_source_routes(self, context, kwargs):
        vm_mgmt_ip = kwargs.get('mgmt_ip')
        source_cidrs = kwargs.get('source_cidrs')
        gateway_ip = kwargs.get('gateway_ip')

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
            return msg
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while configuring "
                   "route of service at: %r ERROR: %r" % (
                    vm_mgmt_ip, str(err).capitalize()))
            LOG.error(msg)
            return msg

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
                return msg

        msg = ("Route configuration status : %r "
               % (active_configured))
        LOG.info(msg)
        if active_configured:
            return const.STATUS_SUCCESS
        else:
            return ("Failed to configure source route. Response code: %s."
                    "Response Content: %r" % (resp.status_code, resp.content))

    def delete_source_routes(self, context, kwargs):
        vm_mgmt_ip = kwargs.get('mgmt_ip')
        source_cidrs = kwargs.get('source_cidrs')

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
            return msg
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while deleting "
                   " route of service at: %r ERROR: %r"
                   % (vm_mgmt_ip,  err))
            LOG.error(msg)
            return msg

        if resp.status_code in const.SUCCESS_CODES:
            active_configured = True

        msg = ("Route deletion status : %r "
               % (active_configured))
        LOG.info(msg)
        if active_configured:
            return const.STATUS_SUCCESS
        else:
            return ("Failed to delete source route. Response code: %s."
                    "Response Content: %r" % (resp.status_code, resp.content))


class FwaasDriver(FwGenericConfigDriver, BaseDriver):
    """
    Driver class for implementing firewall configuration
    requests from Fwaas Plugin.
    """

    service_type = const.SERVICE_TYPE

    def __init__(self):
        self.timeout = cfg.CONF.rest_timeout
        self.host = cfg.CONF.host
        self.context = context.get_admin_context_without_session()

    def _get_firewall_attribute(self, firewall):
        description = ast.literal_eval(firewall["description"])
        if not description.get('vm_management_ip'):
            LOG.debug("Failed to find vm_management_ip.")
            raise

        if not description.get('service_vendor'):
            LOG.debug("Failed to find service_vendor.")
            raise

        LOG.debug("Found vm_management_ip %s."
                  % description['vm_management_ip'])
        return description['vm_management_ip']

    def _print_exception(self, exception_type, err,
                         url, operation, response=None):
        """
        :param exception_type: Name of the exception as a string
        :param err: Either error of type Exception or error code
        :param url: Service url
        :param operation: Create, update or delete
        :param response: Response content from Service VM
        """
        if exception_type == 'ConnectionError':
            msg = ("Error occurred while connecting to firewall "
                   "service at URL: %r. Firewall not %sd. %s. "
                   % (url, operation, str(err).capitalize()))
            LOG.error(msg)
        elif exception_type == 'RequestException':
            msg = ("Unexpected error occurred while connecting to "
                   "firewall service at URL: %r. Firewall not %sd. %s"
                   % (url, operation, str(err).capitalize()))
            LOG.error(msg)
        elif exception_type == 'ValueError':
            msg = ("Unable to parse the response. Invalid "
                   "JSON from URL: %r. Firewall not %sd. %s. %r"
                   % (url, operation, str(err).capitalize(), response))
            LOG.error(msg)
        elif exception_type == 'UnexpectedError':
            msg = ("Unexpected error occurred while connecting to service "
                   "at URL: %r. Firewall not %sd. %s. %r"
                   % (url, operation, str(err).capitalize(), response))
            LOG.error(msg)
        elif exception_type == 'Failure':
            msg = ("Firewall not %sd. URL: %r. Response "
                   "code from server: %r. %r"
                   % (operation, url, err, response))
            LOG.error(msg)

    def create_firewall(self, context, firewall, host):
        LOG.debug("Processing create firewall request in FWaaS Driver "
                  "for Firewall ID: %s." % firewall['id'])
        vm_mgmt_ip = self._get_firewall_attribute(firewall)
        url = const.request_url % (vm_mgmt_ip,
                                   const.CONFIGURATION_SERVER_PORT,
                                   'configure-firewall-rule')
        LOG.info(_("Initiating POST request for FIREWALL ID: %r Tenant ID:"
                   " %r. URL: %s" % (firewall['id'], firewall['tenant_id'],
                                     url)))
        data = json.dumps(firewall)
        try:
            resp = requests.post(url, data, timeout=self.timeout)
        except requests.exceptions.ConnectionError as err:
            self._print_exception('ConnectionError', err, url, 'create')
            raise requests.exceptions.ConnectionError(err)
        except requests.exceptions.RequestException as err:
            self._print_exception('RequestException', err, url, 'create')
            raise requests.exceptions.RequestException(err)

        LOG.debug("POSTed the configuration to Service VM")
        if resp.status_code in const.SUCCESS_CODES:
            try:
                resp_payload = resp.json()
                if resp_payload['config_success']:
                    msg = ("Configured Firewall successfully. URL: %s"
                           % url)
                    LOG.info(msg)
                    return const.STATUS_ACTIVE
                else:
                    self._print_exception('Failure',
                                          resp.status_code, url,
                                          'create', resp.content)
                    return const.STATUS_ERROR
            except ValueError as err:
                self._print_exception('ValueError', err, url,
                                      'create', resp.content)
                return const.STATUS_ERROR
            except Exception as err:
                self._print_exception('UnexpectedError', err, url,
                                      'create', resp.content)
                return const.STATUS_ERROR
        else:
            self._print_exception('Failure', resp.status_code, url,
                                  'create', resp.content)
            return const.STATUS_ERROR

    def update_firewall(self, context, firewall, host):
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
            self._print_exception('UnexpectedError', err, url, 'update')
            raise Exception(err)
        if resp.status_code == 200:
            msg = ("Successful UPDATE request. URL: %s" % url)
            LOG.info(msg)
            return const.STATUS_ACTIVE
        else:
            self._print_exception('Failure', resp.status_code, url,
                                  'create', resp.content)
            return const.STATUS_ERROR

    def delete_firewall(self, context, firewall, host):
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
            self._print_exception('ConnectionError', err, url, 'delete')
            raise requests.exceptions.ConnectionError(err)
        except requests.exceptions.RequestException as err:
            self._print_exception('RequestException', err, url, 'delete')
            raise requests.exceptions.RequestException(err)

        if resp.status_code in const.SUCCESS_CODES:
            # For now agent only check for ERROR.
            try:
                resp_payload = resp.json()
                if resp_payload['delete_success']:
                    msg = ("Deleted Firewall successfully.")
                    LOG.info(msg)
                    return const.STATUS_DELETED
                elif not resp_payload['delete_success'] and \
                        resp_payload.get('message', '') == (
                                            const.INTERFACE_NOT_FOUND):
                    # VK: This is a special case.
                    msg = ("Firewall not deleted, as interface is not "
                           "available in firewall. Possibly got detached. "
                           " So marking this delete as success. URL: %r"
                           "Response Content: %r" % (url, resp.content))
                    LOG.error(msg)
                    return const.STATUS_SUCCESS
                else:
                    self._print_exception('Failure',
                                          resp.status_code, url,
                                          'delete', resp.content)
                    return const.STATUS_ERROR
            except ValueError as err:
                self._print_exception('ValueError', err, url,
                                      'delete', resp.content)
                return const.STATUS_ERROR
            except Exception as err:
                self._print_exception('UnexpectedError', err, url,
                                      'delete', resp.content)
                return const.STATUS_ERROR
        else:
            self._print_exception('Failure', resp.status_code, url,
                                  'create', resp.content)
            return const.STATUS_ERROR