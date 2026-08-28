// The pixel pipeline: render the voxel shell into a small offscreen target,
// posterize and dither it in the fragment shader, add a one-pixel outline in a
// post pass, then let CSS blow the whole thing up with nearest-neighbour.
//
// Colour management is deliberately switched off. The palette in the bundle is
// already in display sRGB, and the offline renderer writes those exact bytes,
// so any conversion here would make the two renderers disagree.

import * as THREE from '../vendor/three/three.module.min.js';
import { buildMeshArrays } from './voxelmesh.js';
import { rampTexels } from './bundle.js';

// The offscreen buffer is sized from the viewport rather than pinned, so the
// blocks come out roughly the same size on a phone and on a desktop. A fixed
// 240 meant a laptop upscaled 5.4x against a phone's 1.8x: the same picture,
// but four times chunkier on the bigger screen, and only 1.6 buffer pixels per
// voxel, which is too few to resolve a cube at all.
const UPSCALE = 2.5;
export const MIN_INTERNAL_HEIGHT = 240;
export const MAX_INTERNAL_HEIGHT = 480;
const MAX_GROUPS = 8;
const KEY_LIGHT = new THREE.Vector3(0.55, 0.72, 0.42).normalize();
const AMBIENT = 0.34;
const BACKGROUND = 0x0a0d13;
const FALLBACK_OUTLINE = '#3a424e';
// The starfield lives on its own sphere with its own camera, so it never
// competes with the model for depth range and never gets clipped by it.
const STAR_RADIUS = 1000;
const STAR_COUNT = 460;

const MODEL_VERTEX = /* glsl */ `
  attribute float aGroup;
  attribute float aColor;
  uniform vec3 uExplode[${MAX_GROUPS}];
  uniform float uExplodeAmount;
  uniform vec3 uLight;
  uniform float uAmbient;
  varying float vColor;
  varying float vShade;
  varying float vGroup;

  void main() {
    int gid = int(aGroup + 0.5);
    vec3 offset = uExplode[gid] * uExplodeAmount;
    vec3 n = normalize(normal);
    vShade = uAmbient + (1.0 - uAmbient) * max(dot(n, normalize(uLight)), 0.0);
    vColor = aColor;
    vGroup = aGroup;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position + offset, 1.0);
  }
`;

const MODEL_FRAGMENT = /* glsl */ `
  precision highp float;
  uniform sampler2D uRamp;
  uniform float uShades;
  uniform float uDither;
  uniform float uHighlight;
  varying float vColor;
  varying float vShade;
  varying float vGroup;

  // Compact ordered 4x4 Bayer, built from two 2x2 lookups.
  float bayer2(vec2 a) { a = floor(a); return fract(a.x / 2.0 + a.y * a.y * 0.75); }

  void main() {
    float level = vShade * (uShades - 1.0);
    float d = (bayer2(0.5 * gl_FragCoord.xy) * 0.25 + bayer2(gl_FragCoord.xy)) - 0.5;
    level += d * uDither;
    float step = clamp(floor(level + 0.5), 0.0, uShades - 1.0);
    float base = vColor;

    if (uHighlight >= 0.0) {
      if (abs(vGroup - uHighlight) > 0.5) {
        // Everything else drops to the darkest charcoal, the way the contact
        // sheet does it. Taking one shade step off was far too subtle to answer
        // the only question a hover asks: which bit is that?
        base = 2.0;
        step = 0.0;
      } else {
        step = min(step + 1.0, uShades - 1.0);
      }
    }

    vec2 uv = vec2((step + 0.5) / uShades, (base + 0.5) / 16.0);
    // Alpha carries the group id so the outline pass can find a real boundary
    // instead of inferring one from depth. Background stays at 1.0.
    gl_FragColor = vec4(texture2D(uRamp, uv).rgb, (vGroup + 1.0) / 255.0);
  }
`;

const PICK_FRAGMENT = /* glsl */ `
  precision highp float;
  varying float vColor;
  varying float vShade;
  varying float vGroup;
  void main() {
    // Group id plus one, so zero stays free to mean background.
    gl_FragColor = vec4((vGroup + 1.0) / 255.0, 0.0, 0.0, 1.0);
  }
`;

const STAR_VERTEX = /* glsl */ `
  attribute float aTone;
  uniform vec3 uViewDir;
  varying float vTone;
  void main() {
    vTone = aTone;
    gl_PointSize = 1.0;
    // Draw only the half of the celestial sphere in front of the camera.
    // Rendering both halves put the near and far hemispheres on screen at once,
    // sliding in opposite directions, which is what made the sky look wrong.
    if (dot(normalize(position), uViewDir) < 0.0) {
      gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
      return;
    }
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const STAR_FRAGMENT = /* glsl */ `
  precision highp float;
  varying float vTone;
  void main() { gl_FragColor = vec4(vTone, vTone, min(vTone + 0.06, 1.0), 1.0); }
