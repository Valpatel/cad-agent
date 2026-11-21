**Fixed**

- Removing an inline 3D model viewer releases its renderer, observers, and event handlers. Reattaching it restores the controls and adjusts touch gestures to its new scroll container (#771).
