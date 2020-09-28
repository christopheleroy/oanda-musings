

class ConfigPathError(Exception):
    """
    Exception that indicates that the path specifed for a v20 config file
    location doesn't exist
    """

    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "Config file '{}' could not be loaded.".format(self.path)


class ConfigValueError(Exception):
    """
    Exception that indicates that the v20 configuration file is missing
    a required value
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "Config is missing value for '{}'.".format(self.value)


class Config(object):
    """
    The Config object encapsulates all of the configuration required to create
    a v20 API context and configure it to work with a specific Account. 

    Using the Config object enables the scripts to exist without many command
    line arguments (host, token, accountID, etc)
    """
    def __init__(self):
        """
        Initialize an empty Config object
        """
        self.hostname = None
        self.streaming_hostname = None
        self.port = 443
        self.ssl = True
        self.token = None
        self.username = None
        self.accounts = []
        self.active_account = None
        self.path = None
        self.datetime_format = "RFC3339"

    def __str__(self):
        """
        Create the string (YAML) representaion of the Config instance 
        """

        s = ""
        s += "hostname: {}\n".format(self.hostname)
        s += "streaming_hostname: {}\n".format(self.streaming_hostname)
        s += "port: {}\n".format(self.port)
        s += "ssl: {}\n".format(str(self.ssl).lower())
        s += "token: {}\n".format(self.token)
        s += "username: {}\n".format(self.username)
        s += "datetime_format: {}\n".format(self.datetime_format)
        s += "accounts:\n"
        for a in self.accounts:
            s += "- {}\n".format(a)
        s += "active_account: {}".format(self.active_account)

        return s

    def dump(self, path):
        """
        Dump the YAML representation of the Config instance to a file.

        Args:
            path: The location to write the config YAML
        """

        path = os.path.expanduser(path)

        with open(path, "w") as f:
            print(str(self), file=f)
            
    def load_from_v20event(self, v20ev, secret_token):
        import os
        if(v20ev is None):
            v20ev = os.environ
            
        yget = lambda key,default: v20ev[key] if(key in v20ev) else (os.environ[key] if key in os.environ else default)
        
        self.hostname = yget("hostname", self.hostname)
        self.streaming_hostname = yget(
            "streaming_hostname", self.streaming_hostname
        )
        self.port = yget("port", self.port)
        self.ssl = yget("ssl", self.ssl)
        self.username = yget("username", self.username)
        self.token = secret_token
        self.accounts = yget("accounts", self.accounts)
        self.active_account = yget(
            "active_account", self.active_account
        )
        if(type(self.accounts) is str):
            self.accounts = self.accounts.split(',')

        self.datetime_format = yget("datetime_format", self.datetime_format)
        
        

    def validate(self):
        """
        Ensure that the Config instance is valid
        """

        if self.hostname is None:
            raise ConfigValueError("hostname")
        if self.streaming_hostname is None:
            raise ConfigValueError("hostname")
        if self.port is None:
            raise ConfigValueError("port")
        if self.ssl is None:
            raise ConfigValueError("ssl")
        if self.username is None:
            raise ConfigValueError("username")
        if self.token is None:
            raise ConfigValueError("token")
        if self.accounts is None:
            raise ConfigValueError("account")
        if self.active_account is None:
            raise ConfigValueError("account")
        if self.datetime_format is None:
            raise ConfigValueError("datetime_format")


    def create_context(self):
        """
        Initialize an API context based on the Config instance
        """
        
        import v20
        
        ctx = v20.Context(
            self.hostname,
            self.port,
            self.ssl,
            application="oanda-musings",
            token=self.token,
            datetime_format=self.datetime_format
        )

        return ctx

    def create_streaming_context(self):
        """
        Initialize a streaming API context based on the Config instance
        """
        import v20
        
        
        ctx = v20.Context(
            self.streaming_hostname,
            self.port,
            self.ssl,
            application="oanda-musings",
            token=self.token,
            datetime_format=self.datetime_format
        )

        return ctx

