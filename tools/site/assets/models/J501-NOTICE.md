# J501 display-model attribution and changes

The real carrier-board geometry derives from **Seeed Studio's OSHW-Jetson-Series**,
revision `c982ee71b305aabd0c1c7c1caac38122e63cd9e1`, under the
[Apache License 2.0](J501-BOARD-LICENSE.txt).

[Immutable upstream board source](https://github.com/Seeed-Studio/OSHW-Jetson-Series/blob/c982ee71b305aabd0c1c7c1caac38122e63cd9e1/reServer%20Jetson%20carrier%20board/reServer%20Industrial%20J501/3D%20Model/RESERVER_AGX_ORIN_CARRIER_BOARD.stp.gz).
The inflated STEP SHA-256 is
`a131fdc60ed76df660e5d491c45af852d28f16e2f0d7f11de0152da4c5f45793`,
identical to the project reference used for the captured mesh. The raw vendor CAD
is not copied into this site.

Changes for this display derivative: tessellated project reference placed at the
configured `[15, 15, 20]` mm assembly offset; render-only 0.4 mm vertex-cell
centroid clustering; degenerate display triangles omitted; welded/quantized mesh
buffers packed for the shared web viewer. These display meshes are not dimensional,
manufacturing, RF or physical-fit evidence. Input hashes and source identities are
recorded in `j501-source.json`.

The enclosure and original project-generated cooler geometry retain their project
provenance. This board licence does **not** grant rights to separate NVIDIA model
assets. The standalone `agx_module` vendor part is omitted from this display pack.

The fitted lid and four optional original antenna display shapes come from product
main `97d7c7e46e11d5d52c4c15879dbe09deac07057c`. The antenna recipe uses public
manufacturer numerical dimensions, with no vendor drawing or vendor mesh copied.
These optional context parts do not establish RF selection, physical connector fit,
purchase BOM or print qualification. Their exact source/recipe/artifact hashes and
placement assumptions are retained in `j501-source.json`. The original captured
assembly exports have no embedded producer revision; CAD input tree equality binds
them to this main without claiming a fresh CAD regeneration.

The opposite CELL pair uses the separately cited Taoglas TG.22.0152 mechanical
reference. Its older 800–2200 MHz penta-band description is not an LTE/5G or
installed-modem qualification. Neither reference is a selected purchase part.
