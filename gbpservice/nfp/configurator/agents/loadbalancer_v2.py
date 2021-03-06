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

import os

from gbpservice.nfp.configurator.agents import agent_base
from gbpservice.nfp.configurator.lib import data_filter
from gbpservice.nfp.configurator.lib import lbv2_constants as lb_constants
from gbpservice.nfp.common import exceptions
from gbpservice.nfp.configurator.lib import utils
from gbpservice.nfp.core import event as nfp_event
from gbpservice.nfp.core import poll as nfp_poll
from neutron import context
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

""" Implements LBaaS response path to Neutron plugin.
Methods of this class are invoked by the LBaasEventHandler class and also
by driver class for sending response from driver to the LBaaS Neutron plugin.
"""


class LBaasRpcSender(data_filter.Filter):

    def __init__(self, sc):
        self.notify = agent_base.AgentBaseNotification(sc)

    # TODO(jiahao): copy from v1 agent need to review
    def get_logical_device(self, pool_id, context):
        """ Calls data filter library to get logical device from pool_id.

        :param pool_id: object type
        :param context: context which has list of all pool related resources
                        belonging to that tenant

        Returns: logical_device
        """
        return self.call(
            context,
            self.make_msg(
                'get_logical_device',
                pool_id=pool_id
            )
        )

    def update_status(self, obj_type, obj_id, root_lb_id,
                      provisioning_status, operating_status,
                      agent_info, obj=None):
        """ Enqueues the response from LBaaS operation to neutron plugin.

        :param obj_type: object type
        :param obj_id: object id
        :param root_lb_id: root loadbalancer id
        :param provisioning_status: an enum of (‘ACTIVE’, ‘PENDING_CREATE’,
        ‘PENDING_UPDATE’, ‘PENDING_DELETE’, ‘ERROR’)
        :param operating_status:  an enum of
        (‘ONLINE’, ‘OFFLINE’, ‘DEGRADED’, ‘ERROR’)

        """

        msg = {'info': {'service_type': lb_constants.SERVICE_TYPE,
                        'context': agent_info['context']},
               'notification': [{'resource': agent_info['resource'],
                                 'data':{'obj_type': obj_type,
                                         'obj_id': obj_id,
                                         'notification_type': 'update_status',
                                         'root_lb_id': root_lb_id,
                                         'provisioning_status':
                                             provisioning_status,
                                         'operating_status':
                                             operating_status,
                                         obj_type: obj}}]
               }
        self.notify._notification(msg)

    # TODO(jiahao): copy from v1 agent need to review
    def update_pool_stats(self, pool_id, stats, context, pool=None):
        """ Enqueues the response from LBaaS operation to neutron plugin.

        :param pool_id: pool id
        :param stats: statistics of that pool

        """
        msg = {'info': {'service_type': lb_constants.SERVICE_TYPE,
                        'context': context.to_dict()},
               'notification': [{'resource': 'pool',
                                 'data': {'pool_id': pool_id,
                                          'stats': stats,
                                          'notification_type': (
                                                        'update_pool_stats'),
                                          'pool': pool_id}}]
               }
        self.notify._notification(msg)

    # TODO(jiahao): copy from v1 agent need to review
    def vip_deleted(self, vip, status, agent_info):
        """ Enqueues the response from LBaaS operation to neutron plugin.

        :param vip: object type
        :param vip_id: object id
        :param status: status of the object to be set

        """
        msg = {'info': {'service_type': lb_constants.SERVICE_TYPE,
                        'context': agent_info['context']},
               'notification': [{'resource': agent_info['resource'],
                                 'data': {'vip_id': vip['id'],
                                          'vip': vip,
                                          'notification_type': 'vip_deleted',
                                          'status': status}}]
               }
        self.notify._notification(msg)


"""Implements APIs invoked by configurator for processing RPC messages.

RPC client of configurator module receives RPC messages from REST server
and invokes the API of this class. The instance of this class is registered
with configurator module using register_service_agent API. Configurator module
identifies the service agent object based on service type and invokes ones of
the methods of this class to configure the device.

"""


