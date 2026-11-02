/**
 * The landing backdrop: two painted plates (light strokes on paper, light trails on
 * graphite) taken from the reference design with its interface removed, see
 * design/build_field_plates.py. The shader lays each plate over its sections, lets it
 * drift slowly and follows the pointer; the CSS grain overlay adds full-resolution grain.
 */

export type FieldFrame = {
  /** seconds */
  time: number
  /** pointer parallax in CSS px */
  shiftX: number
  shiftY: number
  /** viewport-relative CSS px of the section edges */
  heroTop: number
  storyTop: number
  storyBottom: number
  footerTop: number
}

export type LightField = {
  render(frame: FieldFrame): void
  resize(cssWidth: number, cssHeight: number): void
  dispose(): void
}

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`

const FRAG = `
precision highp float;
uniform sampler2D uPaper;   // hero plate: strokes on paper, horizon at the bottom
uniform sampler2D uNight;   // story plate: trails on graphite, continuing that horizon
uniform vec2 uView;         // CSS px
uniform vec2 uBuf;          // drawing-buffer px
uniform float uTime;
uniform vec2 uShift;        // CSS px
uniform vec4 uEdges;        // hero top, story top, story bottom, footer top (CSS px from viewport top)

// The plates are painted in full-chroma cobalt. Grade them softer so the field reads as
// light behind the content: ease the chroma (CSS saturate(), so the fallback plates in
// noise-field.css match), then lift paper toward white and dim the night glow. The paper
// plate's dark horizon (its bottom fifth) takes the night grade, so the seam stays whole.
const vec3 LUMA = vec3(0.213, 0.715, 0.072);
const vec3 PAPER = vec3(0.976, 0.988, 1.0);   // #f9fcff
const float PAPER_SATURATE = 0.9;
const float PAPER_LIFT = 0.5;
const float NIGHT_SATURATE = 0.72;
const float NIGHT_BRIGHTNESS = 0.78;
vec3 gradePaper(vec3 c) { return mix(mix(vec3(dot(c, LUMA)), c, PAPER_SATURATE), PAPER, PAPER_LIFT); }
vec3 gradeNight(vec3 c) { return mix(vec3(dot(c, LUMA)), c, NIGHT_SATURATE) * NIGHT_BRIGHTNESS; }
vec3 gradeField(vec3 c, float v) { return mix(gradePaper(c), gradeNight(c), smoothstep(0.76, 1.0, v)); }

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

// slow drift and pointer parallax, kept inside the plate so edges never smear
vec2 drift(vec2 uv, float t) {
  vec2 d = vec2(sin(uv.y * 5.0 + t * 0.21) + sin(uv.y * 11.0 - t * 0.13),
                cos(uv.x * 4.0 - t * 0.17) + sin(uv.x * 9.0 + t * 0.11)) * 0.0012;
  return clamp(0.5 + (uv - 0.5) * 0.992 + d - uShift / uView * 0.12, 0.0, 1.0);
}

