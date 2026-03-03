from qgis.PyQt.QtWidgets import QToolBar, QAction # type: ignore
from qgis.PyQt.QtCore import Qt # type: ignore


class SuiteToolbar:
    """
    Manages the shared toolbar for the plugin suite.
    Handles creation, action registration, ordering, and cleanup.
    """

    def __init__(self, iface, toolbar_name="My Plugin Suite"):
        self.iface = iface
        self.toolbar_name = toolbar_name
        self.toolbar = None
        self._registered_actions = []  # keeps track of all added actions

    # ------------------------------------------------------------------
    # Setup & Teardown
    # ------------------------------------------------------------------

    def create(self):
        """Create and register the toolbar with QGIS."""
        self.toolbar = self.iface.addToolBar(self.toolbar_name)
        self.toolbar.setObjectName("MyPluginSuiteToolbar")
        self.toolbar.setToolTip(self.toolbar_name)
        # Optional: make toolbar non-movable
        # self.toolbar.setMovable(False)
        return self.toolbar

    def destroy(self):
        """Remove all actions and delete the toolbar cleanly."""
        if self.toolbar:
            for action in self._registered_actions:
                self.toolbar.removeAction(action)
            self._registered_actions.clear()
            self.toolbar.deleteLater()
            self.toolbar = None

    # ------------------------------------------------------------------
    # Action Management
    # ------------------------------------------------------------------

    def add_action(self, action: QAction):
        """Add a single QAction to the toolbar."""
        if action and self.toolbar:
            self.toolbar.addAction(action)
            self._registered_actions.append(action)

    def add_actions(self, actions: list):
        """Add a list of QActions to the toolbar."""
        for action in actions:
            self.add_action(action)

    def add_separator(self):
        """Add a visual separator between groups of tools."""
        if self.toolbar:
            separator = self.toolbar.addSeparator()
            self._registered_actions.append(separator)

    def remove_action(self, action: QAction):
        """Remove a specific action from the toolbar."""
        if action in self._registered_actions and self.toolbar:
            self.toolbar.removeAction(action)
            self._registered_actions.remove(action)

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------

    def show(self):
        if self.toolbar:
            self.toolbar.setVisible(True)

    def hide(self):
        if self.toolbar:
            self.toolbar.setVisible(False)

    def toggle_visibility(self):
        if self.toolbar:
            self.toolbar.setVisible(not self.toolbar.isVisible())

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_action_names(self):
        """Returns a list of the text labels of all registered actions."""
        return [a.text() for a in self._registered_actions if isinstance(a, QAction)]

    def clear(self):
        """Remove all actions from the toolbar without destroying it."""
        if self.toolbar:
            for action in self._registered_actions:
                self.toolbar.removeAction(action)
            self._registered_actions.clear()