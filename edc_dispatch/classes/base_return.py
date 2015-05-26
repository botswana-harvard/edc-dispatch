from .base_controller import BaseController
from .controller_register import registered_controllers


class BaseReturn(BaseController):

    def _repr(self):
        return 'ReturnController[{0}]'.format(self.get_producer().settings_key)

    def __init__(self, using_source, using_destination, **kwargs):
        super(BaseReturn, self).__init__(using_source, using_destination, **kwargs)
        registered_controllers.register(self)
