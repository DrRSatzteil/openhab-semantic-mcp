"""Factory for dynamically discovering storage backends."""

import importlib
import pkgutil
from typing import Dict, Type
import logging

from .config import MonitoringConfig
from .interface import MonitoringStorageInterface

logger = logging.getLogger(__name__)


class StorageRegistry:
    """Registry for dynamically discovered storage backends."""

    def __init__(self):
        self._backends: Dict[str, Type[MonitoringStorageInterface]] = {}
        self._discover_backends()

    def _discover_backends(self):
        """Dynamically discover storage backends in the backends package."""
        try:
            # Import the backends package
            backends_package = importlib.import_module(".backends", package=__package__)

            # Iterate through all modules and subpackages in the backends package
            for _, module_name, is_pkg in pkgutil.iter_modules(
                backends_package.__path__
            ):
                try:
                    if is_pkg:
                        # For subpackages (like 'caldav'), look for __init__.py
                        module = importlib.import_module(
                            f".backends.{module_name}", package=__package__
                        )
                        # Look for storage classes in the subpackage's __init__.py
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)

                            # Check if it's a class that implements MonitoringStorageInterface
                            if (
                                isinstance(attr, type)
                                and issubclass(attr, MonitoringStorageInterface)
                                and attr != MonitoringStorageInterface
                                and not attr_name.startswith("_")
                            ):
                                # Register the backend with the subpackage name
                                backend_name = module_name.lower()
                                self._backends[backend_name] = attr
                                logger.info(
                                    "Registered storage backend: %s -> %s",
                                    backend_name,
                                    attr.__name__,
                                )
                    else:
                        # For direct modules (like 'file.py', 'memory.py')
                        module = importlib.import_module(
                            f".backends.{module_name}", package=__package__
                        )

                        # Look for storage classes in the module
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)

                            # Check if it's a class that implements MonitoringStorageInterface
                            if (
                                isinstance(attr, type)
                                and issubclass(attr, MonitoringStorageInterface)
                                and attr != MonitoringStorageInterface
                                and not attr_name.startswith("_")
                            ):
                                # Register the backend with a lowercase version of the class name
                                backend_name = module_name.lower()
                                self._backends[backend_name] = attr
                                logger.info(
                                    "Registered storage backend: %s -> %s",
                                    backend_name,
                                    attr.__name__,
                                )

                except (ImportError, AttributeError, TypeError) as e:
                    logger.error("Failed to load backend module %s: %s", module_name, e)

        except ImportError as e:
            logger.error("Failed to import backends package: %s", e)

    def get_backend(self, storage_type: str) -> Type[MonitoringStorageInterface]:
        """Get a backend class by storage type."""
        if storage_type not in self._backends:
            available = ", ".join(sorted(self._backends.keys()))
            raise ValueError(
                f"Unknown storage type: {storage_type}. Available: {available}"
            )
        return self._backends[storage_type]

    def list_backends(self) -> Dict[str, str]:
        """List all available backends."""
        return {name: cls.__name__ for name, cls in sorted(self._backends.items())}


# Global registry instance
_registry = StorageRegistry()


def create_monitoring_storage(config: MonitoringConfig) -> MonitoringStorageInterface:
    """Create a monitoring storage instance using dynamically discovered backends."""
    storage_type = config.storage_type or "memory"

    # Get the backend class from registry
    backend_class = _registry.get_backend(storage_type)

    # Get backend config and inject common config (timezone)
    backend_config = config.storage_config.get(storage_type, {}).copy()
    backend_config["timezone"] = config.timezone

    # Create instance
    return backend_class(backend_config)


def list_available_storage_backends() -> Dict[str, str]:
    """List all available storage backends."""
    return _registry.list_backends()
