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

from oslo_log import log as logging
import pecan
from pecan import rest
import requests

LOG = logging.getLogger(__name__)
TOPIC = 'configurator'

"""Implements all the APIs Invoked by HTTP requests.

Implements following HTTP methods.
    -get
    -post

"""

notifications = []
cache_ips = set()


class Controller(rest.RestController):

    def __init__(self, method_name):
        try:
            self.method_name = method_name
            self.supported_service_types = ['config_script',
                                            'firewall',
                                            'loadbalancer', 'vpn']
            self.resource_map = {
                ('interfaces', 'healthmonitor', 'routes'): 'orchestrator',
                ('heat'): 'service_orchestrator',
                ('firewall', 'lb', 'vpn'): 'neutron'
            }
            super(Controller, self).__init__()
        except Exception as err:
            msg = (
                "Failed to initialize Controller class  %s." %
                str(err).capitalize())
            LOG.error(msg)

    def _push_notification(self, context, request_info, result, config_data):
        global notifications
        resource = config_data['resource']
        receiver = ''
        for key in self.resource_map.keys():
            if resource in key:
                receiver = self.resource_map[key]

        response = {
            'receiver': receiver,
            'resource': resource,
            'method': 'network_function_device_notification',
            'kwargs': [
                {
                    'context': context,
                    'resource': resource,
                    'request_info': request_info,
                    'result': result
                }
            ]
        }

        notifications.append(response)

    @pecan.expose(method='GET', content_type='application/json')
    def get(self):
        """Method of REST server to handle request get_notifications.

        This method send an RPC call to configurator and returns Notification
        data to config-agent

        Returns: Dictionary that contains Notification data

        """
        global cache_ips
        global notifications
        try:
            if not cache_ips:
                notification_data = jsonutils.dumps(notifications)
                msg = ("NOTIFICATION_DATA sent to config_agent %s"
                       % notification_data)
                LOG.info(msg)
                notifications = []
                return notification_data
            else:
                for ip in cache_ips:
                    notification_response = requests.get(
                        'http://' + str(ip) + ':8080/v1/nfp/get_notifications')
                    notification = jsonutils.loads(notification_response.text)
                    notifications.extend(notification)
                    cache_ips.remove(ip)
                    if ip not in cache_ips:
                        break
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
        """Method of REST server to handle all the post requests.

        This method sends an RPC cast to configurator according to the
        HTTP request.

        :param body: This method excepts dictionary as a parameter in HTTP
        request and send this dictionary to configurator with RPC cast.

        Returns: None

        """
        try:
            global cache_ips
            global notifications
            body = None
            if pecan.request.is_body_readable:
                body = pecan.request.json_body

            # Assuming config list will have only one element
            config_data = body['config'][0]
            context = config_data['kwargs']['context']
            request_info = config_data['kwargs']['request_info']

            if 'device_ip' in request_info:
                msg = ("POSTING DATA TO VM :: %s" % body)
                LOG.info(msg)
                device_ip = request_info['device_ip']
                ip = str(device_ip)
                requests.post(
                    'http://' + ip + ':8080/v1/nfp/' + self.method_name,
                    data=jsonutils.dumps(body))
                cache_ips.add(device_ip)
            else:
                service_type = body['info'].get('service_type')
                if (service_type == "config_init"):
                    result = "unhandled"
                    self._push_notification(context, request_info,
                                            result, config_data)
                else:
                    result = "error"
                    self._push_notification(context, request_info,
                                            result, config_data)
        except Exception as err:
            pecan.response.status = 400
            msg = ("Failed to serve HTTP post request %s %s."
                   % (self.method_name, str(err).capitalize()))
            LOG.error(msg)
            error_data = self._format_description(msg)
            return jsonutils.dumps(error_data)

    @pecan.expose(method='PUT', content_type='application/json')
    def put(self, **body):
        """Method of REST server to handle all the put requests.

        This method sends an RPC cast to configurator according to the
        HTTP request.

        :param body: This method excepts dictionary as a parameter in HTTP
        request and send this dictionary to configurator with RPC cast.

        Returns: None

        """

        try:
            global cache_ips
            global notifications
            body = None
            if pecan.request.is_body_readable:
                body = pecan.request.json_body

            # Assuming config list will have only one element
            config_data = body['config'][0]
            context = config_data['kwargs']['context']
            request_info = config_data['kwargs']['request_info']
            if 'device_ip' in request_info:
                msg = ("PUTTING DATA TO VM :: %s" % body)
                LOG.info(msg)
                device_ip = request_info['device_ip']
                ip = str(device_ip)
                requests.post(
                    'http://' + ip + ':8080/v1/nfp/' + self.method_name,
                    data=jsonutils.dumps(body))
                cache_ips.add(device_ip)
            else:
                service_type = body['info'].get('service_type')
                if (service_type == "config_init"):
                    result = "unhandled"
                    self._push_notification(context, request_info,
                                            result, config_data)
                else:
                    result = "error"
                    self._push_notification(context, request_info,
                                            result, config_data)
        except Exception as err:
            pecan.response.status = 400
            msg = ("Failed to serve HTTP post request %s %s."
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