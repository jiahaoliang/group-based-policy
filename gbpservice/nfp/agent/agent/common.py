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
from gbpservice.nfp.agent.agent import topics
from neutron.common import rpc as n_rpc
from neutron.plugins.common import constants
from neutron.common import topics as n_topics
from neutron.common import constants as n_constants
LOG = logging.getLogger(__name__)
Version = 'v1'  # v1/v2/v3#


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


def prepare_request_data(resource, kwargs, service_type):

    request_data = {'info': {
        'version': Version,
        'service_type': service_type
    },

        'config': [{
            'resource': resource,
            'kwargs': kwargs
        }]
    }

    return request_data

def _filter_data(routers, networks, filters):
    tenant_id = filters['tenant_id'][0]
    _filtered_routers = []
    _filtered_subnets = []
    _filtered_ports = []
    for router in routers :
        if router['tenant_id'] == tenant_id :
            _filtered_routers.append(router)
    for network in networks :
        subnets = network['subnets']
        ports = network['ports']
        for subnet in subnets :
            if subnet['tenant_id'] == tenant_id:
                _filtered_subnets.append(subnet)
        for port in ports :
            if port['tenant_id'] == tenant_id:
                _filtered_ports.append(port)

    return {'subnets': _filtered_subnets,
            'routers': _filtered_routers,
            'ports': _filtered_ports}

def get_core_context(context, filters, host):
    routers = get_routers(context, host)
    networks = get_networks(context, host)
    return _filter_data(routers, networks, filters)

def get_routers(context, host):
    _target = target.Target(topic=n_topics.L3PLUGIN, version='1.0')
    client = n_rpc.get_client(_target)
    cctxt = client.prepare()
    return cctxt.call(context, 'sync_routers', host=host,
                      router_ids=None)

def get_networks(context, host):
    _target = target.Target(
                topic=n_topics.PLUGIN,
                namespace=n_constants.RPC_NAMESPACE_DHCP_PLUGIN,
                version='1.0')
    client = n_rpc.get_client(_target)
    cctxt = client.prepare(version='1.1')
    return cctxt.call(context, 'get_active_networks_info',
                          host=host)
