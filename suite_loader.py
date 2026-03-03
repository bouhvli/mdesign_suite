from .toolbar import SuiteToolbar
import os
import importlib
import sys
import traceback
from qgis.PyQt.QtWidgets import QToolBar  # type: ignore


class PluginSuiteLoader:
    def __init__(self, iface):
        self.iface = iface
        self.loaded_plugins = []
        self.suite_toolbar = SuiteToolbar(iface, "M Design Suite")

    def initGui(self):
        self.suite_toolbar.create()

        plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
        sys.path.insert(0, plugins_dir)

        for plugin_name in sorted(os.listdir(plugins_dir)):
            plugin_path = os.path.join(plugins_dir, plugin_name)
            if os.path.isdir(plugin_path) and not plugin_name.startswith("_"):
                self._load_plugin(plugin_name)

    def _load_plugin(self, plugin_name):
        try:
            # Snapshot toolbars before loading so we can hide any the sub-plugin creates
            main_window = self.iface.mainWindow()
            toolbars_before = set(main_window.findChildren(QToolBar))

            module = importlib.import_module(plugin_name)
            plugin_instance = module.classFactory(self.iface)
            plugin_instance.initGui()

            # Hide every new toolbar the sub-plugin created — all buttons go in the suite toolbar
            toolbars_after = set(main_window.findChildren(QToolBar))
            for tb in toolbars_after - toolbars_before:
                tb.setVisible(False)

            if hasattr(plugin_instance, "get_actions"):
                actions = [a for a in plugin_instance.get_actions() if a is not None]
                if actions:
                    # Remove from QGIS default toolbar — buttons belong only in the suite toolbar
                    for action in actions:
                        self.iface.removeToolBarIcon(action)
                    self.suite_toolbar.add_separator()
                    self.suite_toolbar.add_actions(actions)

            self.loaded_plugins.append(plugin_instance)

        except Exception as e:
            print(f"[Suite] Failed to load {plugin_name}: {e}")
            print(traceback.format_exc())

    def unload(self):
        for plugin in self.loaded_plugins:
            try:
                plugin.unload()
            except Exception as e:
                print(f"[Suite] Unload error: {e}")

        self.suite_toolbar.destroy()  # ← clean destroy
        self.loaded_plugins.clear()