`;

const POST_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const POST_FRAGMENT = /* glsl */ `
  precision highp float;
  uniform sampler2D tColor;
  uniform sampler2D tDepth;
  uniform vec2 uTexel;
  uniform vec3 uOutline;
  uniform float uOutlineOn;
  uniform float uOutlineDepth;
  uniform float uScanlines;
  varying vec2 vUv;

  void main() {
    vec4 src = texture2D(tColor, vUv);
    vec3 rgb = src.rgb;
    float depth = texture2D(tDepth, vUv).r;

    if (uOutlineOn > 0.5 && depth < 1.0) {
      // Two tests. The first compares the group id the model pass wrote into
      // alpha, which is exact: a silhouette against the sky and a boundary
      // between two components can never flicker.
      float idL = texture2D(tColor, vUv - vec2(uTexel.x, 0.0)).a;
      float idR = texture2D(tColor, vUv + vec2(uTexel.x, 0.0)).a;
      float idD = texture2D(tColor, vUv - vec2(0.0, uTexel.y)).a;
      float idU = texture2D(tColor, vUv + vec2(0.0, uTexel.y)).a;
      float idBreak = max(max(abs(idL - src.a), abs(idR - src.a)),
                          max(abs(idD - src.a), abs(idU - src.a)));

      // The second catches one part passing behind another within the same
      // group. Second difference, not first: a plate seen almost edge on has a
      // huge depth gradient but no curvature, and a first-difference test
      // painted the whole solar array as one flat slab of outline.
      float left = texture2D(tDepth, vUv - vec2(uTexel.x, 0.0)).r;
      float right = texture2D(tDepth, vUv + vec2(uTexel.x, 0.0)).r;
      float down = texture2D(tDepth, vUv - vec2(0.0, uTexel.y)).r;
      float up = texture2D(tDepth, vUv + vec2(0.0, uTexel.y)).r;
      float bend = max(abs(left + right - 2.0 * depth), abs(down + up - 2.0 * depth));

      if (idBreak > 0.002 || bend > uOutlineDepth) rgb = uOutline;
    }

    if (uScanlines > 0.0) {
      // Every other row loses a couple of percent. Any more and small type
      // rendered over the canvas stops being readable.
      float row = mod(floor(gl_FragCoord.y), 2.0);
      rgb *= 1.0 - uScanlines * row;
      vec2 centred = vUv - 0.5;
      rgb *= 1.0 - uScanlines * 1.6 * dot(centred, centred);
    }

    gl_FragColor = vec4(rgb, 1.0);
  }
