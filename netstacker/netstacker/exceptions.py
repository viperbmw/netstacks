
class NetstackerError(Exception):
    """Baseclass for all netstacker errors"""
    pass


class NetstackerDriverError(NetstackerError):
    """Errors related to driver plugins"""
    pass


class NetstackerCheckError(NetstackerError):
    """Errors due to pre or post check validation failure"""
    pass


class NetstackerMetaProcessedException(NetstackerError):
    pass