class LBaaSv2RpcManager(agent_base.AgentBaseRPCManager):
    def __init__(self, sc, conf):
        """Instantiates child and parent class objects.

        :param sc: Service Controller object that is used for interfacing
        with core service controller.
        :param conf: Configuration object that is used for configuration
        parameter access.

        """

        super(LBaaSv2RpcManager, self).__init__(sc, conf)

    def _send_event(self, event_id, data, serialize=False, binding_key=None,
                    key=None):
        """Posts an event to framework.

        :param event_id: Unique identifier for the event
        :param event_key: Event key for serialization
        :param serialize: Serialize the event
        :param binding_key: binding key to be used for serialization
        :param key: event key

        """

        ev = self.sc.new_event(id=event_id, data=data)
        ev.key = key
        ev.serialize = serialize
        ev.binding_key = binding_key
        self.sc.post_event(ev)

    def create_loadbalancer(self, context, loadbalancer, driver_name):
        """Enqueues event for worker to process create loadbalancer request.

        :param context: RPC context
        :param loadbalancer: loadbalancer resource to be created

        Returns: None

        """
        arg_dict = {'context': context,
                    'loadbalancer': loadbalancer,
                    'driver_name': driver_name
                    }
        self._send_event(lb_constants.EVENT_CREATE_LOADBALANCER, arg_dict,
                         serialize=True, binding_key=loadbalancer['id'],
                         key=loadbalancer['id'])

    def update_loadbalancer(self, context, old_loadbalancer, loadbalancer):
        """Enqueues event for worker to process update loadbalancer request.

        :param context: RPC context
        :param old_loadbalancer: old loadbalancer resource to be updated
        :param loadbalancer: new loadbalancer resource

        Returns: None

        """
        arg_dict = {'context': context,
                    'old_loadbalancer': old_loadbalancer,
                    'loadbalancer': loadbalancer,
                    }
        self._send_event(lb_constants.EVENT_UPDATE_LOADBALANCER, arg_dict,
                         serialize=True, binding_key=loadbalancer['id'],
                         key=loadbalancer['id'])

    def delete_loadbalancer(self, context, loadbalancer):
        """Enqueues event for worker to process delete loadbalancer request.

        :param context: RPC context
        :param loadbalancer: loadbalancer resource to be deleted

        Returns: None

        """
        arg_dict = {'context': context,
                    'loadbalancer': loadbalancer,
                    }
        self._send_event(lb_constants.EVENT_DELETE_LOADBALANCER, arg_dict,
                         serialize=True, binding_key=loadbalancer['id'],
                         key=loadbalancer['id'])

    def create_listener(self, context, listener):
        """Enqueues event for worker to process create listener request.

        :param context: RPC context
        :param listener: listener resource to be created

        Returns: None

        """
        arg_dict = {'context': context,
                    'listener': listener,
                    }
        self._send_event(lb_constants.EVENT_CREATE_LISTENER, arg_dict,
                         serialize=True,
                         binding_key=listener['loadbalancer_id'],
                         key=listener['id'])

    def update_listener(self, context, old_listener, listener):
        """Enqueues event for worker to process update listener request.

        :param context: RPC context
        :param old_listener: old listener resource to be updated
        :param listener: new listener resource

        Returns: None

        """
        arg_dict = {'context': context,
                    'old_listener': old_listener,
                    'listener': listener,
                    }
        self._send_event(lb_constants.EVENT_UPDATE_LISTENER, arg_dict,
                         serialize=True,
                         binding_key=listener['loadbalancer_id'],
                         key=listener['id'])

    def delete_listener(self, context, listener):
        """Enqueues event for worker to process delete listener request.

        :param context: RPC context
        :param listener: listener resource to be deleted

        Returns: None

        """
        arg_dict = {'context': context,
                    'listener': listener,
                    }
        self._send_event(lb_constants.EVENT_DELETE_LISTENER, arg_dict,
                         serialize=True,
                         binding_key=listener['loadbalancer_id'],
                         key=listener['id'])

    def create_pool(self, context, pool):
        """Enqueues event for worker to process create pool request.

        :param context: RPC context
        :param pool: pool resource to be created

        Returns: None

        """
        arg_dict = {'context': context,
                    'pool': pool
                    }
        # TODO: M:N pool is not yet implemented.
        # For Mitaka, use binding_key=pool['listeners'][0]['id']
        # For Liberty, use binding_key=pool['listener']['id']
        self._send_event(lb_constants.EVENT_CREATE_POOL, arg_dict,
                         serialize=True,
                         binding_key=pool['loadbalancer_id'],
                         key=pool['id'])

    def update_pool(self, context, old_pool, pool):
        """Enqueues event for worker to process update pool request.

        :param context: RPC context
        :param old_pool: old pool resource to be updated
        :param pool: new pool resource

        Returns: None

        """
        arg_dict = {'context': context,
                    'old_pool': old_pool,
                    'pool': pool,
                    }
        # For Mitaka, use binding_key=pool['listeners'][0]['id']
        # For Liberty, use binding_key=pool['listener']['id']
        self._send_event(lb_constants.EVENT_UPDATE_POOL, arg_dict,
                         serialize=True,
                         binding_key=pool['loadbalancer_id'],
                         key=pool['id'])

    def delete_pool(self, context, pool):
        """Enqueues event for worker to process delete pool request.

        :param context: RPC context
        :param pool: pool resource to be deleted

        Returns: None

        """
        arg_dict = {'context': context,
                    'pool': pool,
                    }
        # For Mitaka, use binding_key=pool['listeners'][0]['id']
        # For Liberty, use binding_key=pool['listener']['id']
        self._send_event(lb_constants.EVENT_DELETE_POOL, arg_dict,
                         serialize=True,
                         binding_key=pool['loadbalancer_id'],
                         key=pool['id'])

    def create_member(self, context, member):
        """Enqueues event for worker to process create member request.

        :param context: RPC context
        :param member: member resource to be created

        Returns: None

        """
        arg_dict = {'context': context,
                    'member': member,
                    }
        self._send_event(lb_constants.EVENT_CREATE_MEMBER, arg_dict,
                         serialize=True,
                         binding_key=member['pool']['loadbalancer_id'],
                         key=member['id'])

    def update_member(self, context, old_member, member):
        """Enqueues event for worker to process update member request.

        :param context: RPC context
        :param old_member: old member resource to be updated
        :param member: new member resource

        Returns: None

        """
        arg_dict = {'context': context,
                    'old_member': old_member,
                    'member': member,
                    }
        self._send_event(lb_constants.EVENT_UPDATE_MEMBER, arg_dict,
                         serialize=True,
                         binding_key=member['pool']['loadbalancer_id'],
                         key=member['id'])

    def delete_member(self, context, member):
        """Enqueues event for worker to process delete member request.

        :param context: RPC context
        :param member: member resource to be deleted

        Returns: None

        """
        arg_dict = {'context': context,
                    'member': member,
                    }
        self._send_event(lb_constants.EVENT_DELETE_MEMBER, arg_dict,
                         serialize=True,
                         binding_key=member['pool']['loadbalancer_id'],
                         key=member['id'])

    def create_healthmonitor(self, context, healthmonitor):
        """Enqueues event for worker to process create health monitor request.

        :param context: RPC context
        :param health_monitor: health_monitor resource to be created
        :param pool_id: pool_id to which health monitor is associated

        Returns: None

        """
        arg_dict = {'context': context,
                    'health_monitor': healthmonitor
                    }
        self._send_event(lb_constants.EVENT_CREATE_HEALTH_MONITOR,
                         arg_dict, serialize=True,
                         binding_key=healthmonitor['pool']['id'],
                         key=healthmonitor['id'])

    def update_healthmonitor(self, context, old_healthmonitor,
                                   healthmonitor):
        """Enqueues event for worker to process update health monitor request.

        :param context: RPC context
        :param old_health_monitor: health_monitor resource to be updated
        :param health_monitor: new health_monitor resource
        :param pool_id: pool_id to which health monitor is associated

        Returns: None

        """
        arg_dict = {'context': context,
                    'old_health_monitor': old_healthmonitor,
                    'health_monitor': healthmonitor
                    }
        self._send_event(lb_constants.EVENT_UPDATE_HEALTH_MONITOR,
                         arg_dict, serialize=True,
                         binding_key=healthmonitor['pool']['id'],
                         key=healthmonitor['id'])

    def delete_healthmonitor(self, context, healthmonitor):
        """Enqueues event for worker to process delete health monitor request.

        :param context: RPC context
        :param health_monitor: health_monitor resource to be deleted
        :param pool_id: pool_id to which health monitor is associated

        Returns: None

        """
        arg_dict = {'context': context,
                    'health_monitor': healthmonitor
                    }
        self._send_event(lb_constants.EVENT_DELETE_HEALTH_MONITOR,
                         arg_dict, serialize=True,
                         binding_key=healthmonitor['pool']['id'],
                         key=healthmonitor['id'])

    # TODO(jiahao): copy from v1 agent need to review
    def agent_updated(self, context, payload):
        """Enqueues event for worker to process agent updated request.

        :param context: RPC context
        :param payload: payload

        Returns: None

        """
        arg_dict = {'context': context,
                    'payload': payload}
        self._send_event(lb_constants.EVENT_AGENT_UPDATED, arg_dict)


