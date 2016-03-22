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

from oslo_config import cfg
from oslo_messaging import target
from oslo_log import log as logging
from neutron import manager
from gbpservice.nfp.common import topics
from neutron.common import rpc as n_rpc
from neutron.plugins.common import constants
from neutron import context as n_context
from oslo_config import cfg as oslo_config
import requests
import json
import exceptions

LOG = logging.getLogger(__name__)
Version = 'v1'  # v1/v2/v3#

rest_opts = [
    cfg.StrOpt('rest_server_address',
               default='127.0.0.1', help='Rest connection IpAddr'),
    cfg.IntOpt('rest_server_port',
               default=8080, help='Rest connection Port'),
]

rpc_opts = [
    cfg.StrOpt('topic',
               default='', help='Topic for rpc connection'),
]

OPTS = [
    cfg.StrOpt(
        'backend',
        default='rpc',
        help='Backend Support for communicationg with configurator.'
    ),
]

oslo_config.CONF.register_opts(OPTS)
oslo_config.CONF.register_opts(rest_opts, "REST")
oslo_config.CONF.register_opts(rpc_opts, "RPC")


class RestClientException(exceptions.Exception):

    """ RestClient Exception """


class RestApi(object):

    def __init__(self, rest_server_ip, rest_server_port):
        self.rest_server_ip = rest_server_ip
        self.rest_server_port = rest_server_port
        self.url = "http://%s:%s/v1/nfp/%s"

    def _response(self, resp, url):
        success_code = [200, 201, 202, 204]
        if success_code.__contains__(resp.status_code):
            return resp
        elif resp.status_code == 400:
            raise RestClientException("HTTPBadRequest: %s" % resp.reason)
        elif resp.status_code == 401:
            raise RestClientException("HTTPUnauthorized: %s" % resp.reason)
        elif resp.status_code == 403:
            raise RestClientException("HTTPForbidden: %s" % resp.reason)
        elif resp.status_code == 404:
            raise RestClientException("HttpNotFound: %s" % resp.reason)
        elif resp_code.status == 405:
            raise RestClientException(
                "HTTPMethodNotAllowed: %s" % resp.reason)
        elif resp_code.status == 406:
            raise RestClientException("HTTPNotAcceptable: %s" % resp.reason)
        elif resp_code.status == 408:
            raise RestClientException("HTTPRequestTimeout: %s" % resp.reason)
        elif resp.status_code == 409:
            raise RestClientException("HTTPConflict: %s" % resp.reason)
        elif resp.status_code == 415:
            raise RestClientException(
                "HTTPUnsupportedMediaType: %s" % resp.reason)
        elif resp.status_code == 417:
            raise RestClientException(
                "HTTPExpectationFailed: %s" % resp.reason)
        elif resp.status_code == 500:
            raise RestClientException("HTTPServerError: %s" % resp.reason)
        else:
            raise RestClientException('Unhandled Exception code: %s %s' %
                                      (resp.status_code, resp.reason))
        return resp

    def post(self, path, body, method_type):
        url = self.url % (
            self.rest_server_ip,
            self.rest_server_port, path)
        data = json.dumps(body)
        try:
            headers = {"content-type": "application/json",
                       "method-type": method_type}
            resp = requests.post(url, data,
                                 headers=headers)
            LOG.info("POST url %s %d" % (url, resp.status_code))
            return self._response(resp, url)
        except RestClientException as rce:
            LOG.error("Rest API %s - Failed. Reason: %s" % (url, rce))

    def get(self, path):
        url = self.url % (
            self.rest_server_ip,
            self.rest_server_port, path)
        try:
            headers = {"content-type": "application/json"}
            resp = requests.get(url,
                                headers=headers)
            LOG.info("GET url %s %d" % (url, resp.status_code))
            return self._response(resp, url)
        except RestClientException as rce:
            LOG.error("Rest API %s - Failed. Reason: %s" % (url, rce))


class RPCClient(object):
    API_VERSION = '1.0'

    def __init__(self, topic):
        self.topic = topic
        _target = target.Target(topic=self.topic,
                                version=self.API_VERSION)
        n_rpc.init(cfg.CONF)
        self.client = n_rpc.get_client(_target)
        self.cctxt = self.client.prepare(version=self.API_VERSION,
                                         topic=self.topic)


def send_request_to_configurator(conf, context, body,
                                 method_type, device_config=False):
    if device_config:
        method_name = method_type.lower() + '_network_function_device_config'
        for ele in body['config']:
            ele['kwargs'].update({'context': context.to_dict()})
    else:
        method_name = method_type.lower() + '_network_function_config'

    if conf.backend == 'rest':
        try:
            rc = RestApi(conf.REST.rest_server_ip, conf.REST.rest_server_port)
            resp = rc.post(method_name, body, method_type.upper())
            LOG.info(
                "%s -> POST response: (%s)" % (method_name, resp))
        except RestClientException as rce:
            LOG.error("%s -> POST request failed.Reason: %s" % (
                method_name, rce))
    else:
        LOG.info(
            "%s -> RPC request sent !" % (method_name))
        rpcClient = RPCClient(conf.RPC.topic)
        rpcClient.cctxt.cast(context, method_name,
                             body=body)


def get_response_from_configurator(conf):
    if conf.backend == 'rest':
        try:
            rc = RestApi(conf.REST.rest_server_ip, conf.REST.rest_server_port)
            resp = rc.get('get_notifications')
            rpc_cbs_data = json.loads(resp.content)
            return rpc_cbs_data
        except RestClientException as rce:
            LOG.error("get_notification -> GET request failed. Reason : %s" % (
                rce))
            return rce
    else:
        rpc_cbs_data = []
        try:
            rpcClient = RPCClient(conf.RPC.topic)
            context = n_context.Context(
                'config_agent_user', 'config_agent_tenant')
            rpc_cbs_data = rpcClient.cctxt.call(context,
                                                'get_notifications')
        except Exception as e:
            LOG.error("Exception while processing %s", e)
        return rpc_cbs_data
