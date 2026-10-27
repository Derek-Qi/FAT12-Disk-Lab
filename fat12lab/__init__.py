"""An educational FAT12 implementation with no runtime dependencies."""

from .filesystem import FAT12, FATError

__version__ = '1.2.1'

__all__ = ["FAT12", "FATError"]