"""Implements event handlers and their helper methods.

Object of this class is registered with the event class of core service
controller. Based on the event key, handle_event method of this class is
invoked by core service controller.

"""


class LBaaSEventHandler(agent_base.AgentBaseEventHandler,
                        nfp_poll.PollEventDesc):
    instance_mapping = {}

    def __init__(self, sc, drivers, rpcmgr):
        self.sc = sc
        self.drivers = drivers
        self.rpcmgr = rpcmgr
        self.plugin_rpc = LBaasRpcSender(sc)

    def _get_driver(self, driver_name):
        """Retrieves service driver object based on service type input.

        Currently, service drivers are identified with service type. Support
        for single driver per service type is provided. When multi-vendor
        support is going to be provided, the driver should be selected based
        on both service type and vendor name.

        :param service_type: Service type - loadbalancer

        Returns: Service driver instance

        """
        driver = lb_constants.SERVICE_TYPE + driver_name
        return self.drivers[driver]

    def _root_loadbalancer_id(self, obj_type, obj_dict):
        """Returns the loadbalancer id this instance is attached to."""

        try:
            # TODO: For Mitaka
            if obj_type == 'loadbalancer':
                lb = obj_dict['id']
            elif obj_type == 'listener':
                lb = obj_dict['loadbalancer']['id']
            elif obj_type == 'l7policy':
                lb = obj_dict['listener']['loadbalancer']['id']
            elif obj_type == 'l7rule':
                lb = obj_dict['policy']['listener']['loadbalancer']['id']
            elif obj_type == 'pool':
                lb = obj_dict['loadbalancer']['id']
            elif obj_type == 'sni':
                lb = obj_dict['listener']['loadbalancer']['id']
            else:
                # Pool Member or Health Monitor
                lb = obj_dict['pool']['loadbalancer']['id']
            # For Liberty
            # if obj_type == 'loadbalancer':
            #     lb = obj_dict['id']
            # elif obj_type == 'listener':
            #     lb = obj_dict['loadbalancer']['id']
            # elif obj_type == 'pool':
            #     lb = obj_dict['listener']['loadbalancer']['id']
            # elif obj_type == 'sni':
            #     lb = obj_dict['listener']['loadbalancer']['id']
            # else:
            #     # Pool Member or Health Monitor
            #     lb = obj_dict['pool']['listener']['loadbalancer']['id']
        except Exception:
            raise exceptions.IncompleteData(
                'Root loadbalancer id was not found')
        else:
            return lb

    def handle_event(self, ev):
        """Processes the generated events in worker context.

        Processes the following events.
        - create loadbalancer
        - update loadbalancer
        - delete loadbalancer
        - create listener
        - update listener
        - delete listener
        - create pool
        - update pool
        - delete pool
        - create member
        - update member
        - delete member
        - create pool health monitor
        - update pool health monitor
        - delete pool health monitor
        - agent updated
        Enqueues responses into notification queue.

        Returns: None

        """
        LOG.info("###### Handling event=%s ########" % (ev.id))
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s of topic: %s. "
                   % (os.getpid(), ev.id, lb_constants.LBAAS_AGENT_RPC_TOPIC))
            LOG.debug(msg)

            method = getattr(self, "_%s" % (ev.id.lower()))
            method(ev)
        except Exception as err:
            LOG.error("Failed to perform the operation: %s. %s"
                      % (ev.id, str(err).capitalize()))
        finally:
            if ev.id == lb_constants.EVENT_COLLECT_STATS:
                """Do not say event done for collect stats as it is
                   to be executed forever
                """
                pass
            else:
                LOG.info("###### Calling event done for ev=%s######" % (ev.id))
                self.sc.event_done(ev)

    def _handle_event_loadbalancer(self, ev, operation):
        data = ev.data
        context = data['context']
        loadbalancer = data['loadbalancer']
        root_lb_id = self._root_loadbalancer_id('loadbalancer', loadbalancer)
        agent_info = ev.data['context'].pop('agent_info')
        service_vendor = agent_info['service_vendor']

        try:
            if operation == 'create':
                driver_name = data['driver_name']
                driver_id = driver_name + service_vendor
                if (driver_id) not in self.drivers.keys():
                    msg = ('No device driver on agent: %s.' % (driver_name))
                    LOG.error(msg)
                    self.plugin_rpc.update_status(
                        'loadbalancer', loadbalancer['id'], root_lb_id,
                        lb_constants.ERROR, lb_constants.OFFLINE, agent_info,
                        None)
                    return
                driver = self.drivers[driver_id]
                driver.load_balancer.create(context, loadbalancer) 
                LBaaSEventHandler.instance_mapping[loadbalancer['id']] \
                    = driver_name
            elif operation == 'update':
                old_loadbalancer = data['old_loadbalancer']
                driver = self._get_driver(service_vendor)
                driver.load_balancer.update(context, 
                    old_loadbalancer, loadbalancer)
            elif operation == 'delete':
                driver = self._get_driver(service_vendor)
                driver.load_balancer.delete(context, loadbalancer)
                del LBaaSEventHandler.instance_mapping[loadbalancer['id']]
                return  # Don't update object status for delete operation
        except Exception:
            if operation == 'delete':
                LOG.warn(
                    "Failed to delete loadbalancer %s" % (loadbalancer['id']))
                del LBaaSEventHandler.instance_mapping[loadbalancer['id']]
            else:
                self.plugin_rpc.update_status(
                    'loadbalancer', loadbalancer['id'], root_lb_id,
                    lb_constants.ERROR, lb_constants.OFFLINE,
                    agent_info, None)
        else:
            self.plugin_rpc.update_status(
                    'loadbalancer', loadbalancer['id'], root_lb_id,
                    lb_constants.ACTIVE, lb_constants.ONLINE,
                    agent_info, None)

    def _create_loadbalancer(self, ev):
        self._handle_event_loadbalancer(ev, 'create')

    def _update_loadbalancer(self, ev):
        self._handle_event_loadbalancer(ev, 'update')

    def _delete_loadbalancer(self, ev):
        self._handle_event_loadbalancer(ev, 'delete')

    def _handle_event_listener(self, ev, operation):
        data = ev.data
        context = data['context']
        listener = data['listener']
        root_lb_id = self._root_loadbalancer_id('listener', listener)
        agent_info = ev.data['context'].pop('agent_info')
        service_vendor = agent_info['service_vendor']
        driver = self._get_driver(service_vendor)

        try:
            if operation == 'create':
                driver.listener.create(context, listener)
            elif operation == 'update':
                old_listener = data['old_listener']
                driver.listener.update(context, old_listener, listener)
            elif operation == 'delete':
                driver.listener.delete(context, listener)
                return  # Don't update object status for delete operation
        except Exception:
            if operation == 'delete':
                LOG.warn("Failed to delete listener %s" % (listener['id']))
            else:
                self.plugin_rpc.update_status(
                    'listener', listener['id'], root_lb_id,
                    lb_constants.ERROR,  lb_constants.OFFLINE,
                    agent_info, None)
        else:
            self.plugin_rpc.update_status(
                    'listener', listener['id'], root_lb_id,
                    lb_constants.ACTIVE,  lb_constants.ONLINE,
                    agent_info, None)

    def _create_listener(self, ev):
        self._handle_event_listener(ev, 'create')

    def _update_listener(self, ev):
        self._handle_event_listener(ev, 'update')

    def _delete_listener(self, ev):
        self._handle_event_listener(ev, 'delete')

    def _handle_event_pool(self, ev, operation):
        data = ev.data
        context = data['context']
        pool = data['pool']
        root_lb_id = self._root_loadbalancer_id('pool', pool)
        agent_info = ev.data['context'].pop('agent_info')
        service_vendor = agent_info['service_vendor']
        driver = self._get_driver(service_vendor)

        try:
            if operation == 'create':
                driver.pool.create(context, pool)
            elif operation == 'update':
                old_pool = data['old_pool']
                driver.pool.update(context, old_pool, pool)
            elif operation == 'delete':
                driver.pool.delete(context, pool)
                return  # Don't update object status for delete operation
        except Exception:
            if operation == 'delete':
                LOG.warn("Failed to delete pool %s" % (pool['id']))
            else:
                self.plugin_rpc.update_status(
                    'pool', pool['id'], root_lb_id,
                    lb_constants.ERROR,  lb_constants.OFFLINE,
                    agent_info, None)
        else:
            self.plugin_rpc.update_status(
                    'pool', pool['id'], root_lb_id,
                    lb_constants.ACTIVE,  lb_constants.ONLINE,
                    agent_info, None)

    def _create_pool(self, ev):
        self._handle_event_pool(ev, 'create')

    def _update_pool(self, ev):
        self._handle_event_pool(ev, 'update')

    def _delete_pool(self, ev):
        self._handle_event_pool(ev, 'delete')

    def _handle_event_member(self, ev, operation):
        data = ev.data
        context = data['context']
        member = data['member']
        root_lb_id = self._root_loadbalancer_id('member', member)
        agent_info = ev.data['context'].pop('agent_info')
        service_vendor = agent_info['service_vendor']
        driver = self._get_driver(service_vendor)  # member['pool_id'])
        try:
            if operation == 'create':
                driver.member.create(context, member)
            elif operation == 'update':
                old_member = data['old_member']
                driver.member.update(context, old_member, member)
            elif operation == 'delete':
                driver.member.delete(context, member)
                return  # Don't update object status for delete operation
        except Exception:
            if operation == 'delete':
                LOG.warn(
                    "Failed to delete member %s" % (member['id']))
            else:
                self.plugin_rpc.update_status(
                    'member', member['id'], root_lb_id,
                    lb_constants.ERROR,  lb_constants.OFFLINE,
                    agent_info, None)
        else:
            self.plugin_rpc.update_status(
                    'member', member['id'], root_lb_id,
                    lb_constants.ACTIVE,  lb_constants.ONLINE,
                    agent_info, None)

    def _create_member(self, ev):
        self._handle_event_member(ev, 'create')

    def _update_member(self, ev):
        self._handle_event_member(ev, 'update')

    def _delete_member(self, ev):
        self._handle_event_member(ev, 'delete')

    # TODO: need to update parameters sent according to lbaasv2
    # TODO: need to update update_status()
    def _handle_event_health_monitor(self, ev, operation):
        data = ev.data
        context = data['context']
        health_monitor = data['health_monitor']
        root_lb_id = self._root_loadbalancer_id(
            'healthmonitor', health_monitor)
        agent_info = context.pop('agent_info')
        service_vendor = agent_info['service_vendor']
        driver = self._get_driver(service_vendor)  # (pool_id)

        pool_id = health_monitor['pool']['id']
        assoc_id = {'pool_id': pool_id,
                    'monitor_id': health_monitor['id']}
        try:
            if operation == 'create':
                driver.health_monitor.create(context, health_monitor)
            elif operation == 'update':
                old_health_monitor = data['old_health_monitor']
                driver.health_monitor.update(context, old_health_monitor, 
                                                  health_monitor)
            elif operation == 'delete':
                driver.health_monitor.delete(context, health_monitor)
                return  # Don't update object status for delete operation
        except Exception:
            if operation == 'delete':
                LOG.warn("Failed to delete pool health monitor."
                         " assoc_id: %s" % (assoc_id))
            else:
                self.plugin_rpc.update_status(
                    'healthmonitor', health_monitor['id'], root_lb_id,
                    lb_constants.ERROR,  lb_constants.OFFLINE,
                    agent_info, None)
        else:
            self.plugin_rpc.update_status(
                    'healthmonitor', health_monitor['id'], root_lb_id,
                    lb_constants.ACTIVE,  lb_constants.ONLINE,
                    agent_info, None)

    def _create_health_monitor(self, ev):
        self._handle_event_health_monitor(ev, 'create')

    def _update_health_monitor(self, ev):
        self._handle_event_health_monitor(ev, 'update')

    def _delete_health_monitor(self, ev):
        self._handle_event_health_monitor(ev, 'delete')

    # TODO(jiahao): copy from v1 agent need to review
    def _agent_updated(self, ev):
        """ TODO:(pritam): Support """
        return None

    # TODO(jiahao): copy from v1 agent need to review
    def _collect_stats(self, ev):
        self.sc.poll_event(ev)

    # TODO(jiahao): copy from v1 agent need to review
    @nfp_poll.poll_event_desc(event=lb_constants.EVENT_COLLECT_STATS,
                              spacing=60)
    def collect_stats(self, ev):
        for pool_id, driver_name in LBaaSEventHandler.instance_mapping.items():
            driver_id = lb_constants.SERVICE_TYPE + driver_name
            driver = self.drivers[driver_id]
            try:
                stats = driver.get_stats(pool_id)
                if stats:
                    self.plugin_rpc.update_pool_stats(pool_id, stats,
                                                      self.context)
            except Exception:
                msg = ("Error updating statistics on pool %s" % (pool_id))
                LOG.error(msg)


