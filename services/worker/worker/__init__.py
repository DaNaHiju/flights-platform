"""Out-of-band jobs, invoked by a CronJob defined in the manifests repo."""

# Python runs a package's __init__ before any of its submodules, so importing
# worker.config here guarantees the environment check happens first — before
# worker.refresh_deals imports shared.cache, which opens the Redis client.
from worker import config  # noqa: F401
