def classFactory(iface):
    from .suite_loader import PluginSuiteLoader
    return PluginSuiteLoader(iface)