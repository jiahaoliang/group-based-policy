# One Convergence, Inc. CONFIDENTIAL
# Copyright (c) 2012-2016, One Convergence, Inc., USA
# All Rights Reserved.
#
# All information contained herein is, and remains the property of
# One Convergence, Inc. and its suppliers, if any. The intellectual and
# technical concepts contained herein are proprietary to One Convergence,
# Inc. and its suppliers.
#
# Dissemination of this information or reproduction of this material is
# strictly forbidden unless prior written permission is obtained from
# One Convergence, Inc., USA


DRIVERS_DIR = '/usr/lib/python2.7/dist-packages/gbpservice/neutron/nsf/'\
              'configurator/drivers/vpn'

SERVICE_TYPE = 'vpn'

STATE_PENDING = 'PENDING_CREATE'
STATE_INIT = 'INIT'
STATE_ACTIVE = 'ACTIVE'
STATE_ERROR = 'ERROR'

CONFIGURATION_SERVER_PORT = 8888
request_url = "http://%s:%s/%s"
SUCCESS_CODES = [200, 201, 202, 203, 204]
ERROR_CODES = [400, 404, 500]

VYOS = 'vyos'
SM_RPC_TOPIC = 'VPN-sm-topic'
VPN_RPC_TOPIC = "vpn_topic"
VPN_GENERIC_CONFIG_RPC_TOPIC = "vyos_vpn_topic"

VPN_PLUGIN_TOPIC = 'vpn_plugin'
VPN_AGENT_TOPIC = 'vpn_agent'
