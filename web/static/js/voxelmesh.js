// Turns the voxel bundle into one BufferGeometry of visible cube faces.
//
// Only faces with an empty neighbour are emitted, which is most of the saving
// available here: the model is a shell, so the interior is already hollow.
// Positions are integers in grid units and ride in an Int16Array, which keeps
// the largest grid comfortably inside a phone's memory budget.

const AXES = [0, 1, 2];

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

/** The six face directions, each with a quad wound counter-clockwise from outside. */
const FACES = buildFaceTable();

function buildFaceTable() {
  const table = [];
  for (const axis of AXES) {
    for (const sign of [1, -1]) {
      const u = (axis + 1) % 3;
      const v = (axis + 2) % 3;
      const corners = [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ].map(([a, b]) => {
        const point = [0, 0, 0];
        point[axis] = sign > 0 ? 1 : 0;
        point[u] = a;
        point[v] = b;
        return point;
      });

      const normal = [0, 0, 0];
      normal[axis] = sign;
      // Wind the quad so its geometric normal agrees with the face normal,
      // rather than trusting a hand-written corner table.
      if (dot(cross(sub(corners[1], corners[0]), sub(corners[2], corners[0])), normal) < 0) {
        corners.reverse();
      }
      table.push({ axis, sign, normal, corners });
    }
  }
  return table;
}

/**
 * Build the mesh arrays.
 *
 * @returns {{position: Int16Array, normal: Int8Array, group: Uint8Array,
 *            color: Uint8Array, index: Uint32Array, quads: number}}
 */
export function buildMeshArrays(model) {
  const [nx, ny, nz] = model.header.grid.dims;
  const { x, y, z, group, color } = model.arrays;
  const count = model.count;

  const occupied = new Uint8Array(nx * ny * nz);
  const at = (a, b, c) => (a * ny + b) * nz + c;

  for (let i = 0; i < count; i += 1) occupied[at(x[i], y[i], z[i])] = 1;

  // Pass one counts the visible faces so every array is allocated exactly once.
  let quads = 0;
  for (let i = 0; i < count; i += 1) {
    for (const face of FACES) {
      const p = [x[i], y[i], z[i]];
      p[face.axis] += face.sign;
      if (p[face.axis] < 0 || p[face.axis] >= [nx, ny, nz][face.axis]) quads += 1;
      else if (!occupied[at(p[0], p[1], p[2])]) quads += 1;
    }
  }

  const position = new Int16Array(quads * 4 * 3);
  const normal = new Int8Array(quads * 4 * 3);
  const groupAttr = new Uint8Array(quads * 4);
  const colorAttr = new Uint8Array(quads * 4);
  const index = new Uint32Array(quads * 6);

  let vertex = 0;
  let tri = 0;
  for (let i = 0; i < count; i += 1) {
    const vx = x[i];
    const vy = y[i];
    const vz = z[i];
    for (const face of FACES) {
      const p = [vx, vy, vz];
      p[face.axis] += face.sign;
      const limit = [nx, ny, nz][face.axis];
      const outside = p[face.axis] < 0 || p[face.axis] >= limit;
      if (!outside && occupied[at(p[0], p[1], p[2])]) continue;

      const base = vertex;
      for (const corner of face.corners) {
        position[vertex * 3 + 0] = vx + corner[0];
        position[vertex * 3 + 1] = vy + corner[1];
        position[vertex * 3 + 2] = vz + corner[2];
        normal[vertex * 3 + 0] = face.normal[0] * 127;
        normal[vertex * 3 + 1] = face.normal[1] * 127;
        normal[vertex * 3 + 2] = face.normal[2] * 127;
        groupAttr[vertex] = group[i];
        colorAttr[vertex] = color[i];
        vertex += 1;
      }
      index[tri * 6 + 0] = base;
      index[tri * 6 + 1] = base + 1;
      index[tri * 6 + 2] = base + 2;
      index[tri * 6 + 3] = base;
      index[tri * 6 + 4] = base + 2;
      index[tri * 6 + 5] = base + 3;
      tri += 1;
    }
  }

  return { position, normal, group: groupAttr, color: colorAttr, index, quads };
}
