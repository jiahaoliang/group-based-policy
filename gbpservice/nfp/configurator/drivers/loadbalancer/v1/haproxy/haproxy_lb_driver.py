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

import ast

from gbpservice.nfp.configurator.drivers.base import base_driver
from gbpservice.nfp.configurator.drivers.loadbalancer.v1.haproxy import (
                                                    haproxy_rest_client)
from gbpservice.nfp.configurator.lib import constants as common_const
from gbpservice.nfp.configurator.lib import lb_constants
from oslo_log import log as logging

DRIVER_NAME = 'loadbalancer'
PROTOCOL_MAP = {
    lb_constants.PROTOCOL_TCP: 'tcp',
    lb_constants.PROTOCOL_HTTP: 'http',
    lb_constants.PROTOCOL_HTTPS: 'https',
}
BALANCE_MAP = {
    lb_constants.LB_METHOD_ROUND_ROBIN: 'roundrobin',
    lb_constants.LB_METHOD_LEAST_CONNECTIONS: 'leastconn',
    lb_constants.LB_METHOD_SOURCE_IP: 'source'
}
REQUEST_RETRIES = 0
REQUEST_TIMEOUT = 120


LOG = logging.getLogger(__name__)


""" Loadbalancer generic configuration driver for handling device
configuration requests.

"""


class LbGenericConfigDriver(object):
    """
    Driver class for implementing loadbalancer configuration
    requests from Orchestrator.
    """

    def __init__(self):
        pass

    def configure_interfaces(self, context, resource_data):
        """ Configure interfaces for the service VM.

        Calls static IP configuration function and implements
        persistent rule addition in the service VM.
        Issues REST call to service VM for configuration of interfaces.

        :param context: neutron context
        :param resource_data: a dictionary of loadbalancer objects
        send by neutron plugin

        Returns: SUCCESS/Failure message with reason.

        """

        mgmt_ip = resource_data['mgmt_ip']

        try:
            result_log_forward = self._configure_log_forwarding(
                lb_constants.REQUEST_URL, mgmt_ip,
                self.port)
        except Exception as err:
            msg = ("Failed to configure log forwarding for service at %s. "
                   "Error: %s" % (mgmt_ip, err))
            LOG.error(msg)
            return msg
        else:
            if result_log_forward == common_const.UNHANDLED:
                pass
            elif result_log_forward != lb_constants.STATUS_SUCCESS:
                msg = ("Failed to configure log forwarding for service at %s. "
                       "Error: %s" % (mgmt_ip, err))
                LOG.error(msg)
                return result_log_forward
            else:
                msg = ("Configured log forwarding for service at %s. "
                       "Result: %s" % (mgmt_ip, result_log_forward))
                LOG.info(msg)

        return lb_constants.STATUS_SUCCESS


