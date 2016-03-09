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

    def __init__(self, method_name):
        try:
            self.host = subprocess.check_output(
                            'hostname', shell=True).rstrip()
        except Exception as err:
            msg = ("Failed to get hostname  %s." % str(err).capitalize())
            LOG.error(msg)
        self.rpcclient = RPCClient(topic=constants.TOPIC, host=self.host)
        self.method_name = method_name
        super(Controller, self).__init__()

    @expose(method='GET', content_type='application/json')
    def get(self):
        """get method of REST server.
        This method returns Notification data to config-agent"""
        try:
            notification_data = json.dumps(self.rpcclient.call())
            pecan.response.status=200
            msg = ("NOTIFICATION_DATA sent to config_agent %s"
                   % notification_data)
            LOG.info(msg)
            return notification_data
        except Exception as err:
            pecan.response.status=400
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
            
            self.rpcclient.cast(self.method_name, body)
            msg = ("Successfully served HTTP request %s" % self.method_name)
            pecan.response.status=200
            LOG.info(msg)
            return json.dumps({'SUCCESS': self.method_name})
        except Exception as err:
            pecan.response.status=400
            msg = ("Failed to serve HTTP post request %s %s."
                   % (self.method_name, str(err).capitalize()))
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

            self.rpcclient.cast(self.method_name, body)
            pecan.response.status=200
            msg = ("Successfully served HTTP request %s" % self.method_name)
            LOG.info(msg)
            return json.dumps({'SUCCESS': self.method_name})

        except Exception as err:
            pecan.response.status=400
            msg = ("Failed to serve HTTP put request %s %s."
                   % (self.method_name, str(err).capitalize()))
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

    def call(self):
        """ make rpc call for 'get_notifications' """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.call(self,
                          'get_notifications')

    def cast(self, method_name, request_data):
        """ make rpc cast for called method """
        cctxt = self.client.prepare(server=self.host)
        return cctxt.cast(self,
                          method_name,
                          request_data=request_data)
                          
    def to_dict(self):

        return {}
