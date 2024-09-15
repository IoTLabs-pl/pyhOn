class PyhOnException(Exception):
    pass


class AuthenticationException(PyhOnException):
    pass


class NoAuthenticationDataException(PyhOnException):
    pass


class ApiError(PyhOnException):
    pass