void main() {
  vec2 css = vec2(gl_FragCoord.x, uBuf.y - gl_FragCoord.y) * (uView / uBuf);
  float H = uView.y;
  float y = css.y;
  float u = css.x / uView.x;
  float t = uTime;
  float heroTop = uEdges.x, st = uEdges.y, sb = uEdges.z, ft = uEdges.w;
  // narrower than 16:10, show a window of each plate rather than squeezing it
  float c = min(1.0, uView.x / H / 1.6);
  float up = clamp(0.36, c * 0.5, 1.0 - c * 0.5) + (u - 0.5) * c;   // around the main sweep
  float un = clamp(0.7, c * 0.5, 1.0 - c * 0.5) + (u - 0.5) * c;    // around the arc beside the product

  // the hero plate fills the first screen and scrolls with the hero; night takes over at
  // its bottom edge (or the story's top, if sooner), where the two plates were one image
  float dusk = min(st, heroTop + H);
  float vp = (y - heroTop) / max(dusk - heroTop, 1.0);
  vec3 paper = gradeField(texture2D(uPaper, drift(vec2(up, vp), t)).rgb, vp);
  // story plate stays with the pinned stage, then leaves with the section
  float stage = min(max(dusk, 0.0), sb - H);
  vec3 night = gradeNight(texture2D(uNight, drift(vec2(un, (y - stage) / H), t)).rgb);
  // between story and footer the paper plate returns mirrored: horizon, open paper, horizon
  float k = clamp((y - sb) / max(ft - sb, 1.0), 0.0, 1.0);
  float va = abs(1.0 - 2.0 * k);
  vec3 after = gradeField(texture2D(uPaper, drift(vec2(up, va), t)).rgb, va);
  // the footer picks the night plate up again from its top row
  vec3 footer = gradeNight(texture2D(uNight, drift(vec2(un, (y - ft) / H), t)).rgb);

  vec3 col = y < dusk ? paper : y < sb ? night : y < ft ? after : footer;
  // a soft handover where the story gives way to paper again
  col = mix(col, night, (1.0 - smoothstep(sb, sb + 160.0, y)) * step(sb, y) * step(y, ft));

  // dither against 8-bit banding
  col += (hash(gl_FragCoord.xy + fract(t)) - 0.5) / 255.0;
  gl_FragColor = vec4(col, 1.0);
}
`

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const sh = gl.createShader(type)
  if (!sh) return null
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn('light field shader:', gl.getShaderInfoLog(sh))
    gl.deleteShader(sh)
    return null
  }
  return sh
}

function plateTexture(gl: WebGLRenderingContext, unit: number, image: HTMLImageElement) {
  const tex = gl.createTexture()
  gl.activeTexture(gl.TEXTURE0 + unit)
  gl.bindTexture(gl.TEXTURE_2D, tex)
  // keep the plate's sRGB values exactly as painted
  gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, image)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  return tex
}

/** Pixels drawn per CSS pixel; the plates are soft, so a reduced buffer is invisible. */
const BUFFER_SCALE = 0.75
const MAX_BUFFER_PIXELS = 1_400_000

export function createLightField(canvas: HTMLCanvasElement, plates: { paper: HTMLImageElement; night: HTMLImageElement }): LightField | null {
  const gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: 'low-power', preserveDrawingBuffer: false })
  if (!gl) return null
  const vs = compile(gl, gl.VERTEX_SHADER, VERT)
  const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG)
  if (!vs || !fs) return null
  const prog = gl.createProgram()!
  gl.attachShader(prog, vs)
  gl.attachShader(prog, fs)
  gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null
  gl.useProgram(prog)

  const buf = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, buf)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
  const aPos = gl.getAttribLocation(prog, 'aPos')
  gl.enableVertexAttribArray(aPos)
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0)

  const textures = [plateTexture(gl, 0, plates.paper), plateTexture(gl, 1, plates.night)]
  gl.uniform1i(gl.getUniformLocation(prog, 'uPaper'), 0)
  gl.uniform1i(gl.getUniformLocation(prog, 'uNight'), 1)
  const u = {
    view: gl.getUniformLocation(prog, 'uView'),
    buf: gl.getUniformLocation(prog, 'uBuf'),
    time: gl.getUniformLocation(prog, 'uTime'),
    shift: gl.getUniformLocation(prog, 'uShift'),
    edges: gl.getUniformLocation(prog, 'uEdges'),
  }
  let cssW = 1
  let cssH = 1

  return {
    resize(w, h) {
      cssW = Math.max(1, w)
      cssH = Math.max(1, h)
      const scale = Math.min(BUFFER_SCALE, Math.sqrt(MAX_BUFFER_PIXELS / (cssW * cssH)))
      canvas.width = Math.max(1, Math.round(cssW * scale))
      canvas.height = Math.max(1, Math.round(cssH * scale))
      gl.viewport(0, 0, canvas.width, canvas.height)
    },
    render(f) {
      gl.uniform2f(u.view, cssW, cssH)
      gl.uniform2f(u.buf, canvas.width, canvas.height)
      gl.uniform1f(u.time, f.time)
      gl.uniform2f(u.shift, f.shiftX, f.shiftY)
      gl.uniform4f(u.edges, f.heroTop, f.storyTop, f.storyBottom, f.footerTop)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    },
    dispose() {
      for (const tex of textures) gl.deleteTexture(tex)
      gl.deleteBuffer(buf)
      gl.deleteProgram(prog)
      gl.deleteShader(vs)
      gl.deleteShader(fs)
    },
  }
}
