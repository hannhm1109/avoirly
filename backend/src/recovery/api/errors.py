class DomainError(Exception):
    def __init__(self, code, message, status=409, details=None):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details
