import json
import subprocess

from neutron.common import rpc as n_rpc
from neutron.agent.common import config
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging
from pecan import expose, request
from pecan import rest

import constants

LOG = logging.getLogger(__name__)

"""Controller class for handling all the HTTP requests.
This Controller class serves all the HTTP requests sent by
config-agent to configurator and make RPC call accordingly."""


class Controller(rest.RestController):

    def __init__(self, module_name):
        try:
            self.host = subprocess.check_output(
                            'hostname', shell=True).rstrip()
        except Exception as err:
            msg = ("Failed to get hostname  %s." % str(err).capitalize())
            LOG.error(msg)
        self.rpcclient = RPCClient(topic=constants.TOPIC, host=self.host)
        self.module_name = module_name
        super(Controller, self).__init__()

    @expose(method='GET', content_type='application/json')
    def get(self):
        """get method of REST server.
        This method returns Notification data to config-agent"""
        try:
            notification_data = json.dumps(self.rpcclient.get_notifications())
            msg = ("NOTIFICATION_DATA sent to config_agent %s"
                   % notification_data)
            LOG.info(msg)
            return notification_data
        except Exception as err:
            msg = ("Failed to get notification_data  %s."
                   % str(err).capitalize())
            LOG.error(msg)
            return json.dumps({'ERROR': msg})

    @expose(method='POST', content_type='application/json')
    def post(self, **body):
        """post method REST server.
        cast RPC according to the post request by using
        object of RPCClient"""
        try:
            body = None
            if request.is_body_readable:
                body = request.json_body

            method = getattr(self.rpcclient, '%s' % self.module_name)
            method(body)
            msg = ("Successfully served HTTP request %s" % self.module_name)
            LOG.info(msg)
            return json.dumps({'SUCCESS': self.module_name})
        except Exception as err:
            msg = ("Failed to serve HTTP post request %s %s."
                   % (self.module_name, str(err).capitalize()))
            LOG.error(msg)
            return json.dumps({'ERROR': msg})

    @expose(method='PUT', content_type='application/json')
    def put(self, **body):
        """put method REST server.
        cast RPC according to the put request by using
        object of RPCClient"""
        try:
            body = None
            if request.is_body_readable:
                body = request.json_body

            method = getattr(self.rpcclient, '%s' % self.module_name)
            method(body)
            msg = ("Successfully served HTTP request %s" % self.module_name)
            LOG.info(msg)
            return json.dumps({'SUCCESS': self.module_name})

        except Exception as err:
            msg = ("Failed to serve HTTP put request %s %s."
                   % (self.module_name, str(err).capitalize()))
            LOG.error(msg)
            return json.dumps({'ERROR': msg})


"""This class make RPC call/cast on behalf of controller class
    according to the HTTP request coming from config-agent."""


class RPCClient(object):

    API_VERSION = '1.0'

    def __init__(self, topic, host):

        self.topic = topic
        self.host = host
        target = oslo_messaging.Target(
            topic=self.topic,
            version=self.API_VERSION)
        n_rpc.init(cfg.CONF)
        self.client = n_rpc.get_client(target)

    def get_notifications(self):
        """ make rpc call 'get_notifications' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.call(self, 'get_notifications')

    def create_network_function_device_config(self, request_data):
        """ make rpc cast 'create_network_function_device_config' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self, 'create_network_function_device_config',
                          request_data=request_data)

    def create_network_function_config(self, request_data):
        """ make rpc cast 'create_network_function_config' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self, 'create_network_function_config',
                          request_data=request_data)

    def update_network_function_device_config(self, request_data):
        """ make rpc cast 'update_network_function_device_config' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self, 'update_network_function_device_config',
                          request_data=request_data)

    def update_network_function_config(self, request_data):
        """ make rpc cast 'update_network_function_config' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self, 'update_network_function_config',
                          request_data=request_data)

    def delete_network_function_device_config(self, request_data):
        """ make rpc cast 'delete_network_function_device_config' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self, 'delete_network_function_device_config',
                          request_data=request_data)

    def delete_network_function_config(self, request_data):
        """ make rpc cast 'delete_network_function_config' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self, 'delete_network_function_config',
                          request_data=request_data)

    def to_dict(self):

        return {}
