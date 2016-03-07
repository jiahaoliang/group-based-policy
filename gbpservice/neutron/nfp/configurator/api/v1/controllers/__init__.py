from wsmeext import pecan as wsme_pecan
from wsme import types as wtypes

import controller

"""this class call methods of Controller class
according to HTTP request"""


class ControllerResolver(object):

    create_network_function_device_config = controller.Controller(
        "create_network_function_device_config")
    delete_network_function_device_config = controller.Controller(
        "delete_network_function_device_config")
    update_network_function_device_config = controller.Controller(
        "update_network_function_device_config")
    create_network_function_config = controller.Controller(
        "create_network_function_config")
    delete_network_function_config = controller.Controller(
        "delete_network_function_config")
    update_network_function_config = controller.Controller(
        "update_network_function_config")
    get_notifications = controller.Controller("get_notifications")


""" All HTTP requests with path starting from /v1
land here.
This class forward request with path starting from /v1/nfp
to ControllerResolver."""


class V1Controller(object):

    nfp = ControllerResolver()

    @wsme_pecan.wsexpose(wtypes.text)
    def get(self):
        # TODO(blogan): decide what exactly should be here, if anything
        return {'versions': [{'status': 'CURRENT',
                              'updated': '2014-12-11T00:00:00Z',
                              'id': 'v1'}]}
