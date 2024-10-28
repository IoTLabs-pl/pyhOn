class PyhOnException(Exception):
    pass


class AuthorizationFlowException(PyhOnException):
    pass


class InvalidCredentialsException(AuthorizationFlowException):
    pass


class MissingCredentialsException(PyhOnException):
    def __init__(self):
        super().__init__("No authentication data provided")


class ApiError(PyhOnException):
    pass
