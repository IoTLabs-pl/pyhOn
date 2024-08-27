class pyhOnException(Exception):
    pass


class HonAuthenticationError(pyhOnException):
    pass


class NoAuthenticationException(pyhOnException):
    pass


class ApiError(pyhOnException):
    pass
