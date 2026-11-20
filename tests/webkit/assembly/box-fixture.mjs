/** An axis-aligned box for browser fixtures, with binary STL bytes and matching bounds in millimetres. */
export function cube(origin, size) {
  const vertices = Array.from({ length: 8 }, (_, i) => origin.map((n, axis) => n + (i & (1 << axis) ? size[axis] : 0)));
  const faces = [[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4], [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]];
  const bytes = Buffer.alloc(84 + 50 * faces.length); bytes.writeUInt32LE(faces.length, 80);
  faces.forEach((face, i) => face.forEach((vertex, j) => vertices[vertex].forEach((n, k) => bytes.writeFloatLE(n, 84 + 50 * i + 12 + j * 12 + k * 4))));
  return { bytes, bounds: [...origin, ...origin.map((n, i) => n + size[i])] };
}
