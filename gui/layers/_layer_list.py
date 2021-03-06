import weakref
from collections.abc import Iterable

from vispy.util.event import EmitterGroup, Event
from ._base import Layer


class ItemEvent(Event):
    def __init__(self, type, item, **kwargs):
        super().__init__(type, **kwargs)
        self._item = item

    @property
    def item(self):
        return self._item


def _check_layer(obj, error=False):
    result = isinstance(obj, Layer)
    if error and not result:
        raise TypeError(f'expected {obj} to be Layer; '
                        f'got {type(obj)}') from None
    return result


class LayerList:
    """List-like layer collection with built-in reordering and callback hooks.

    Parameters
    ----------
    viewer : Viewer, optional
        Parent viewer.

    Attributes
    ----------
    viewer : Viewer
        Parent viewer.
    events : vispy.util.event.EmitterGroup
        Event hooks:
            * add_item(item): whenever an item is added
            * remove_item(item): whenever an item is removed
            * reorder(): whenever the list is reordered
    """
    __slots__ = ('__weakref__', '_list', '_viewer', 'events')

    def __init__(self, viewer=None):
        self._list = []
        self._viewer = None
        self.events = EmitterGroup(source=self,
                                   auto_connect=True,
                                   add_item=ItemEvent,
                                   remove_item=ItemEvent,
                                   reorder=Event)

        self.events.add_item.connect(self._add)
        self.events.remove_item.connect(self._remove)
        self.events.reorder.connect(self._reorder)

        # property setting - happens last
        self.viewer = viewer

    def __str__(self): return str(self._list)
    def __repr__(self): return repr(self._list)
    def __iter__(self): return iter(self._list)
    def __contains__(self, item): return item in self._list
    def __len__(self): return len(self._list)
    def __getitem__(self, i): return self._list[i]

    @property
    def viewer(self):
        """Viewer: Parent viewer.
        """
        if self._viewer is None:
            return self._viewer

        return self._viewer()

    @viewer.setter
    def viewer(self, viewer):
        prev = self.viewer
        if viewer == prev:
            return

        if prev is not None:
            self.events.add_item.disconnect(prev._on_layers_change)
            self.events.remove_item.disconnect(prev._on_layers_change)

        for layer in self:
            layer.viewer = viewer

        if viewer is not None:
            self.events.add_item.connect(viewer._on_layers_change)
            self.events.remove_item.connect(viewer._on_layers_change)
            viewer = weakref.ref(viewer)

        self._viewer = viewer

    def _to_index(self, obj):
        """Ensures that an object is a proper integer index.

        Parameters
        ----------
        obj : int or Layer
            Object to be converted.

        Returns
        -------
        index : int
            Index of the object if it is not already an int.
        """
        if _check_layer(obj):
            return self.index(obj)
        if not isinstance(obj, int):
            raise TypeError(f'expected {obj} to be int or Layer; '
                            f'got {type(obj)}') from None
        return obj

    def _reordered_list(self, ordering):
        """Generates the reordered list given an ordering.

        Parameters
        ----------
        ordering : iterable of int
            Ordering of the indices to use.

        Yields
        ------
        item : Layer
            Next layer in the ordered list.

        Raises
        ------
        ValueError
            When the improper indices are used.
        """
        expected = list(range(len(self)))

        for o in ordering:
            if not isinstance(o, int):
                raise TypeError(f'expected {o} to be int; '
                                f'got {type(o)}') from None
            try:
                expected.remove(o)
            except ValueError:
                raise ValueError(f'duplicate index: {o}') from None
            yield self._list[o]

        if expected:
            raise ValueError(f'indices {tuple(expected)} not provided')

    def append(self, item):
        """Appends a layer to the list.

        Parameters
        ----------
        item : Layer
            Layer to append.
        """
        _check_layer(item, error=True)

        self._list.append(item)
        self.events.add_item(item=item)

    def insert(self, index, item):
        """Inserts an item before an index.

        Parameters
        ----------
        index : int
            Index to insert before.
        item : Layer
            Layer to insert.
        """
        _check_layer(item, error=True)

        self._list.insert(index, item)
        self.events.add_item(item=item)

    def pop(self, index=-1):
        """Removes and returns an item given an index.

        Parameters
        ----------
        index : int, optional
            Index to remove.

        Returns
        -------
        item : Layer
            Removed item.
        """
        item = self._list.pop(index)
        self.events.remove_item(item=item)

    def remove(self, item):
        """Removes an item from the list.

        Parameters
        ----------
        item : Layer
            Item to remove.
        """
        self._list.remove(item)
        self.events.remove_item(item=item)

    def __delitem__(self, index):
        """Removes an item given its index.

        Parameters
        ----------
        index : int
            Index of the item to remove.
        """
        self.pop(index)

    def swap(self, a, b):
        """Swaps the ordering of two elements in the list.

        Parameters
        ----------
        a : Layer or int
            Layer to swap or its index.
        b : Layer or int
            Layer to swap or its index.
        """
        i = self._to_index(a)
        j = self._to_index(b)

        self._list[i], self._list[j] = self._list[j], self._list[i]
        self.events.reorder()

    def reorder(self, *ordering):
        """Reorders the list given an iterable of its elements
        or their indices.

        Parameters
        ----------
        ordering : iterable of Layer or int
            Ordering of the items. Can also be used as *args.

        Notes
        -----
        LayerList.reorder(i, j, k, ...)
        LayerList.reorder([i, j, k, ...])
        """
        if not isinstance(ordering[0], (int, Layer)):
            ordering = ordering[0]
            if not isinstance(ordering, Sequence):
                raise TypeError(f'expected {ordering} to be Sequence; '
                                f'got {type(ordering)}') from None

        self._list[:] = self._reordered_list(self._to_index(o)
                                             for o in ordering)
        self.events.reorder()

    def index(self, item, start=None, stop=None):
        """Finds the index of an item in the list.

        Parameters
        ----------
        item : object
            Querying item..
        start : int, optional
            Start of slice index to look.
        stop : int, optional
            Stop of slice index to look.

        Returns
        -------
        index : int
            Index of the item.

        Raises
        ------
        ValueError
            When the item is not in the list.
        """
        args = (item,)
        if stop is not None and start is None:
            start = 0

        if start is not None:
            args += (start,)

        if stop is not None:
            args += (stop,)

        return self._list.index(*args)

    def _add(self, event):
        """Callback when an item is added to set its order and viewer.
        """
        layer = event.item
        layer._order = -len(self)
        layer.viewer = self.viewer

    def _remove(self, event):
        """Callback when an item is removed to remove its viewer
        and reset its order.
        """
        layer = event.item
        layer.viewer = None
        layer._order = 0

    def _reorder(self, event):
        """Callback when the list is reordered to propagate those changes
        to the node draw order.
        """
        for i in range(len(self)):
            self[i]._order = -i
        canvas = self.viewer._canvas
        canvas._draw_order.clear()
        canvas.update()