def events_init(sc, drivers, rpcmgr):
    """Registers events with core service controller.

    All the events will come to handle_event method of class instance
    registered in 'handler' field.

    :param drivers: Driver instances registered with the service agent
    :param rpcmgr: Instance to receive all the RPC messages from configurator
    module.

    Returns: None

    """
    ev_ids = [lb_constants.EVENT_CREATE_LOADBALANCER, lb_constants.EVENT_UPDATE_LOADBALANCER,
              lb_constants.EVENT_DELETE_LOADBALANCER,

              lb_constants.EVENT_CREATE_LISTENER, lb_constants.EVENT_UPDATE_LISTENER,
              lb_constants.EVENT_DELETE_LISTENER,

              lb_constants.EVENT_CREATE_POOL, lb_constants.EVENT_UPDATE_POOL,
              lb_constants.EVENT_DELETE_POOL,

              lb_constants.EVENT_CREATE_MEMBER,
              lb_constants.EVENT_UPDATE_MEMBER,
              lb_constants.EVENT_DELETE_MEMBER,

              lb_constants.EVENT_CREATE_HEALTH_MONITOR,
              lb_constants.EVENT_UPDATE_HEALTH_MONITOR,
              lb_constants.EVENT_DELETE_HEALTH_MONITOR,

              lb_constants.EVENT_AGENT_UPDATED,
              lb_constants.EVENT_COLLECT_STATS
              ]

    evs = []
    for ev_id in ev_ids:
        ev = nfp_event.Event(id=ev_id, handler=LBaaSEventHandler(sc, drivers,
                                                            rpcmgr))
        evs.append(ev)
    sc.register_events(evs)


