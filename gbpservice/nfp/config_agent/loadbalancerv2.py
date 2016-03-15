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

from gbpservice.nfp.config_agent.common import *
from gbpservice.nfp.config_agent import RestClientOverUnix as rc
from neutron_lbaas.agent import agent_manager
from neutron_lbaas.agent import agent_api
from gbpservice.nfp.config_agent import topics

LOG = logging.getLogger(__name__)


class Lbv2Agent(agent_manager.LbaasAgentManager):
    def __init__(self, conf, sc):
        super(Lbv2Agent, self).__init__(conf)
        self.plugin_rpc = agent_api.LbaasAgentApi(
            topics.LBv2_NFP_CONFIGAGENT_TOPIC,
            self.context,
            self.conf.host
        )
