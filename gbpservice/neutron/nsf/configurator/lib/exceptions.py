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

from neutron.common import exceptions


class UnknownReasonException(exceptions.NeutronException):
    message = _("Unsupported rpcreason '%(reason)s' from plugin ")


class UnknownResourceException(exceptions.NeutronException):
    message = _("Unsupported resource '%(resource)s' from plugin ")


class InvalidRsrcType(exceptions.NeutronException):
    message = _("Unsupported rsrctype '%(rsrc_type)s' from agent")


class ResourceErrorState(exceptions.NeutronException):
    message = _("Resource '%(name)s' : '%(id)s' \
        went to error state, %(message)")