def load_drivers(sc, conf):
    """Imports all the driver files.

    Returns: Dictionary of driver objects with a specified service type and/or
    vendor name

    """
    cutils = utils.ConfiguratorUtils()
    drivers = cutils.load_drivers(lb_constants.DRIVERS_DIR)

    plugin_rpc = LBaasRpcSender(sc)

    for service_type, dobj in drivers.iteritems():
        '''LB Driver constructor needs plugin_rpc as a param'''
        instantiated_dobj = dobj(plugin_rpc=plugin_rpc, conf=conf)
        drivers[service_type] = instantiated_dobj

    return drivers


def register_service_agent(cm, sc, conf, rpcmgr):
    """Registers Loadbalaner service agent with configurator module.

    :param cm: Instance of configurator module
    :param sc: Instance of core service controller
    :param conf: Instance of oslo configuration
    :param rpcmgr: Instance containing RPC methods which are invoked by
    configurator module on corresponding RPC message arrival

    """

    service_type = lb_constants.SERVICE_TYPE
    cm.register_service_agent(service_type, rpcmgr)


def init_agent(cm, sc, conf):
    """Initializes Loadbalaner agent.

    :param cm: Instance of configuration module
    :param sc: Instance of core service controller
    :param conf: Instance of oslo configuration

    """

    try:
        drivers = load_drivers(sc, conf)
    except Exception as err:
        msg = ("Loadbalaner V2 agent failed to load service drivers. %s"
               % (str(err).capitalize()))
        LOG.error(msg)
        raise err
    else:
        msg = ("Loadbalaner V2 agent loaded service"
               " drivers successfully.")
        LOG.debug(msg)

    rpcmgr = LBaaSv2RpcManager(sc, conf)

    try:
        events_init(sc, drivers, rpcmgr)
    except Exception as err:
        msg = ("Loadbalaner V2 agent failed to initialize events. %s"
               % (str(err).capitalize()))
        LOG.error(msg)
        raise err
    else:
        msg = ("Loadbalaner V2 agent initialized"
               " events successfully.")
        LOG.debug(msg)

    try:
        register_service_agent(cm, sc, conf, rpcmgr)
    except Exception as err:
        msg = ("Failed to register Loadbalaner V2 agent with"
               " configurator module. %s" % (str(err).capitalize()))
        LOG.error(msg)
        raise err
    else:
        msg = ("Loadbalaner V2 agent registered with configuration"
               " module successfully.")
        LOG.debug(msg)


def _start_collect_stats(sc):
    """Enqueues poll event for worker to collect pool stats periodically.
       Agent keeps map of pool_id:driver. As part of handling this event,
       stats for pool_id is requested from agent inside service vm
    """

    arg_dict = {}
    ev = sc.new_event(id=lb_constants.EVENT_COLLECT_STATS, data=arg_dict)
    sc.post_event(ev)


def init_agent_complete(cm, sc, conf):
    # _start_collect_stats(sc)
    LOG.info("Initialization of loadbalancer agent v2 completed.")