`;

export class Observatory {
  constructor(canvas, model, options = {}) {
    this.model = model;
    this.dims = model.header.grid.dims;
    this.groups = model.header.groups;
    this.options = {
      dither: 0.55,
      outline: true,
      scanlines: 0.05,
      ...options,
    };

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      alpha: false,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(1);
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    this.renderer.setClearColor(BACKGROUND, 1);

    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 4000);

    this._buildRamp();
    this._prepareMesh();
    this._buildStars();
    this._buildPost();

    this.highlight = -1;
    this.explode = 0;
    this.size = { width: 2, height: 2 };
  }

  get groupCount() {
    return this.groups.length;
  }

  _buildRamp() {
    const shades = this.model.header.palette.shades.length;
    const texture = new THREE.DataTexture(
      rampTexels(this.model.header),
      shades,
      16,
      THREE.RGBAFormat
    );
    texture.magFilter = THREE.NearestFilter;
    texture.minFilter = THREE.NearestFilter;
    texture.needsUpdate = true;
    this.ramp = texture;
    this.shades = shades;
  }

  /**
   * Everything the renderer needs before it can draw a frame, none of which is
   * expensive: uniforms, materials, explode vectors, the points the camera
   * frames against. The geometry is deliberately not built here, so the sky and
   * the interface can be on screen while it is.
   */
  _prepareMesh() {
    const explode = [];
    for (let i = 0; i < MAX_GROUPS; i += 1) {
      const g = this.groups[i];
      explode.push(g ? new THREE.Vector3(...g.explode) : new THREE.Vector3());
    }
    this.explodeVectors = explode;
    // Explode distance is expressed in grid units, scaled off the long axis so
    // it looks the same however fine the grid is.
    this.explodeScale = Math.max(...this.dims) * 0.32;
    // Longest explode vector, unitless; multiplied by the live amount when framing.
    this.maxExplodeVector = Math.max(...explode.map((v) => v.length()), 0);

    this.uniforms = {
      uRamp: { value: this.ramp },
      uShades: { value: this.shades },
      uDither: { value: this.options.dither },
      uHighlight: { value: -1 },
      uLight: { value: KEY_LIGHT.clone() },
      uAmbient: { value: AMBIENT },
      uExplode: { value: explode },
      uExplodeAmount: { value: 0 },
    };

    const material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: MODEL_VERTEX,
      fragmentShader: MODEL_FRAGMENT,
    });

    this.pickUniforms = {
      uLight: { value: KEY_LIGHT.clone() },
      uAmbient: { value: AMBIENT },
      uExplode: { value: explode },
      uExplodeAmount: { value: 0 },
    };
    this.pickMaterial = new THREE.ShaderMaterial({
      uniforms: this.pickUniforms,
      vertexShader: MODEL_VERTEX,
      fragmentShader: PICK_FRAGMENT,
    });

    this._buildFitPoints();
    this.material = material;
  }

  /**
   * The expensive half: roughly 200k quads walked out of the voxel bundle into
   * typed arrays. Call it after a frame has painted, or the first thing the
   * visitor gets is a locked main thread.
   */
  buildGeometry() {
    if (this.mesh) return;
    const arrays = buildMeshArrays(this.model);
    this.quadCount = arrays.quads;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(arrays.position, 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(arrays.normal, 3, true));
    geometry.setAttribute('aGroup', new THREE.BufferAttribute(arrays.group, 1));
    geometry.setAttribute('aColor', new THREE.BufferAttribute(arrays.color, 1));
    geometry.setIndex(new THREE.BufferAttribute(arrays.index, 1));

    this.mesh = new THREE.Mesh(geometry, this.material);
    this.mesh.position.set(-this.dims[0] / 2, -this.dims[1] / 2, -this.dims[2] / 2);
    this.mesh.frustumCulled = false;
    this.scene.add(this.mesh);
  }

  /**
   * A subsample of the actual occupied voxels, centred, used to frame the
   * camera. Fitting the grid's bounding box instead wastes the frame: the box
   * corners are empty sky, so at most angles the observatory sat at about two
   * thirds the size it could have been. Worst on a phone, where the frame is
   * fitted by width to begin with.
   */
  _buildFitPoints() {
    const { x, y, z } = this.model.arrays;
    const count = this.model.count;
    const stride = Math.max(1, Math.floor(count / 4000));
    const half = [this.dims[0] / 2, this.dims[1] / 2, this.dims[2] / 2];
    const points = [];
    for (let i = 0; i < count; i += stride) {
      points.push(x[i] - half[0], y[i] - half[1], z[i] - half[2]);
    }
    this.fitPoints = new Float32Array(points);
  }

  _buildStars() {
    const radius = STAR_RADIUS;
    const count = STAR_COUNT;
    const positions = new Float32Array(count * 3);
    const tones = new Float32Array(count);
    // Fixed seed: the sky is part of the artwork, not a random draw per load.
    let seed = 20270501;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) % 4294967296;
      return seed / 4294967296;
    };
    for (let i = 0; i < count; i += 1) {
      const u = random() * 2 - 1;
      const theta = random() * Math.PI * 2;
      const r = Math.sqrt(1 - u * u);
      positions[i * 3 + 0] = Math.cos(theta) * r * radius;
      positions[i * 3 + 1] = u * radius;
      positions[i * 3 + 2] = Math.sin(theta) * r * radius;
      tones[i] = [0.11, 0.15, 0.22, 0.33][Math.floor(random() * 4)];
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aTone', new THREE.BufferAttribute(tones, 1));

    this.starUniforms = { uViewDir: { value: new THREE.Vector3(0, 0, -1) } };
    const material = new THREE.ShaderMaterial({
      uniforms: this.starUniforms,
      vertexShader: STAR_VERTEX,
      fragmentShader: STAR_FRAGMENT,
      depthTest: false,
      depthWrite: false,
    });
    this.stars = new THREE.Points(geometry, material);
    this.stars.frustumCulled = false;
    this.starScene = new THREE.Scene();
    this.starScene.add(this.stars);
    this.starCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, -1, 1);
  }

  /** Point the star camera the same way as the main one, at a fixed scale.

      Sharing the main camera would either clip the sky or drag the model's
      depth range out to the stars and cost the outline pass its precision.
      A separate camera also keeps the sky from zooming, which is correct: the
      stars are a long way further off than the zoom is pretending to travel. */
  _updateStarCamera() {
    const { width, height } = this.size;
    const camera = this.starCamera;
    camera.position.copy(this.camera.position);
    camera.quaternion.copy(this.camera.quaternion);
    // Frame the middle of the projected disc, never its rim. At the rim a star
    // sits exactly on the hemisphere boundary, so it would blink in and out as
    // the camera turned past it.
    // 0.68 rather than 0.75: the frame corner is sqrt(2) further out than its
    // edge, so on a square window 0.75 would push the corners past the
    // hemisphere boundary and stars would blink there.
    const half = STAR_RADIUS * 0.68;
    if (width >= height) {
      camera.right = half;
      camera.top = (half * height) / width;
    } else {
      camera.top = half;
      camera.right = (half * width) / height;
    }
    camera.left = -camera.right;
    camera.bottom = -camera.top;
    camera.near = -STAR_RADIUS * 4;
    camera.far = STAR_RADIUS * 4;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();

    // Forward, in world space: the camera always looks at the origin.
    this.starUniforms.uViewDir.value.copy(camera.position).multiplyScalar(-1).normalize();
  }

  /**
   * Build (or rebuild) the offscreen targets at a given size.
   *
   * The depth texture is recreated rather than resized: RenderTarget.setSize
   * grows the colour attachments but leaves an attached depth texture at its
   * original size, which silently gives the outline pass a flat depth buffer
   * and no edges to find.
   */
  _makeTargets(width, height) {
    this.target?.dispose();
    this.target?.depthTexture?.dispose();
    this.pickTarget?.dispose();

    const depth = new THREE.DepthTexture(width, height);
    depth.minFilter = THREE.NearestFilter;
    depth.magFilter = THREE.NearestFilter;

    this.target = new THREE.WebGLRenderTarget(width, height, {
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      depthBuffer: true,
      depthTexture: depth,
    });
    this.pickTarget = new THREE.WebGLRenderTarget(width, height, {
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
    });

    if (this.postUniforms) {
      this.postUniforms.tColor.value = this.target.texture;
      this.postUniforms.tDepth.value = depth;
      this.postUniforms.uTexel.value.set(1 / width, 1 / height);
    }
  }

  _buildPost() {
    this._makeTargets(2, 2);

    this.postUniforms = {
      tColor: { value: this.target.texture },
      tDepth: { value: this.target.depthTexture },
      uTexel: { value: new THREE.Vector2(1 / 2, 1 / 2) },
      uOutline: {
        // From the bundle, so the offline renderer and this one cannot drift.
        value: new THREE.Color(this.model.header.palette.outline || FALLBACK_OUTLINE),
      },
      uOutlineOn: { value: this.options.outline ? 1 : 0 },
      uOutlineDepth: { value: 0.008 },
      uScanlines: { value: this.options.scanlines },
    };
    this.postScene = new THREE.Scene();
    this.postCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.postScene.add(
      new THREE.Mesh(
        new THREE.PlaneGeometry(2, 2),
        new THREE.ShaderMaterial({
          uniforms: this.postUniforms,
          vertexShader: POST_VERTEX,
          fragmentShader: POST_FRAGMENT,
          depthTest: false,
          depthWrite: false,
        })
      )
    );
  }

  /** Resize the internal buffer to match the canvas aspect ratio. */
  resize(cssWidth, cssHeight) {
    const target = Math.min(
      Math.max(Math.round(cssHeight / UPSCALE), MIN_INTERNAL_HEIGHT),
      MAX_INTERNAL_HEIGHT,
      // Never render more rows than the canvas has: downscaling a pixel grid
      // just throws the pixels away again.
      Math.max(Math.round(cssHeight), 2)
    );
    const height = Math.max(2, target);
    const width = Math.max(2, Math.round((height * cssWidth) / Math.max(cssHeight, 1)));
    if (width === this.size.width && height === this.size.height) return;

    this.size = { width, height };
    this.renderer.setSize(width, height, false);
    this._makeTargets(width, height);
    this.frameCamera();
  }

  /**
   * Fit the orthographic camera to the model's silhouette from wherever the
   * camera currently sits. Fitting the bounding sphere instead would waste most
   * of the frame: this observatory is nearly three times longer than it is tall.
   */
  frameCamera(zoom = this.zoom || 1) {
    this.zoom = zoom;
    const { width, height } = this.size;
    const radius = Math.hypot(...this.dims) / 2;

    this.camera.updateMatrixWorld();
    const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 1);

    let spanX = 0;
    let spanY = 0;
    const points = this.fitPoints;
    const rx = right.x;
    const ry = right.y;
    const rz = right.z;
    const ux = up.x;
    const uy = up.y;
    const uz = up.z;
    for (let i = 0; i < points.length; i += 3) {
      const px = points[i];
      const py = points[i + 1];
      const pz = points[i + 2];
      const sx = Math.abs(px * rx + py * ry + pz * rz);
      const sy = Math.abs(px * ux + py * uy + pz * uz);
      if (sx > spanX) spanX = sx;
      if (sy > spanY) spanY = sy;
    }
    // Half a voxel for the sample that was skipped, plus the cube's own extent.
    spanX += 1;
    spanY += 1;

    // Pulling the model apart makes it bigger, so widen the frame to match
    // rather than letting the pieces slide off the edges.
    const bulge = (this.uniforms?.uExplodeAmount.value ?? 0) * (this.maxExplodeVector ?? 0);
    spanX += bulge;
    spanY += bulge;

    const scale = Math.max((spanX * 1.06) / (width / 2), (spanY * 1.06) / (height / 2)) / zoom;
    this.camera.left = (-scale * width) / 2;
    this.camera.right = (scale * width) / 2;
    this.camera.top = (scale * height) / 2;
    this.camera.bottom = (-scale * height) / 2;

    // Wrap near and far tightly around the model, plus whatever room the
    // exploded view needs. A loose frustum leaves the depth buffer too coarse
    // for the outline pass to see the step between two overlapping parts.
    const distance = this.camera.position.length() || radius * 3;
    const halfDepth = radius * 1.25 + this.explodeScale * 1.5;
    this.camera.near = Math.max(distance - halfDepth, 0.1);
    this.camera.far = distance + halfDepth;
    this.camera.updateProjectionMatrix();

    if (this.postUniforms) {
      // Roughly three voxels of depth curvature. The id test already catches
      // every silhouette and component boundary exactly, so this one can afford
      // to be conservative, and a conservative threshold is what stops the
      // outline shimmering as the model turns.
      const range = this.camera.far - this.camera.near;
      this.postUniforms.uOutlineDepth.value = 3.2 / range;
    }
  }

  setHighlight(groupIndex) {
    this.highlight = groupIndex;
    this.uniforms.uHighlight.value = groupIndex;
  }

  setExplode(amount) {
    this.explode = amount;
    const scaled = amount * this.explodeScale;
    this.uniforms.uExplodeAmount.value = scaled;
    this.pickUniforms.uExplodeAmount.value = scaled;
    this.frameCamera();
  }

  setOutline(enabled) {
    this.options.outline = enabled;
    this.postUniforms.uOutlineOn.value = enabled ? 1 : 0;
  }

  setDither(amount) {
    this.options.dither = amount;
    this.uniforms.uDither.value = amount;
  }

  render() {
    this.renderer.setRenderTarget(this.target);
    this.renderer.autoClear = true;
    this.renderer.clear();
    this.renderer.autoClear = false;
    this._updateStarCamera();
    this.renderer.render(this.starScene, this.starCamera);
    this.renderer.render(this.scene, this.camera);
    this.renderer.autoClear = true;
    this.renderer.setRenderTarget(null);
    this.renderer.render(this.postScene, this.postCamera);
  }

  /**
   * Read the group under a canvas-relative point, or -1 for empty sky.
   * Costs one extra draw, so callers should throttle to once per frame.
   */
  pick(cssX, cssY, cssWidth, cssHeight) {
    if (!this.mesh) return -1;
    const x = Math.round((cssX / Math.max(cssWidth, 1)) * this.size.width);
    const y = Math.round((1 - cssY / Math.max(cssHeight, 1)) * this.size.height);
    if (x < 0 || y < 0 || x >= this.size.width || y >= this.size.height) return -1;

    this.scene.overrideMaterial = this.pickMaterial;
    this.renderer.setRenderTarget(this.pickTarget);
    this.renderer.setClearColor(0x000000, 1);
    this.renderer.clear();
    this.renderer.render(this.scene, this.camera);
    this.renderer.setClearColor(BACKGROUND, 1);
    this.scene.overrideMaterial = null;

    const pixel = new Uint8Array(4);
    this.renderer.readRenderTargetPixels(this.pickTarget, x, y, 1, 1, pixel);
    this.renderer.setRenderTarget(null);
    return pixel[0] === 0 ? -1 : pixel[0] - 1;
  }

  dispose() {
    this.mesh?.geometry.dispose();
    this.material?.dispose();
    this.pickMaterial.dispose();
    this.target.dispose();
    this.pickTarget.dispose();
    this.renderer.dispose();
  }
}
