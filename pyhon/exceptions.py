class PyhOnException(Exception):
    pass


class HonAuthenticationError(PyhOnException):
    pass


class NoAuthenticationException(PyhOnException):
    pass


class ApiError(PyhOnException):
    pass
