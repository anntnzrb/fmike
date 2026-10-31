class FmikeError(Exception):
    fix: str

    def __init__(self, message: str, *, fix: str) -> None:
        super().__init__(message)
        self.fix = fix


class ConfigError(FmikeError):
    pass


class BananaNotInstalledError(FmikeError):
    pass


class BananaUnavailableError(FmikeError):
    pass


class DeviceNotFoundError(FmikeError):
    pass


class NotWindowsError(FmikeError):
    pass
