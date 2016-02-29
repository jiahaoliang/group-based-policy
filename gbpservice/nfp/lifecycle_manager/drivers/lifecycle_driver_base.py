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
from gbpservice.nfp.lifecycle_manager.openstack import (
    openstack_driver
)

LOG = logging.getLogger(__name__)


class LifeCycleDriverBase(object):
    """Generic Driver class for Lifecycle handling of virtual appliances

    Does not support sharing of virtual appliance for different chains
    Does not support hotplugging interface to devices
    Launches the VM with all the management and data ports and a new VM
    is launched for each Network Service Instance
    """
    def __init__(self, supports_device_sharing=False, supports_hotplug=False,
                 max_interfaces=5):
        self.service_vendor = 'general'
        self.supports_device_sharing = supports_device_sharing
        self.supports_hotplug = supports_hotplug
        self.maximum_interfaces = max_interfaces

        # TODO[Magesh]: Try to move the following handlers to
        # Device LCM manager rather than having here in the driver
        self.identity_handler = openstack_driver.KeystoneClient()
        self.compute_handler_nova = openstack_driver.NovaClient()
        self.network_handler_gbp = openstack_driver.GBPClient()
        self.network_handler_neutron = openstack_driver.NeutronClient()

    def _is_device_sharing_supported(self):
        return self.supports_device_sharing and self.supports_hotplug

    def _create_management_interface(self, device_data):
        token = (device_data['token']
                 if device_data.get('token')
                 else self.identity_handler.get_admin_token())
        name = 'mgmt_interface'  # TODO[RPM]: Use proper name
        if device_data['network_policy'].lower() == 'gbp':
            mgmt_ptg_id = device_data['management_network_info']['id']
            mgmt_interface = self.network_handler_gbp.create_policy_target(
                                token,
                                device_data['tenant_id'],
                                mgmt_ptg_id,
                                name)
        else:
            mgmt_net_id = device_data['management_network_info']['id']
            mgmt_interface = self.network_handler_neutron.create_port(
                                token,
                                device_data['tenant_id'],
                                mgmt_net_id)

        return {'id': mgmt_interface['id'],
                'port_policy': device_data['network_policy'],
                'port_classification': 'mgmt',
                'port_type': 'NA'}

    def _delete_management_interface(self, device_data, interface):
        token = (device_data['token']
                 if device_data.get('token')
                 else self.identity_handler.get_admin_token())

        if interface['port_policy'].lower() == 'gbp':
            self.network_handler_gbp.delete_policy_target(token,
                                                          interface['id'])
        else:
            self.network_handler_neutron.delete_port(token, interface['id'])

    def _get_interfaces_for_device_create(self, device_data):
        mgmt_interface = self._create_management_interface(device_data)

        return [mgmt_interface]

    def _delete_interfaces(self, device_data, interfaces):
        for interface in interfaces:
            if interface['port_classification'].lower() == 'mgmt':
                self._delete_management_interface(device_data, interface)

    def _get_port_id(self, interface, token):
        if interface['port_policy'].lower() == 'gbp':
            pt = self.network_handler_gbp.get_policy_target(
                                token,
                                interface['id'])
            return pt['port_id']
        else:
            return interface['id']

    def _get_port_details(self, token, port_id):
        port = self.network_handler_neutron.get_port(token, port_id)
        ip = port['port']['fixed_ips'][0]['ip_address']
        mac = port['port']['mac_address']
        subnet_id = port['port']['fixed_ips'][0]['subnet_id']
        subnet = self.network_handler_neutron.get_subnet(token, subnet_id)
        cidr = subnet['subnet']['cidr']
        gateway_ip = subnet['subnet']['gateway_ip']

        return (ip, mac, cidr, gateway_ip)

    def get_network_function_device_sharing_info(self, device_data):
        if not self._is_device_sharing_supported():
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support device sharing")

        if any(key not in device_data
               for key in ['tenant_id',
                           'service_vendor']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        return {
                'filters': {
                    'tenant_id': [device_data['tenant_id']],
                    'service_vendor': [device_data['service_vendor']],
                    'status': ['ACTIVE']
                }
        }

    def select_network_function_device(self, devices, device_data):
        if not self._is_device_sharing_supported():
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support device sharing")

        if any(key not in device_data
               for key in ['ports']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        hotplug_ports_count = 1  # for provider interface (default)
        if any(port['port_classification'].lower() == 'consumer'
               for port in device_data['ports']):
            hotplug_ports_count = 2

        for device in devices:
            if (
                (device['interfaces_in_use'] + hotplug_ports_count) <=
                self.maximum_interfaces
            ):
                return device
        return None

    def create_network_function_device(self, device_data):
        if any(key not in device_data
               for key in ['tenant_id',
                           'service_vendor',
                           'compute_policy',
                           'network_policy',
                           'management_network_info',
                           'ports']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        # Not handling operations on compute policies other than 'nova' for now
        if device_data['compute_policy'] != 'nova':
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support operation"
                            " with compute policy %s"
                            % (device_data['compute_policy']))

        try:
            interfaces = self._get_interfaces_for_device_create(device_data)
        except Exception:
            LOG.error(_('Failed to get interfaces for device creation'))
            return None

        try:
            token = (device_data['token']
                     if device_data.get('token')
                     else self.identity_handler.get_admin_token())
        except Exception:
            LOG.error(_('Failed to get token, for device creation'))
            self._delete_interfaces(device_data, interfaces)
            return None

        image_name = '%s' % device_data['service_vendor'].lower()
        try:
            image_id = self.compute_handler_nova.get_image_id(
                    token,
                    device_data['tenant_id'],
                    image_name)
        except Exception:
            LOG.error(_('Failed to get image id for device creation.'
                        ' image name: %s'
                        % (image_name)))
            self._delete_interfaces(device_data, interfaces)
            return None

        flavor = 'm1.medium'
        interfaces_to_attach = []
        try:
            for interface in interfaces:
                port_id = self._get_port_id(interface, token)
                interfaces_to_attach.append({'port': port_id})

            if not self.supports_hotplug:
                for port in device_data['ports']:
                    if port['port_classification'].lower() == 'provider':
                        port_id = self._get_port_id(port, token)
                        interfaces_to_attach.append({'port': port_id})
                for port in device_data['ports']:
                    if port['port_classification'].lower() == 'consumer':
                        port_id = self._get_port_id(port, token)
                        interfaces_to_attach.append({'port': port_id})
        except Exception:
            LOG.error(_('Failed to fetch list of interfaces to attach'
                        ' for device creation'))
            self._delete_interfaces(device_data, interfaces)
            return None

        instance_name = 'instance'  # TODO[RPM]:use proper name
        try:
            instance_id = self.compute_handler_nova.create_instance(
                    token, device_data['tenant_id'],
                    image_id, flavor,
                    interfaces_to_attach, instance_name)
        except Exception:
            LOG.error(_('Failed to create %s instance'
                        % (device_data['compute_policy'])))
            self._delete_interfaces(device_data, interfaces)
            return None

        mgmt_ip_address = None
        try:
            for interface in interfaces:
                if interface['port_classification'].lower() == 'mgmt':
                    port_id = self._get_port_id(interface, token)
                    port = self.network_handler_neutron.get_port(token,
                                                                 port_id)
                    mgmt_ip_address = port['port']['fixed_ips'][0][
                                                                'ip_address']
        except Exception:
            LOG.error(_('Failed to get management port details'))
            self._delete_interfaces(device_data, interfaces)
            return None

        return {'id': instance_id,
                'name': instance_name,
                'mgmt_ip_address': mgmt_ip_address,
                'mgmt_data_ports': interfaces,
                'max_interfaces': self.maximum_interfaces,
                'interfaces_in_use': len(interfaces_to_attach),
                'description': ''}  # TODO[RPM]: what should be the description

    def delete_network_function_device(self, device_data):
        if any(key not in device_data
               for key in ['id',
                           'tenant_id',
                           'compute_policy',
                           'mgmt_data_ports']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        # Not handling operations on compute policies other than 'nova' for now
        if device_data['compute_policy'] != 'nova':
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support operation"
                            " with compute policy %s"
                            % (device_data['compute_policy']))

        try:
            token = (device_data['token']
                     if device_data.get('token')
                     else self.identity_handler.get_admin_token())
        except Exception:
            LOG.error(_('Failed to get token for device deletion'))
            return None

        try:
            self.compute_handler_nova.delete_instance(token,
                                                      device_data['tenant_id'],
                                                      device_data['id'])
        except Exception:
            LOG.error(_('Failed to delete %s instance'
                        % (device_data['compute_policy'])))

        try:
            self._delete_interfaces(device_data,
                                    device_data['mgmt_data_ports'])
        except Exception:
            LOG.error(_('Failed to delete the management data port(s)'))

    def get_network_function_device_status(self, device_data):
        if any(key not in device_data
               for key in ['id',
                           'tenant_id',
                           'compute_policy']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        # Not handling operations on compute policies other than 'nova' for now
        if device_data['compute_policy'] != 'nova':
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support operation"
                            " with compute policy %s"
                            % (device_data['compute_policy']))

        try:
            token = (device_data['token']
                     if device_data.get('token')
                     else self.identity_handler.get_admin_token())
        except Exception:
            LOG.error(_('Failed to get token for get device status operation'))
            return None

        try:
            device = self.compute_handler_nova.get_instance(
                            token,
                            device_data['tenant_id'],
                            device_data['id'])
        except Exception:
            LOG.error(_('Failed to get %s instance details'
                        % (device_data['compute_policy'])))
            return None  # TODO[RPM]: should we raise an Exception here?

        # return True if device['status'] == 'ACTIVE' else False
        return device['status']

    def plug_network_function_device_interfaces(self, device_data):
        if not self.supports_hotplug:
            raise Exception("Driver doesn't support interface hotplug")

        if any(key not in device_data
               for key in ['id',
                           'tenant_id',
                           'compute_policy',
                           'ports']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        # Not handling operations on compute policies other than 'nova' for now
        if device_data['compute_policy'] != 'nova':
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support operation"
                            " with compute policy %s"
                            % (device_data['compute_policy']))

        try:
            token = (device_data['token']
                     if device_data.get('token')
                     else self.identity_handler.get_admin_token())
        except Exception:
            LOG.error(_('Failed to get token for plug interface to device'
                        ' operation'))
            return False  # TODO[RPM]: should we raise an Exception here?

        try:
            for port in device_data['ports']:
                port_id = self._get_port_id(port, token)
                self.compute_handler_nova.attach_interface(
                            token,
                            device_data['tenant_id'],
                            device_data['id'],
                            port_id)
        except Exception:
            LOG.error(_('Failed to plug interface(s) to the device'))
            return False  # TODO[RPM]: should we raise an Exception here?
        else:
            return True

    def unplug_network_function_device_interfaces(self, device_data):
        if not self.supports_hotplug:
            raise Exception("Driver doesn't support interface hotplug")

        if any(key not in device_data
               for key in ['id',
                           'tenant_id',
                           'compute_policy',
                           'ports']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        # Not handling operations on compute policies other than 'nova' for now
        if device_data['compute_policy'] != 'nova':
            # TODO[RPM]: raise proper exception
            raise Exception("Driver doesn't support operation"
                            " with compute policy %s"
                            % (device_data['compute_policy']))

        try:
            token = (device_data['token']
                     if device_data.get('token')
                     else self.identity_handler.get_admin_token())
        except Exception:
            LOG.error(_('Failed to get token for unplug interface from device'
                        ' operation'))
            return False  # TODO[RPM]: should we raise an Exception here?

        try:
            for port in device_data['ports']:
                port_id = self._get_port_id(port, token)
                self.compute_handler_nova.detach_interface(
                            token,
                            device_data['tenant_id'],
                            device_data['id'],
                            port_id)
        except Exception:
            LOG.error(_('Failed to unplug interface(s) from the device'))
            return False  # TODO[RPM]: should we raise an Exception here?
        else:
            return True

    def get_network_function_device_healthcheck_info(self, device_data):
        if any(key not in device_data
               for key in ['id',
                           'mgmt_ip_address']):
            # TODO[RPM]: raise proper exception
            raise Exception('Not enough required data is received')

        return {
            'info': {
                'version': 1
            },
            'config': [
                {
                    'resource': 'healthmonitor',
                    'kwargs': {
                        'vmid': device_data['id'],
                        'mgmt_ip': device_data['mgmt_ip_address'],
                        'type': 'ping'
                    }
                }
            ]
        }

    def get_network_function_device_config_info(self, device_data):
        # Child class implements this
        pass