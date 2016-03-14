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

from oslo_log import log as logging

from gbpservice.nfp._i18n import _
from gbpservice.nfp.common import exceptions
from gbpservice.nfp.lifecycle_manager.drivers.lifecycle_driver_base import (
    LifeCycleDriverBase
)

LOG = logging.getLogger(__name__)


class HaproxyLifeCycleDriver(LifeCycleDriverBase):
    """Haproxy Service VM Driver for Lifecycle handling of virtual appliances

    Overrides methods from HotplugSupportedLifeCycleDriver class for performing
    things specific to Haproxy service VM
    """
    def __init__(self, supports_device_sharing=True, supports_hotplug=True,
                 max_interfaces=10):
        super(HaproxyLifeCycleDriver, self).__init__(
            supports_device_sharing=supports_device_sharing,
            supports_hotplug=supports_hotplug,
            max_interfaces=max_interfaces)
        self.service_vendor = 'Haproxy'

    def get_network_function_device_config_info(self, device_data):
        if (
            any(key not in device_data
                for key in ['service_vendor',
                            'mgmt_ip_address',
                            'ports']) or

            any(key not in port
                for port in device_data['ports']
                for key in ['id',
                            'port_classification',
                            'port_policy'])
        ):
            raise exceptions.IncompleteData()

        try:
            token = (device_data['token']
                     if device_data.get('token')
                     else self.identity_handler.get_admin_token())
        except Exception:
            self._increment_stats_counter('keystone_token_get_failures')
            LOG.error(_('Failed to get token'
                        ' for get device config info operation'))
            return None

        provider_ip = None
        provider_mac = None
        provider_cidr = None
        consumer_ip = None
        consumer_mac = None
        consumer_cidr = None
        consumer_gateway_ip = None

        for port in device_data['ports']:
            if port['port_classification'] == 'provider':
                try:
                    port_id = self._get_port_id(port, token)
                    (provider_ip, provider_mac,
                     provider_cidr, dummy) = self._get_port_details(token,
                                                                    port_id)
                except Exception:
                    self._increment_stats_counter('port_details_get_failures')
                    LOG.error(_('Failed to get provider port details'
                                ' for get device config info operation'))
                    return None
            elif port['port_classification'] == 'consumer':
                try:
                    port_id = self._get_port_id(port, token)
                    (consumer_ip, consumer_mac,
                     consumer_cidr,
                     consumer_gateway_ip) = self._get_port_details(token,
                                                                   port_id)
                except Exception:
                    self._increment_stats_counter('port_details_get_failures')
                    LOG.error(_('Failed to get consumer port details'
                                ' for get device config info operation'))
                    return None

        return {
            'info': {
                'version': 1
            },
            'config': [
                {
                    'resource': 'interfaces',
                    'kwargs': {
                        'mgmt_ip': device_data['mgmt_ip_address'],
                        'service_vendor': device_data['service_vendor'],
                        'provider_ip': provider_ip,
                        'provider_cidr': provider_cidr,
                        'provider_interface_position': 2,
                        'stitching_ip': consumer_ip,
                        'stitching_cidr': consumer_cidr,
                        'stitching_interface_position': 3,
                        'provider_mac': provider_mac,
                        'stitching_mac': consumer_mac
                    }
                },
                {
                    'resource': 'routes',
                    'kwargs': {
                        'mgmt_ip': device_data['mgmt_ip_address'],
                        'service_vendor': device_data['service_vendor'],
                        'source_cidrs': ([provider_cidr, consumer_cidr]
                                         if consumer_cidr
                                         else [provider_cidr]),
                        'destination_cidr': consumer_cidr,
                        'gateway_ip': consumer_gateway_ip,
                        'provider_interface_position': 2
                    }
                }
            ]
        }