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

import oslo_serialization.jsonutils as jsonutils
import subprocess

import netaddr
import netifaces
from oslo_log._i18n import _LE
from oslo_log._i18n import _LI
from oslo_log import log as logging
import pecan
from pecan import rest
import time
import yaml

LOG = logging.getLogger(__name__)
TOPIC = 'configurator'
SUCCESS = 'SUCCESS'

"""Implements all the APIs Invoked by HTTP requests.

Implements following HTTP methods.
    -get
    -post

"""

notifications = []
FW_SCRIPT_PATH = ("/home/ubuntu/reference_configurator/" +
                  "scripts/configure_fw_rules.py")


class Controller(rest.RestController):

    def __init__(self, method_name):
        try:
            self.method_name = "network_function_device_notification"
            super(Controller, self).__init__()
        except Exception as err:
            msg = (
                "Failed to initialize Controller class  %s." %
                str(err).capitalize())
            LOG.error(msg)

    def _push_notification(self, context, notification_data,
                           config_data, service_type):
        response = {'info': {'service_type': service_type,
                             'context': context},
                    'notification': notification_data
                    }

        notifications.append(response)

    @pecan.expose(method='GET', content_type='application/json')
    def get(self):
        """Method of REST server to handle request get_notifications.

        This method send an RPC call to configurator and returns Notification
        data to config-agent

        Returns: Dictionary that contains Notification data

        """

        global notifications
        try:
            notification_data = jsonutils.dumps(notifications)
            msg = ("NOTIFICATION_DATA sent to config_agent %s"
                   % notification_data)
            LOG.info(msg)
            notifications = []
            return notification_data
        except Exception as err:
            pecan.response.status = 400
            msg = ("Failed to get notification_data  %s."
                   % str(err).capitalize())
            LOG.error(msg)
            error_data = self._format_description(msg)
            return jsonutils.dumps(error_data)

    @pecan.expose(method='POST', content_type='application/json')
    def post(self, **body):
        try:
            body = None
            if pecan.request.is_body_readable:
                body = pecan.request.json_body

            msg = ("Request data:: %s" % body)
            LOG.debug(msg)

            # Assuming config list will have only one element
            config_datas = body['config']
            service_type = body['info']['service_type']
            notification_data = []

            for config_data in config_datas:
                resource = config_data['resource']
                if resource == 'routes':
                    self._add_routes(config_data)

                if (config_data['resource'] in ['ansible', 'heat',
                                                'custom_json']):
                    service_config = config_data['resource_data'][
                                                 'config_string']
                    service_config = str(service_config)
                    if config_data['resource'] == 'ansible':
                        config_str = service_config.lstrip('ansible:')
                        rules = config_str
                    elif config_data['resource'] == 'heat':
                        config_str = service_config.lstrip('heat_config:')
                        rules = self._get_rules_from_config(config_str)
                    elif config_data['resource'] == 'custom_json':
                        config_str = service_config.lstrip('custom_json:')
                        rules = config_str

                    fw_rule_file = FW_SCRIPT_PATH
                    command = ("sudo python " + fw_rule_file + " '" +
                               rules + "'")
                    subprocess.check_output(command, stderr=subprocess.STDOUT,
                                            shell=True)
                notification_data.append(
                            {'resource': config_data['resource'],
                             'data': {'status_code': SUCCESS}})

            context = body['info']['context']
            self._push_notification(context, notification_data,
                                    config_data, service_type)
        except Exception as err:
            pecan.response.status = 400
            msg = ("Failed to serve HTTP post request %s %s."
                   % (self.method_name, str(err).capitalize()))
            LOG.error(msg)
            error_data = self._format_description(msg)
            return jsonutils.dumps(error_data)

    @pecan.expose(method='PUT', content_type='application/json')
    def put(self, **body):
        try:
            body = None
            notification_data = []
            if pecan.request.is_body_readable:
                body = pecan.request.json_body

            # Assuming config list will have only one element
            config_data = body['config'][0]
            context = body['info']['context']
            service_type = body['info']['service_type']

            notification_data.append(
                        {'resource': config_data['resource'],
                         'data': {'status_code': SUCCESS}})
            self._push_notification(context, notification_data,
                                    config_data, service_type)
        except Exception as err:
            pecan.response.status = 400
            msg = ("Failed to serve HTTP put request %s %s."
                   % (self.method_name, str(err).capitalize()))
            LOG.error(msg)
            error_data = self._format_description(msg)
            return jsonutils.dumps(error_data)

    def _format_description(self, msg):
        """This methgod formats error description.

        :param msg: An error message that is to be formatted

        Returns: error_data dictionary
        """

        error_data = {'failure_desc': {'msg': msg}}
        return error_data

    def _add_routes(self, route_info):
        source_cidrs = route_info['resource_data']['source_cidrs']
        # consumer_cidr = route_info['resource_data']['destination_cidr']
        gateway_ip = route_info['resource_data']['gateway_ip']
        for cidr in source_cidrs:
            source_interface = self._get_if_name_by_cidr(cidr)
            try:
                interface_number_string = source_interface.split("eth", 1)[1]
            except IndexError:
                LOG.error(_LE("Retrieved wrong interface %(interface)s for "
                          "configuring routes") %
                          {'interface': source_interface})
            routing_table_number = 20 + int(interface_number_string)
            ip_rule_command = "ip rule add from %s table %s" % (
                cidr, routing_table_number)
            out1 = subprocess.Popen(ip_rule_command, shell=True,
                                    stdout=subprocess.PIPE).stdout.read()
            ip_rule_command = "ip rule add to %s table main" % (cidr)
            out2 = subprocess.Popen(ip_rule_command, shell=True,
                                    stdout=subprocess.PIPE).stdout.read()
            ip_route_command = "ip route add table %s default via %s" % (
                                    routing_table_number, gateway_ip)
            out3 = subprocess.Popen(ip_route_command, shell=True,
                                    stdout=subprocess.PIPE).stdout.read()
            output = "%s\n%s\n%s" % (out1, out2, out3)
            LOG.info(_LI("Static route configuration result: %(output)s") %
                     {'output': output})

    def _get_if_name_by_cidr(self, cidr):
        interfaces = netifaces.interfaces()
        retry_count = 0
        while True:
            all_interfaces_have_ip = True
            for interface in interfaces:
                inet_list = netifaces.ifaddresses(interface).get(
                    netifaces.AF_INET)
                if not inet_list:
                    all_interfaces_have_ip = False
                for inet_info in inet_list or []:
                    netmask = inet_info.get('netmask')
                    ip_address = inet_info.get('addr')
                    subnet_prefix = cidr.split("/")
                    if (ip_address == subnet_prefix[0] and (
                         len(subnet_prefix) == 1 or subnet_prefix[1] == "32")):
                        return interface
                    ip_address_netmask = '%s/%s' % (ip_address, netmask)
                    interface_cidr = netaddr.IPNetwork(ip_address_netmask)
                    if str(interface_cidr.cidr) == cidr:
                        return interface
            # Sometimes the hotplugged interface takes time to get IP
            if not all_interfaces_have_ip:
                if retry_count < 10:
                    time.sleep(3)
                    retry_count = retry_count + 1
                    continue
                else:
                    raise Exception("Some of the interfaces do not have "
                                    "IP Address")

    def _get_rules_from_config(self, config_str):
        rules_list = []
        try:
            stack_template = (jsonutils.loads(config_str) if
                              config_str.startswith('{') else
                              yaml.load(config_str))
        except Exception:
            return config_str

        resources = stack_template['resources']
        for resource in resources:
            if resources[resource]['type'] == 'OS::Neutron::FirewallRule':
                rule_info = {}
                destination_port = ''
                rule = resources[resource]['properties']
                # action = rule['action']
                protocol = rule['protocol']
                rule_info['action'] = 'log'
                rule_info['name'] = protocol
                if rule.get('destination_port'):
                    destination_port = rule['destination_port']
                if protocol == 'tcp':
                    rule_info['service'] = (protocol + '/' +
                                            str(destination_port))
                else:
                    rule_info['service'] = protocol
                rules_list.append(rule_info)

        return jsonutils.dumps({'rules': rules_list})
