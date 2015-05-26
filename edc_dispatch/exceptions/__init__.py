class AlreadyDispatched(Exception):
    pass


class AlreadyDispatchedItem(Exception):
    pass


class AlreadyDispatchedContainer(Exception):
    pass


class DispatchModelError(Exception):
    pass


class DispatchError(Exception):
    pass


class DispatchAttributeError(Exception):
    pass


class DispatchContainerError(Exception):
    pass


class DispatchItemError(Exception):
    pass


class AlreadyReturned(Exception):
    pass


class BackupError(Exception):
    pass


class RestoreError(Exception):
    pass


class AlreadyReturnedController(Exception):
    pass


class DispatchControllerNotReady(Exception):
    pass


class DispatchControllerProducerError(Exception):
    pass


class AlreadyRegisteredController(Exception):
    pass


class NotRegisteredController(Exception):
    pass


class ControllerBaseModelError(Exception):
    pass


class DispatchControllerError(Exception):
    pass