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


def _is_class(obj):
    return 'class' in str(type(obj))


def _name(obj):
    """Helper method to construct name of an object.

    'module.class' if object is of type 'class'
    'module.class.method' if object is of type 'method'
    """
    # If it is callable, then it is a method
    if callable(obj):
        return "{0}.{1}.{2}".format(
            type(obj.im_self).__module__,
            type(obj.im_self).__name__,
            obj.__name__)
    # If obj is of type class
    elif _is_class(obj):
        return "{0}.{1}".format(
            type(obj).__module__,
            type(obj).__name__)
    else:
        return obj.__name__


def identify(obj):
    """Helper method to display identify an object.

    Useful for logging. Decodes based on the type of obj.
    Supports 'class' & 'method' types for now.
    """
    try:
        return "(%s)" % (_name(obj))
    except Exception:
        """Some unknown type, returning empty """
        return ""


def log_info(log, msg):
    log.info(msg)


def log_debug(log, msg):
    log.debug(msg)


def log_error(log, msg):
    log.error(msg)


def log_warn(log, msg):
    log.warn(msg)


def log_exception(log, msg):
    log.exception(msg)
