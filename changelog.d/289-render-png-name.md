**Fixed**
- `cadagent.publish.render.Renderer.render` adds `.png` to a name with no extension, and refuses any other extension before rendering. A bare name used to render the whole scene, then fail in Pillow (#289).
