from pecan import rest
from pecan import expose
from v1 import controllers

class RootController(object):
    """This is root controller that forward the request to __init__.py file inside controller folder inside v1"""
    v1 = controllers.V1Controller()

    @expose()
    def get(self):
        # TODO(blogan): once a decision is made on how to do versions, do that
        # here
        return {'versions': [{'status': 'CURRENT',
                              'updated': '2014-12-11T00:00:00Z',
                              'id': 'v1'}]}
    
