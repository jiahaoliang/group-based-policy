# Copyright (c) 2013 OpenStack Foundation
# All Rights Reserved.
#
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

import contextlib

from neutron.services.firewall.agents import firewall_agent_api as api
#from neutron.services.firewall.drivers import fwaas_base as base_driver
from neutron_fwaas.services.firewall.drivers import fwaas_base as base_driver

class NoOpFwaasDriver(base_driver.FwaasDriverBase):

    """Noop Fwaas Driver.

    Firewall driver which does nothing.
    This driver is for disabling Fwaas functionality.
    """

    def create_firewall(self, agent_mode, apply_list, firewall):
        pass

    def delete_firewall(self, agent_mode, apply_list, firewall):
        pass

    def update_firewall(self, agent_mode, apply_list, firewall):
        pass

    def apply_default_policy(self, apply_list, firewall):
        pass


