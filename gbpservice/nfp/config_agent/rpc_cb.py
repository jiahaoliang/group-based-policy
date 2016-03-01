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

import importlib
from gbpservice.nfp.core import poll as core_pt
from gbpservice.nfp.config_agent import RestClientOverUnix as rc
from gbpservice.nfp.config_agent import loadbalancer as lb
from gbpservice.nfp.config_agent import firewall as fw
from gbpservice.nfp.config_agent import vpn as vpn
from gbpservice.nfp.config_agent import generic as gc
from gbpservice.nfp.config_agent.common import *
import json
LOG = logging.getLogger(__name__)

CONFIG_AGENT_MODULES = {'loadbalancer': lb,
                        'firewall': fw,
                        'vpn': vpn,
                        'generic': gc}


class RpcCallback(core_pt.PollEventDesc):

    def __init__(self, sc):
        self._sc = sc

    def handle_event(self, ev):
        self._sc.poll_event(ev)

    def _method_handler(self, rpc_cb):
        if rpc_cb['receiver'] == 'orchestrator':
            mod = CONFIG_AGENT_MODULES['generic']
            mod_method = getattr(mod, rpc_cb['method'])
            mod_method(rpc_cb['resource'], rpc_cb['kwargs'])
        else:
            mod = CONFIG_AGENT_MODULES[rpc_cb['resource']]
            mod_method = getattr(mod, rpc_cb['method'])
            mod_method(**rpc_cb['kwargs'])

    @core_pt.poll_event_desc(event='PULL_RPC_NOTIFICATIONS', spacing=1)
    def rpc_pull_event(self, ev):
        try :
            print "coming for polling request"
            resp, rpc_cbs_data = rc.get('get_notifications')
            rpc_cbs_data = json.loads(rpc_cbs_data)
            '''
            response_data = [
                {'receiver': <neutron/orchestrator>,
                 'resource': <firewall/vpn/loadbalancer/orchestrator>,
                 'method': <notification method name>,
                 'kwargs': <notification method arguments>
            },
            ]
            '''
            if not rpc_cbs_data :
                LOG.info("get_notification -> GET request: Empty")
            else :
                rpc_cbs = rpc_cbs_data
                for rpc_cb in rpc_cbs:
                    if not rpc_cb :
                        LOG.info("Receiver Response: Empty")
                        continue
                    try:
                        self._method_handler(rpc_cb)
                    except AttributeError:
                        import sys
                        import traceback
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        print traceback.format_exception(exc_type, exc_value, exc_traceback)

                        LOG.error("AttributeError while handling message" % (
                            rpc_cb))
                    except Exception as e:
                        LOG.error("Generic exception (%s) \
                            while handling message (%s)" % (e, rpc_cb))
        except rc.RestClientException as rce:
            LOG.error("get_notification -> GET request failed. Reason : %s" % (
                rce))
