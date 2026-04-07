from modules.base import CapabilityModule
from modules.finance.service import FinanceCapability
from modules.manga.service import MangaCapability


class CapabilityRegistry:
    def __init__(self):
        modules = [MangaCapability(), FinanceCapability()]
        self._modules = {module.descriptor.id: module for module in modules}

    def list_capabilities(self):
        return [module.descriptor for module in self._modules.values()]

    def get(self, capability_id: str) -> CapabilityModule:
        try:
            return self._modules[capability_id]
        except KeyError as exc:
            raise KeyError(f"Capability '{capability_id}' is not registered") from exc
