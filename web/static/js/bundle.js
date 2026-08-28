// Reads the .pxob bundle the Python pipeline emits. Format: docs/model-format.md.

const MAGIC = 0x50584f42; // "PXOB"
const GZIP_MAGIC = 0x1f8b;

/**
 * Fetch and decode a bundle.
 *
 * The gzipped file is fetched directly so the wire size holds even on a server
 * that has not been told to compress. If the server does set Content-Encoding
 * the browser has already unwrapped it for us, so we sniff the magic number
 * rather than trusting the file extension.
 */
export async function loadBundle(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`bundle fetch failed: ${response.status}`);
  let buffer = await response.arrayBuffer();

  const head = new DataView(buffer);
  if (head.byteLength >= 2 && head.getUint16(0, false) === GZIP_MAGIC) {
    if (typeof DecompressionStream !== 'function') {
      const plain = await fetch(url.replace(/\.gz$/, ''));
      if (!plain.ok) throw new Error('no gzip support and no uncompressed bundle');
      buffer = await plain.arrayBuffer();
    } else {
      const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'));
      buffer = await new Response(stream).arrayBuffer();
    }
  }
  return decode(buffer);
}

export function decode(buffer) {
  const view = new DataView(buffer);
  if (view.getUint32(0, false) !== MAGIC) throw new Error('not a pxob bundle');
  const version = view.getUint16(4, true);
  if (version !== 1) throw new Error(`unsupported bundle version ${version}`);
  const headerLength = view.getUint32(6, true);
  const count = view.getUint32(10, true);

  const headerStart = 14;
  const header = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buffer, headerStart, headerLength))
  );

  const arrays = {};
  let offset = headerStart + headerLength;
  for (const spec of header.arrays) {
    if (spec.type === 'uint16') {
      // The body is not guaranteed to be 2-byte aligned, so copy rather than view.
      arrays[spec.name] = new Uint16Array(buffer.slice(offset, offset + count * 2));
      offset += count * 2;
    } else {
      arrays[spec.name] = new Uint8Array(buffer.slice(offset, offset + count));
      offset += count;
    }
  }

  return { header, arrays, count };
}

/** Flatten the header's palette ramp into the RGB bytes a DataTexture wants. */
export function rampTexels(header) {
  const ramp = header.palette.ramp;
  const bytes = new Uint8Array(ramp.length * 4);
  for (let i = 0; i < ramp.length; i += 1) {
    bytes[i * 4 + 0] = ramp[i][0];
    bytes[i * 4 + 1] = ramp[i][1];
    bytes[i * 4 + 2] = ramp[i][2];
    bytes[i * 4 + 3] = 255;
  }
  return bytes;
}
