#    Copyright 2014 Rackspace
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

import octavia.common.models as models


# Amphorae Data Models

class Topology(models.BaseDataModel):

    def __init__(self, hostname=None, uuid=None, topology=None, role=None,
                 ip=None, ha_ip=None):
        self.hostname = hostname
        self.uuid = uuid
        self.topology = topology
        self.role = role
        self.ip = ip
        self.ha_ip = ha_ip


class Info(models.BaseDataModel):

    def __init__(self, hostname=None, uuid=None, version=None,
                 api_version=None):
        self.hostname = hostname
        self.uuid = uuid
        self.version = version
        self.api_version = api_version


class Details(models.BaseDataModel):

    def __init__(self, hostname=None, uuid=None, version=None,
                 api_version=None, network_tx=None, network_rx=None,
                 active=None, haproxy_count=None, cpu=None, memory=None,
                 disk=None, load=None, listeners=None, packages=None):
        self.hostname = hostname
        self.uuid = uuid,
        self.version = version
        self.api_version = api_version
        self.network_tx = network_tx
        self.network_rx = network_rx
        self.active = active
        self.haproxy_count = haproxy_count
        self.cpu = cpu
        self.memory = memory
        self.disk = disk
        self.load = load or []
        self.listeners = listeners or []
        self.packages = packages or []


class CPU(models.BaseDataModel):

    def __init__(self, total=None, user=None, system=None, soft_irq=None):
        self.total = total
        self.user = user
        self.system = system
        self.soft_irq = soft_irq


class Memory(models.BaseDataModel):

    def __init__(self, total=None, free=None, available=None, buffers=None,
                 cached=None, swap_used=None, shared=None, slab=None,
                 committed_as=None):
        self.total = total
        self.free = free
        self.available = available
        self.buffers = buffers
        self.cached = cached
        self.swap_used = swap_used
        self.shared = shared
        self.slab = slab
        self.committed_as = committed_as


class Disk(models.BaseDataModel):

    def __init__(self, used=None, available=None):
        self.used = used
        self.available = available


class ListenerStatus(models.BaseDataModel):

    def __init__(self, status=None, uuid=None, provisioning_status=None,
                 type=None, pools=None):
        self.status = status
        self.uuid = uuid
        self.provisioning_status = provisioning_status
        self.type = type
        self.pools = pools or []


class Pool(models.BaseDataModel):

    def __init__(self, uuid=None, status=None, members=None):
        self.uuid = uuid
        self.status = status
        self.members = members or []


# Network Data Models

class Interface(models.BaseDataModel):

    def __init__(self, id=None, compute_id=None, network_id=None,
                 fixed_ips=None, port_id=None):
        self.id = id
        self.compute_id = compute_id
        self.network_id = network_id
        self.port_id = port_id
        self.fixed_ips = fixed_ips


class Delta(models.BaseDataModel):

    def __init__(self, amphora_id=None, compute_id=None,
                 add_nics=None, delete_nics=None):
        self.compute_id = compute_id
        self.amphora_id = amphora_id
        self.add_nics = add_nics
        self.delete_nics = delete_nics


class Network(models.BaseDataModel):

    def __init__(self, id=None, name=None, subnets=None,
                 project_id=None, admin_state_up=None, mtu=None,
                 provider_network_type=None,
                 provider_physical_network=None,
                 provider_segmentation_id=None,
                 router_external=None):
        self.id = id
        self.name = name
        self.subnets = subnets
        self.project_id = project_id
        self.admin_state_up = admin_state_up
        self.provider_network_type = provider_network_type
        self.provider_physical_network = provider_physical_network
        self.provider_segmentation_id = provider_segmentation_id
        self.router_external = router_external
        self.mtu = mtu


class Subnet(models.BaseDataModel):

    def __init__(self, id=None, name=None, network_id=None, project_id=None,
                 gateway_ip=None, cidr=None, ip_version=None):
        self.id = id
        self.name = name
        self.network_id = network_id
        self.project_id = project_id
        self.gateway_ip = gateway_ip
        self.cidr = cidr
        self.ip_version = ip_version


class Port(models.BaseDataModel):

    def __init__(self, id=None, name=None, device_id=None, device_owner=None,
                 mac_address=None, network_id=None, status=None,
                 project_id=None, admin_state_up=None, fixed_ips=None,
                 network=None):
        self.id = id
        self.name = name
        self.device_id = device_id
        self.device_owner = device_owner
        self.mac_address = mac_address
        self.network_id = network_id
        self.status = status
        self.project_id = project_id
        self.admin_state_up = admin_state_up
        self.fixed_ips = fixed_ips or []
        self.network = network

    def get_subnet_id(self, fixed_ip_address):
        for fixed_ip in self.fixed_ips:
            if fixed_ip.ip_address == fixed_ip_address:
                return fixed_ip.subnet_id


class FixedIP(models.BaseDataModel):

    def __init__(self, subnet_id=None, ip_address=None, subnet=None):
        self.subnet_id = subnet_id
        self.ip_address = ip_address
        self.subnet = subnet


class AmphoraNetworkConfig(models.BaseDataModel):

    def __init__(self, amphora=None, vip_subnet=None, vip_port=None,
                 vrrp_subnet=None, vrrp_port=None, ha_subnet=None,
                 ha_port=None):
        self.amphora = amphora
        self.vip_subnet = vip_subnet
        self.vip_port = vip_port
        self.vrrp_subnet = vrrp_subnet
        self.vrrp_port = vrrp_port
        self.ha_subnet = ha_subnet
        self.ha_port = ha_port


