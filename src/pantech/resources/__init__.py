"""Resource classes. Reach them through a client: ``client.instances``, ``client.networks.subnets``…"""

from ._async import AsyncResources
from ._sync import Resources

__all__ = ["Resources", "AsyncResources"]