class HaproxyOnVmDriver(LbGenericConfigDriver, base_driver.BaseDriver):
    service_type = 'loadbalancer'
    service_vendor = 'haproxy'
    pool_to_device = {}

    def __init__(self, plugin_rpc=None, conf=None):
        self.plugin_rpc = plugin_rpc
        self.conf = conf
        self.timeout = 30
        self.port = lb_constants.HAPROXY_AGENT_LISTEN_PORT
        super(HaproxyOnVmDriver, self).__init__()

    def _get_rest_client(self, ip_addr):
        client = haproxy_rest_client.HttpRequests(
                            ip_addr, self.port,
                            REQUEST_RETRIES, REQUEST_TIMEOUT)
        return client

    def _get_device_for_pool(self, pool_id, context):
        device = HaproxyOnVmDriver.pool_to_device.get(pool_id, None)
        if device is not None:
            return device

        logical_device = self.plugin_rpc.get_logical_device(pool_id,
                                                            context)
        vip = logical_device.get('vip', None)
        if vip is None:
            return None
        else:
            vip_desc = ast.literal_eval(vip['description'])
            device = vip_desc['floating_ip']
            if device:
                HaproxyOnVmDriver.pool_to_device[pool_id] = device
                return device

    def _get_interface_mac(self, vip):
        vip_desc = ast.literal_eval(vip['description'])
        return vip_desc['provider_interface_mac']

    def _expand_expected_codes(self, codes):
        """Expand the expected code string in set of codes.

        200-204 -> 200, 201, 202, 204
        200, 203 -> 200, 203
        """

        retval = set()
        for code in codes.replace(',', ' ').split(' '):
            code = code.strip()
            if not code:
                continue
            elif '-' in code:
                low, hi = code.split('-')[:2]
                retval.update(str(i) for i in xrange(int(low), int(hi) + 1))
            else:
                retval.add(code)
        return retval

    def _prepare_haproxy_frontend(self, vip):
        # Prepare the frontend request body
        vip_ip = vip['address']
        vip_port_number = vip['protocol_port']
        protocol = vip['protocol']

        frontend = {
            'option': {},
            'bind': '%s:%d' % (vip_ip, vip_port_number),
            'mode': PROTOCOL_MAP[protocol],
            'default_backend': "bck:%s" % vip['pool_id']
        }
        if vip['connection_limit'] >= 0:
            frontend.update({'maxconn': '%s' % vip['connection_limit']})
        if protocol in [lb_constants.PROTOCOL_HTTP,
                        lb_constants.PROTOCOL_HTTPS]:
            frontend['option'].update({'httplog': True})
        else:
            frontend['option'].update({'tcplog': True})
        try:
            if protocol == lb_constants.PROTOCOL_HTTP:
                frontend['option'].update({'forwardfor': True})
            provider_interface_mac = self._get_interface_mac(vip)
            frontend.update({'provider_interface_mac': provider_interface_mac})
        except Exception as e:
            raise e
        return frontend

    def _prepare_haproxy_backend(self, pool, context):
        logical_device = self.plugin_rpc.get_logical_device(pool['id'],
                                                            context)
        protocol = pool['protocol']
        lb_method = pool['lb_method']
        monitor = None
        for monitor in logical_device['healthmonitors']:
            break
        server_addon = ''

        backend = {
            'mode': '%s' % PROTOCOL_MAP[protocol],
            'balance': '%s' % BALANCE_MAP.get(lb_method, 'roundrobin'),
            'option': {},
            'timeout': {},
            'server': {}
        }
        try:
            if protocol == lb_constants.PROTOCOL_HTTP:
                backend['option'].update({'forwardfor': True})

            # health monitor options
            if monitor:
                # server addon options
                server_addon = ('check inter %(delay)ds fall %(max_retries)d'
                                % monitor)

                backend['timeout'].update({'check': '%ds'
                                           % monitor['timeout']})
                if monitor['type'] in (lb_constants.HEALTH_MONITOR_HTTP,
                                       lb_constants.HEALTH_MONITOR_HTTPS):
                    backend['option'].update(
                        {'httpchk': '%(http_method)s %(url_path)s' % monitor})
                    backend.update({'http-check expect': 'rstatus %s'
                                    % '|'.join(
                                        self._expand_expected_codes(
                                            monitor['expected_codes']))})
                if monitor['type'] == lb_constants.HEALTH_MONITOR_HTTPS:
                    backend['option'].update({'ssl-hello-chk': True})

            # session persistance options
            vip = logical_device['vip']
            persistence = vip.get('session_persistence')
            if persistence:
                if persistence['type'] == 'SOURCE_IP':
                    backend.update({'stick-table type': 'ip size 10k'})
                    backend.update({'stick on': 'src'})
                elif persistence['type'] == 'HTTP_COOKIE':
                    backend.update({'cookie': 'SRV insert indirect nocache'})
                elif (persistence['type'] == 'APP_COOKIE' and
                      persistence.get('cookie_name')):
                    backend.update({'appsession': '%s len 56 timeout 3h' %
                                    persistence['cookie_name']})

            # server options
            for member in logical_device['members']:
                backend['server'].update(
                    {"srvr:%s" % member['id']: [
                            '%(address)s:%(protocol_port)s' % member,
                            'weight %(weight)s' % member, server_addon]}
                )
                if (vip.get('session_persistence') and
                        vip['session_persistence']['type'] == 'HTTP_COOKIE'):
                            backend['server'][member['id']].append(
                                'cookie %d'
                                % logical_device['members'].index(
                                                            member['id']))

            return backend
        except Exception as e:
            raise e

    def _prepare_haproxy_backend_with_member(self, member, backend, context):
        logical_device = self.plugin_rpc.get_logical_device(member['pool_id'],
                                                            context)
        vip = logical_device['vip']
        monitor = None
        # chose first monitor
        for monitor in logical_device['healthmonitors']:
            break

        # update backend with the new server
        if monitor:
            server_addon = ('check inter %(delay)ds fall %(max_retries)d'
                            % monitor)
        else:
            server_addon = ''
        try:
            backend['server'].update(
                {'srvr:%s' % member['id']: [
                    '%(address)s:%(protocol_port)s' % member,
                    'weight %(weight)s' % member, server_addon]})
        except Exception as e:
            raise e
        if (vip.get('session_persistence') and
                vip['session_persistence']['type'] == 'HTTP_COOKIE'):
            backend['server'][member['id']].append(
                'cookie %d' % logical_device['members'].index(member['id']))

        return backend

    def _prepare_backend_adding_health_monitor_to_pool(self, health_monitor,
                                                       pool_id,
                                                       backend):
        # server addon options
        server_addon = ('check inter %(delay)ds fall %(max_retries)d'
                        % health_monitor)
        for server in backend['server'].itervalues():
            total_lines = len(server)
            for index, line in enumerate(server):
                if 'check' in line:
                    server[index] = server_addon
                    break
                elif total_lines == index + 1:
                    server.append(server_addon)

        try:
            backend['timeout'].update({'check': '%ds'
                                       % health_monitor['timeout']})
            if health_monitor['type'] in (lb_constants.HEALTH_MONITOR_HTTP,
                                          lb_constants.HEALTH_MONITOR_HTTPS):
                backend['option'].update(
                    {'httpchk': ('%(http_method)s %(url_path)s'
                                 % health_monitor)})
                backend.update({'http-check expect': 'rstatus %s' % (
                                '|'.join(self._expand_expected_codes(
                                    health_monitor['expected_codes'])))})
            if health_monitor['type'] == lb_constants.PROTOCOL_HTTPS:
                backend['option'].update({'ssl-hello-chk': True})
        except Exception as e:
            raise e
        return backend

    def _prepare_backend_deleting_health_monitor_from_pool(self,
                                                           health_monitor,
                                                           pool_id,
                                                           backend, context):
        logical_device = self.plugin_rpc.get_logical_device(pool_id, context)
        remaining_hms_type = []
        for monitor in logical_device['healthmonitors']:
            if health_monitor['type'] != monitor['type']:
                remaining_hms_type.append(monitor['type'])

        # Remove http, https corresponding configuration
        # Not removing http or https configuration if any 1 of them,
        # present in remaining hms type.
        try:
            if ((lb_constants.HEALTH_MONITOR_HTTP and
                    lb_constants.HEALTH_MONITOR_HTTPS)
                not in remaining_hms_type and health_monitor['type'] in
                    (lb_constants.HEALTH_MONITOR_HTTP,
                     lb_constants.HEALTH_MONITOR_HTTPS)):
                del backend['option']['httpchk']
                del backend['http-check expect']
                if health_monitor['type'] == lb_constants.HEALTH_MONITOR_HTTPS:
                    del backend['option']['ssl-hello-chk']

            server_addon = ('check inter %(delay)ds fall %(max_retries)d'
                            % health_monitor)
            for server in backend['server'].itervalues():
                for index, line in enumerate(server):
                    if 'check' in line:
                        if len(logical_device['healthmonitors']) == 0:
                            del server[index]
                        else:
                            server[index] = server_addon
                        break

            if len(logical_device['healthmonitors']) == 0:
                del backend['timeout']['check']
        except Exception as e:
            raise e
        return backend

    def _prepare_backend_updating_health_monitor_for_pool(self, health_monitor,
                                                          pool_id,
                                                          backend):
        # update backend by updatinig the health monitor
        # server addon options
        server_addon = ('check inter %(delay)ds fall %(max_retries)d'
                        % health_monitor)
        for server in backend['server'].itervalues():
            health_chk_index_in_srvr_list = 0
            for line in server:
                if 'check' in line:
                    server[health_chk_index_in_srvr_list] = server_addon
                    break
                else:
                    health_chk_index_in_srvr_list += 1

        try:
            backend['timeout'].update({'check': '%ds'
                                       % health_monitor['timeout']})
            if health_monitor['type'] in (lb_constants.HEALTH_MONITOR_HTTP,
                                          lb_constants.HEALTH_MONITOR_HTTPS):
                backend['option'].update(
                    {'httpchk': ('%(http_method)s %(url_path)s'
                                 % health_monitor)})
                backend.update({'http-check expect': 'rstatus %s' % '|'.join(
                                    self._expand_expected_codes(
                                        health_monitor['expected_codes']))})
            if health_monitor['type'] == lb_constants.HEALTH_MONITOR_HTTPS:
                backend['option'].update({'ssl-hello-chk': True})
        except Exception as e:
            raise e

        return backend

    def _create_vip(self, vip, device_addr):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            # Prepare the frontend request body
            frontend = self._prepare_haproxy_frontend(vip)

            body = {"frnt:%s" % vip['id']: frontend}

            # Send REST API request to Haproxy agent on VM
            client.create_resource("frontend", body)
        except Exception as e:
            raise e

    def _delete_vip(self, vip, device_addr):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            # Send REST API request to Haproxy agent on VM
            client.delete_resource("frontend/frnt:%s" % vip['id'])
        except Exception as e:
            raise e

    def _create_pool(self, pool, device_addr, context):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            # Prepare the backend request body
            backend = self._prepare_haproxy_backend(pool, context)
            body = {'bck:%s' % pool['id']: backend}

            # Send REST API request to Haproxy agent on VM
            client.create_resource("backend", body)
        except Exception as e:
            raise e

    def _delete_pool(self, pool, device_addr):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            # Send REST API request to Haproxy agent on VM
            client.delete_resource("backend/bck:%s" % pool['id'])
        except Exception as e:
            raise e

    def _create_member(self, member, device_addr, context):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            # get backend
            backend = client.get_resource("backend/bck:%s"
                                          % member['pool_id'])

            backend = self._prepare_haproxy_backend_with_member(
                                                    member, backend, context)

            # Send REST API request to Haproxy agent on VM
            client.update_resource("backend/bck:%s" % member['pool_id'],
                                   backend)
        except Exception as e:
            raise e

    def _delete_member(self, member, device_addr):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            # get backend
            backend = client.get_resource("backend/bck:%s"
                                          % member['pool_id'])

            # update backend with the server deleted from that
            del backend['server']['srvr:%s' % member['id']]

            # Send REST API request to Haproxy agent on VM
            client.update_resource("backend/bck:%s" % member['pool_id'],
                                   backend)
        except Exception as e:
            raise e

    def _create_pool_health_monitor(self, hm, pool_id, device_addr):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            backend = client.get_resource("backend/bck:%s" % pool_id)

            # server addon options
            backend = self._prepare_backend_adding_health_monitor_to_pool(
                                                                    hm,
                                                                    pool_id,
                                                                    backend)

            client.update_resource("backend/bck:%s" % pool_id, backend)
        except Exception as e:
            raise e

    def _delete_pool_health_monitor(self, hm, pool_id,
                                    device_addr, context):
        # create REST client object
        try:
            client = self._get_rest_client(device_addr)

            backend = client.get_resource("backend/bck:%s" % pool_id)

            backend = self._prepare_backend_deleting_health_monitor_from_pool(
                                                                    hm,
                                                                    pool_id,
                                                                    backend,
                                                                    context)
            client.update_resource("backend/bck:%s" % pool_id, backend)
        except Exception as e:
            raise e

    @classmethod
    def get_name(self):
        return DRIVER_NAME

    def deploy_instance(self, logical_config):
        # do actual deploy only if vip and pool are configured and active
        if (not logical_config or
                'vip' not in logical_config or
                (logical_config['vip']['status'] not in
                 lb_constants.ACTIVE_PENDING_STATUSES) or
                not logical_config['vip']['admin_state_up'] or
                (logical_config['pool']['status'] not in
                 lb_constants.ACTIVE_PENDING_STATUSES) or
                not logical_config['pool']['admin_state_up']):
            return

        try:
            device_addr = self._get_device_for_pool(
                                            logical_config['pool']['id'])

            self._create_pool(logical_config['pool'], device_addr)
            self._create_vip(logical_config['vip'], device_addr)
            for member in logical_config['members']:
                self._create_member(member, device_addr)
            for hm in logical_config['healthmonitors']:
                self._create_pool_health_monitor(hm,
                                                 logical_config['pool']['id'],
                                                 device_addr)
        except Exception as e:
            msg = ("Failed to deploy instance. %s"
                   % str(e).capitalize())
            LOG.error(msg)
            raise e

    def undeploy_instance(self, pool_id, context):
        try:
            device_addr = self._get_device_for_pool(pool_id, context)
            logical_device = self.plugin_rpc.get_logical_device(pool_id,
                                                                context)

            self._delete_vip(logical_device['vip'], device_addr)
            self._delete_pool(logical_device['pool'], device_addr)
        except Exception as e:
            msg = ("Failed to undeploy instance. %s"
                   % str(e).capitalize())
            LOG.error(msg)
            raise e

    def remove_orphans(self, pol_ids):
        raise NotImplementedError

    def get_stats(self, pool_id):
        stats = {}
        try:
            # if pool is not known, do nothing
            device = HaproxyOnVmDriver.pool_to_device.get(pool_id, None)
            if device is None:
                return stats

            device_addr = self._get_device_for_pool(pool_id, None)

            # create REST client object
            client = self._get_rest_client(device_addr)

            stats = client.get_resource('stats/%s' % pool_id)

            for key, value in stats.get('members', {}).items():
                if key.find(":") != -1:
                    member_id = key[key.find(":") + 1:]
                    del stats['members'][key]
                    stats['members'][member_id] = value
        except Exception as e:
            msg = ("Failed to get stats. %s"
                   % str(e).capitalize())
            LOG.error(msg)
            raise e

        return stats

    def create_vip(self, vip, context):
        msg = (" create vip [vip=%s ]" % (vip))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(vip['pool_id'], context)
            logical_device = self.plugin_rpc.get_logical_device(vip['pool_id'],
                                                                context)

            self._create_pool(logical_device['pool'], device_addr, context)
            for member in logical_device['members']:
                self._create_member(member, device_addr, context)
            for hm in logical_device['healthmonitors']:
                self._create_pool_health_monitor(hm,
                                                 vip['pool_id'], device_addr)

            self._create_vip(vip, device_addr)
        except Exception as e:
            msg = ("Failed to create vip %s. %s"
                   % (vip['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Created vip %s." % vip['id'])
            LOG.info(msg)

    def update_vip(self, old_vip, vip, context):
        msg = (" update vip [old_vip=%s, vip=%s ]" % (old_vip, vip))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(old_vip['pool_id'],
                                                    context)

            # if old_vip is either not having associated to pool
            # or not created
            if (not old_vip['pool_id'] or
                    device_addr is None):
                return

            # is vip's pool changed
            if not vip['pool_id'] == old_vip['pool_id']:
                msg = (" vip pool id changed. first deleting old vip "
                       " [old pool=%s, new pool=%s]" % (old_vip['pool_id'],
                                                        vip['pool_id']))
                LOG.info(msg)
                # Delete the old VIP
                self._delete_vip(old_vip, device_addr)

                # Create the new VIP along with pool
                logical_device = self.plugin_rpc.get_logical_device(
                                                            vip['pool_id'],
                                                            context)
                pool = logical_device['pool']
                self._create_pool(pool, device_addr)
                self._create_vip(vip, device_addr)
                return

            # create REST client object
            client = self._get_rest_client(device_addr)

            # Prepare the frontend request body
            body = self._prepare_haproxy_frontend(vip)

            # Send REST API request to Haproxy agent on VM
            client.update_resource("frontend/frnt:%s" % vip['id'], body)
        except Exception as e:
            msg = ("Failed to update vip %s. %s"
                   % (vip['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Updated vip %s." % vip['id'])
            LOG.info(msg)

    def delete_vip(self, vip, context):
        msg = (" delete vip [vip=%s ]" % (vip))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(vip['pool_id'], context)
            logical_device = self.plugin_rpc.get_logical_device(vip['pool_id'],
                                                                context)

            # Delete vip from VM
            self._delete_vip(vip, device_addr)

            # Delete pool from VM
            pool = logical_device['pool']
            self._delete_pool(pool, device_addr)
        except Exception as e:
            msg = ("Failed to delete vip %s. %s"
                   % (vip['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Deleted vip %s." % vip['id'])
            LOG.info(msg)

    def create_pool(self, pool, context):
        # nothing to do here because a pool needs a vip to be useful
        msg = ("create pool [pool=%s]" % (pool))
        LOG.info(msg)
        pass

    def update_pool(self, old_pool, pool, context):
        msg = ("update pool [old_pool=%s, pool=%s]" % (old_pool, pool))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(pool['id'], context)
            if (pool['vip_id'] and
                    device_addr is not None):
                # create REST client object
                client = self._get_rest_client(device_addr)
                # Prepare the backend request body for create request
                backend = self._prepare_haproxy_backend(pool, context)
                body = backend

                # Send REST API request to Haproxy agent on VM
                client.update_resource("backend/bck:%s" % pool['id'], body)
        except Exception as e:
            msg = ("Failed to update pool from %s to %s. %s"
                   % (old_pool['id'], pool['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Updated pool from %s to %s."
                   % (old_pool['id'], pool['id']))
            LOG.info(msg)

    def delete_pool(self, pool, context):
        # if pool is not known, do nothing
        msg = ("delete pool [pool=%s]" % (pool))
        LOG.info(msg)
        try:
            device = HaproxyOnVmDriver.pool_to_device.get(pool['id'], None)
            if device is None:
                return

            device_addr = self._get_device_for_pool(pool['id'], context)
            if (pool['vip_id'] and
                    device_addr):
                self._delete_pool(pool, device_addr)
        except Exception as e:
            msg = ("Failed to delete pool: %s. %s"
                   % (pool['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Deleted pool: %s." % pool['id'])
            LOG.info(msg)

    def create_member(self, member, context):
        msg = (" create member [member=%s] " % (member))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(member['pool_id'], context)
            if device_addr is not None:
                self._create_member(member, device_addr, context)
        except Exception as e:
            msg = ("Failed to create member %s. %s"
                   % (member['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Created member %s." % member['id'])
            LOG.info(msg)

    def update_member(self, old_member, member, context):
        msg = (" update member [old_member=%s, member=%s] " % (old_member,
                                                               member))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(old_member['pool_id'],
                                                    context)
            if device_addr is not None:
                self._delete_member(old_member, device_addr)

            # create the member (new)
            device_addr = self._get_device_for_pool(member['pool_id'], context)
            if device_addr is not None:
                self._create_member(member, device_addr, context)
        except Exception as e:
            msg = ("Failed to update member %s. %s"
                   % (member['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("updated member %s." % member['id'])
            LOG.info(msg)

    def delete_member(self, member, context):
        msg = (" delete member [member=%s] " % (member))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(member['pool_id'],
                                                    context)
            if device_addr is not None:
                self._delete_member(member, device_addr)
        except Exception as e:
            msg = ("Failed to delete member %s. %s"
                   % (member['id'], str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Deleted member %s." % member['id'])
            LOG.info(msg)

    def create_pool_health_monitor(self, health_monitor, pool_id, context):
        # create the health_monitor
        msg = ("create pool health monitor [hm=%s, pool_id=%s]"
               % (health_monitor, pool_id))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(pool_id, context)
            if device_addr is not None:
                self._create_pool_health_monitor(health_monitor, pool_id,
                                                 device_addr)
        except Exception as e:
            msg = ("Failed to create pool health monitor: %s with "
                   "pool ID: %s. %s"
                   % (str(health_monitor), pool_id, str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Created pool health monitor: %s with pool ID: %s"
                   % (str(health_monitor), pool_id))
            LOG.info(msg)

    def update_pool_health_monitor(self, old_health_monitor, health_monitor,
                                   pool_id, context):
        msg = ("update pool health monitor [old_hm=%s, hm=%s, pool_id=%s]"
               % (old_health_monitor, health_monitor, pool_id))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(pool_id, context)
            if device_addr is not None:
                # create REST client object
                client = self._get_rest_client(device_addr)

                backend = client.get_resource("backend/bck:%s" % pool_id)

                # update backend deleting the health monitor from it
                # server addon options
                backend = (
                    self._prepare_backend_updating_health_monitor_for_pool(
                                            health_monitor,
                                            pool_id,
                                            backend))

                client.update_resource("backend/bck:%s" % pool_id, backend)
        except Exception as e:
            msg = ("Failed to update health monitor from %s to "
                   "%s for pool: %s. %s"
                   % (str(old_health_monitor), str(health_monitor),
                      pool_id, str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Updated health monitor from %s to %s for pool: %s"
                   % (str(old_health_monitor), str(health_monitor), pool_id))
            LOG.info(msg)

    def delete_pool_health_monitor(self, health_monitor, pool_id, context):
        msg = ("delete pool health monitor [hm=%s, pool_id=%s]"
               % (health_monitor, pool_id))
        LOG.info(msg)
        try:
            device_addr = self._get_device_for_pool(pool_id, context)
            if device_addr is not None:
                self._delete_pool_health_monitor(health_monitor, pool_id,
                                                 device_addr, context)
        except Exception as e:
            msg = ("Failed to delete pool health monitor: %s with "
                   "pool ID: %s. %s"
                   % (str(health_monitor), pool_id, str(e).capitalize()))
            LOG.error(msg)
            raise e
        else:
            msg = ("Deleted pool health monitor: %s with pool ID: %s"
                   % (str(health_monitor), pool_id))
            LOG.info(msg)
