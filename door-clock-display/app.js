const DEFAULT_CONFIG = {
  time: { use24Hour: true },
  palette: {
    background: "#06090f",
    core: "#d7e5ff",
    ambient: "#4a6fa5"
  },
  layout: {
    textWidthRatio: 0.82,
    textHeightRatio: 0.55,
    fontFamily: "'Courier New', Consolas, monospace",
    fontWeight: "bold"
  },
  motion: {
    particleCount: 900,
    ambientRatio: 0.06,
    approach: 0.15,
    scatterDecay: 0.85,
    jitter: 1.2,
    wanderSpeed: 0.4,
    scatterForce: 0.5
  },
  render: {
    sizeMin: 1.4,
    sizeMax: 2.0,
    coreScale: 1.5,
    coreAlpha: 0.6,
    glowScale: 4.5,
    glowAlpha: 0.07,
    ambientScale: 0.5,
    ambientAlpha: 0.06,
    dprCap: 1,
    fps: 30
  },
  background: {
    count: 260,
    sizeMin: 0.8,
    sizeMax: 2.0,
    speed: 0.25,
    alpha: 0.45,
    glowAlpha: 0.1,
    glowScale: 4,
    linkDist: 130,
    linkAlpha: 0.18,
    linkWidth: 0.8
  },
  drag: {
    force: 3.5,
    radius: 110,
    clockForceRatio: 0.6,
    trailFadeMs: 1200,
    trailWidth: 1.5,
    trailGlow: 8,
    trailColor: "#5a9fff"
  },
  interaction: {
    enabled: true,
    radius: 160,
    burstForce: 10,
    pulseDuration: 600,
    pulseForce: 3,
    dblClickWindow: 280
  }
};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const rand = (a, b) => Math.random() * (b - a) + a;
const TAU = Math.PI * 2;

function deepMerge(base, patch) {
  if (!patch || typeof patch !== "object") return structuredClone(base);
  const out = { ...base };
  for (const k of Object.keys(patch)) {
    const b = base?.[k], p = patch[k];
    out[k] =
      b && p && typeof b === "object" && !Array.isArray(b) &&
      typeof p === "object" && !Array.isArray(p)
        ? deepMerge(b, p) : p;
  }
  return out;
}

function hexToRgb(hex) {
  const c = String(hex || "").replace("#", "");
  const f = c.length === 3 ? c.split("").map(ch => ch + ch).join("") : c;
  const n = parseInt(f, 16);
  return Number.isFinite(n)
    ? { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
    : { r: 215, g: 229, b: 255 };
}

async function loadConfig() {
  try {
    const r = await fetch("./config.json", { cache: "no-store" });
    if (!r.ok) throw 0;
    return deepMerge(DEFAULT_CONFIG, await r.json());
  } catch {
    return structuredClone(DEFAULT_CONFIG);
  }
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

class ParticleClock {
  constructor(canvas, config) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.cfg = config;
    this.w = 0;
    this.h = 0;
    this.dpr = 1;
    this.frameMs = 1000 / clamp(config.render.fps, 15, 60);
    this.prevTs = 0;
    this.timeKey = "";

    this.targets = [];
    this.particles = [];
    this.bgParticles = [];
    this.effects = [];
    this.dragTrail = [];

    this.visible = true;
    this._ptrId = null;
    this._ptrStart = null;
    this._isDrag = false;
    this._suppressClick = false;
    this.pendingClick = null;
    this.clickTimer = null;

    const cRgb = hexToRgb(config.palette.core);
    const aRgb = hexToRgb(config.palette.ambient);
    const tRgb = hexToRgb(config.drag.trailColor);
    const R = config.render;
    const B = config.background;
    this._styles = {
      bg: config.palette.background,
      glow: `rgba(${cRgb.r},${cRgb.g},${cRgb.b},${R.glowAlpha})`,
      core: `rgba(${cRgb.r},${cRgb.g},${cRgb.b},${R.coreAlpha})`,
      clockAmbient: `rgba(${aRgb.r},${aRgb.g},${aRgb.b},${R.ambientAlpha})`,
      bgDot: `rgba(${aRgb.r},${aRgb.g},${aRgb.b},${B.alpha})`,
      bgGlow: `rgba(${aRgb.r},${aRgb.g},${aRgb.b},${B.glowAlpha})`,
      linkR: aRgb.r, linkG: aRgb.g, linkB: aRgb.b,
      trailR: tRgb.r, trailG: tRgb.g, trailB: tRgb.b
    };

    this._sampler = document.createElement("canvas");
    this._samplerCtx = this._sampler.getContext("2d", { willReadFrequently: true });

    for (const fn of [
      "_resize", "_vis", "_key",
      "_click", "_dblclick", "_ctxmenu",
      "_ptrDown", "_ptrMove", "_ptrUp",
      "_frame"
    ]) this[fn] = this[fn].bind(this);
  }

  start() {
    if (!this.ctx) return;
    document.documentElement.style.setProperty("--bg", this._styles.bg);
    this._resize();
    this._initBg();
    this._tick(true);
    addEventListener("resize", this._resize, { passive: true });
    document.addEventListener("visibilitychange", this._vis);
    addEventListener("keydown", this._key);
    this.canvas.addEventListener("click", this._click);
    this.canvas.addEventListener("dblclick", this._dblclick);
    this.canvas.addEventListener("contextmenu", this._ctxmenu);
    this.canvas.addEventListener("pointerdown", this._ptrDown);
    this.canvas.addEventListener("pointermove", this._ptrMove);
    this.canvas.addEventListener("pointerup", this._ptrUp);
    this.canvas.addEventListener("pointercancel", this._ptrUp);
    this.canvas.addEventListener("pointerleave", this._ptrUp);
    requestAnimationFrame(this._frame);
  }

  stop() {
    removeEventListener("resize", this._resize);
    document.removeEventListener("visibilitychange", this._vis);
    removeEventListener("keydown", this._key);
    this.canvas.removeEventListener("click", this._click);
    this.canvas.removeEventListener("dblclick", this._dblclick);
    this.canvas.removeEventListener("contextmenu", this._ctxmenu);
    this.canvas.removeEventListener("pointerdown", this._ptrDown);
    this.canvas.removeEventListener("pointermove", this._ptrMove);
    this.canvas.removeEventListener("pointerup", this._ptrUp);
    this.canvas.removeEventListener("pointercancel", this._ptrUp);
    this.canvas.removeEventListener("pointerleave", this._ptrUp);
    if (this.clickTimer != null) clearTimeout(this.clickTimer);
  }

  /* ---- pointer / drag ---- */

  _ptrDown(e) {
    if (!this.cfg.interaction.enabled || this._ptrId != null) return;
    e.preventDefault();
    this._ptrId = e.pointerId;
    this._ptrStart = { x: e.clientX, y: e.clientY };
    this._isDrag = false;
    try { this.canvas.setPointerCapture(e.pointerId); } catch {}
  }

  _ptrMove(e) {
    if (this._ptrId == null || e.pointerId !== this._ptrId) return;
    const sx = this._ptrStart.x, sy = this._ptrStart.y;
    if (!this._isDrag) {
      if ((e.clientX - sx) ** 2 + (e.clientY - sy) ** 2 < 100) return;
      this._isDrag = true;
      this._suppressClick = true;
    }
    const x = e.clientX, y = e.clientY;
    this.dragTrail.push({ x, y, t: performance.now() });
    this._applyDragForce(x, y);
  }

  _ptrUp(e) {
    if (this._ptrId == null) return;
    try { this.canvas.releasePointerCapture(e.pointerId); } catch {}
    this._ptrId = null;
    if (this._isDrag) {
      this._isDrag = false;
      setTimeout(() => { this._suppressClick = false; }, 100);
    }
  }

  _applyDragForce(x, y) {
    const D = this.cfg.drag;
    const R = D.radius, R2 = R * R, force = D.force;

    for (const p of this.bgParticles) {
      const dx = p.x - x, dy = p.y - y;
      const d2 = dx * dx + dy * dy;
      if (d2 > R2) continue;
      const d = Math.sqrt(d2) || 0.001;
      const s = force * (1 - d / R) * rand(0.8, 1.2);
      p.vx += (dx / d) * s;
      p.vy += (dy / d) * s;
    }

    const cf = force * D.clockForceRatio;
    for (const p of this.particles) {
      const dx = p.x - x, dy = p.y - y;
      const d2 = dx * dx + dy * dy;
      if (d2 > R2) continue;
      const d = Math.sqrt(d2) || 0.001;
      const s = cf * (1 - d / R);
      p.vx += (dx / d) * s;
      p.vy += (dy / d) * s;
    }
  }

  /* ---- click / tap ---- */

  _click(e) {
    if (!this.cfg.interaction.enabled || this._suppressClick) return;
    e.preventDefault();
    this.pendingClick = { x: e.clientX, y: e.clientY };
    if (this.clickTimer != null) clearTimeout(this.clickTimer);
    this.clickTimer = setTimeout(() => {
      if (!this.pendingClick) return;
      this._burst(this.pendingClick.x, this.pendingClick.y, 1);
      this.pendingClick = null;
      this.clickTimer = null;
    }, clamp(this.cfg.interaction.dblClickWindow, 100, 400));
  }

  _dblclick(e) {
    if (!this.cfg.interaction.enabled || this._suppressClick) return;
    e.preventDefault();
    if (this.clickTimer != null) {
      clearTimeout(this.clickTimer);
      this.clickTimer = null;
    }
    this.pendingClick = null;
    this._burst(e.clientX, e.clientY, -1);
  }

  _ctxmenu(e) {
    if (!this.cfg.interaction.enabled) return;
    e.preventDefault();
    this._burst(e.clientX, e.clientY, -1);
  }

  _burst(x, y, dir) {
    const ia = this.cfg.interaction;
    const R = ia.radius * 1.1, R2 = R * R;
    for (const p of this.particles) {
      const dx = p.x - x, dy = p.y - y;
      const d2 = dx * dx + dy * dy;
      if (d2 > R2) continue;
      const d = Math.sqrt(d2) || 0.001;
      p.vx += (dx / d) * ia.burstForce * (1 - d / R) * rand(0.7, 1.3);
      p.vy += (dy / d) * ia.burstForce * (1 - d / R) * rand(0.7, 1.3);
    }
    for (const p of this.bgParticles) {
      const dx = p.x - x, dy = p.y - y;
      const d2 = dx * dx + dy * dy;
      if (d2 > R2) continue;
      const d = Math.sqrt(d2) || 0.001;
      p.vx += (dx / d) * ia.burstForce * 0.8 * (1 - d / R) * rand(0.7, 1.3);
      p.vy += (dy / d) * ia.burstForce * 0.8 * (1 - d / R) * rand(0.7, 1.3);
    }
    this.effects.push({ x, y, dir, t: performance.now() });
    if (this.effects.length > 8) this.effects.shift();
  }

  /* ---- events ---- */

  _resize() {
    this.dpr = Math.min(devicePixelRatio || 1, this.cfg.render.dprCap);
    this.w = innerWidth;
    this.h = innerHeight;
    this.canvas.width = Math.floor(this.w * this.dpr);
    this.canvas.height = Math.floor(this.h * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._initBg();
    this._tick(true);
  }

  _vis() {
    this.visible = document.visibilityState === "visible";
    if (this.visible) this._tick(true);
  }

  _key(e) {
    if (e.key.toLowerCase() !== "f") return;
    (document.fullscreenElement
      ? document.exitFullscreen()
      : document.documentElement.requestFullscreen()
    ).catch(() => {});
  }

  /* ---- background particles ---- */

  _initBg() {
    const B = this.cfg.background;
    const n = clamp(B.count, 0, 600);
    while (this.bgParticles.length < n) {
      this.bgParticles.push({
        x: rand(0, this.w), y: rand(0, this.h),
        vx: 0, vy: 0,
        phase: rand(0, TAU),
        size: rand(B.sizeMin, B.sizeMax)
      });
    }
    if (this.bgParticles.length > n) this.bgParticles.length = n;
    for (const p of this.bgParticles) {
      p.x = clamp(p.x, 0, this.w);
      p.y = clamp(p.y, 0, this.h);
    }
  }

  _bgPhysics(ts) {
    const B = this.cfg.background;
    const spd = B.speed;
    for (const p of this.bgParticles) {
      p.vx += Math.cos(p.phase + ts * 0.00025) * spd * 0.015;
      p.vy += Math.sin(p.phase + ts * 0.0003) * spd * 0.015;
      p.x += p.vx;
      p.y += p.vy;
      const s2 = p.vx * p.vx + p.vy * p.vy;
      p.vx *= s2 > 1 ? 0.88 : 0.99;
      p.vy *= s2 > 1 ? 0.88 : 0.99;
      if (p.x < -10) p.x += this.w + 20;
      else if (p.x > this.w + 10) p.x -= this.w + 20;
      if (p.y < -10) p.y += this.h + 20;
      else if (p.y > this.h + 10) p.y -= this.h + 20;
    }
  }

  /* ---- time & text sampling ---- */

  _tick(force) {
    const now = new Date();
    const key = `${now.getHours()}:${now.getMinutes()}`;
    if (!force && key === this.timeKey) return;
    this.timeKey = key;
    let h = now.getHours();
    if (!this.cfg.time.use24Hour) h = h % 12 || 12;
    const text = `${String(h).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    this.targets = this._sample(text);
    this._assign();
  }

  _sample(text) {
    const L = this.cfg.layout;
    const scale = 0.5;
    const aW = Math.ceil(this.w * L.textWidthRatio * scale);
    const aH = Math.ceil(this.h * L.textHeightRatio * scale);
    if (aW < 10 || aH < 10) return [];
    const sc = this._sampler;
    const sx = this._samplerCtx;
    sc.width = aW;
    sc.height = aH;
    sx.clearRect(0, 0, aW, aH);
    let fs = Math.floor(aH * 0.92);
    const { fontWeight, fontFamily } = L;
    sx.font = `${fontWeight} ${fs}px ${fontFamily}`;
    sx.textAlign = "center";
    sx.textBaseline = "middle";
    while (sx.measureText(text).width > aW * 0.95 && fs > 16) {
      fs -= 2;
      sx.font = `${fontWeight} ${fs}px ${fontFamily}`;
    }
    sx.fillStyle = "#fff";
    sx.fillText(text, aW / 2, aH / 2);
    const { data, width: iW, height: iH } = sx.getImageData(0, 0, aW, aH);
    let lit = 0;
    for (let i = 3; i < data.length; i += 4) if (data[i] > 80) lit++;
    if (lit === 0) return [];
    const desired = Math.floor(this.cfg.motion.particleCount * (1 - this.cfg.motion.ambientRatio));
    const step = Math.max(2, Math.round(Math.sqrt(lit / desired)));
    const half = step / 2;
    const oX = (this.w - aW / scale) / 2;
    const oY = (this.h - aH / scale) / 2;
    const pts = [];
    for (let y = half; y < iH; y += step) {
      for (let x = half; x < iW; x += step) {
        if (data[(Math.floor(y) * iW + Math.floor(x)) * 4 + 3] > 80) {
          pts.push({ x: oX + x / scale, y: oY + y / scale });
        }
      }
    }
    return pts;
  }

  /* ---- clock particles ---- */

  _createParticle() {
    return {
      x: rand(0, this.w), y: rand(0, this.h),
      vx: 0, vy: 0, tx: null, ty: null,
      phase: rand(0, TAU),
      size: rand(this.cfg.render.sizeMin, this.cfg.render.sizeMax)
    };
  }

  _assign() {
    const total = clamp(this.cfg.motion.particleCount, 50, 3000);
    while (this.particles.length < total) this.particles.push(this._createParticle());
    if (this.particles.length > total) this.particles.length = total;
    const tLen = this.targets.length;
    const coreN = Math.min(tLen, Math.floor(total * (1 - this.cfg.motion.ambientRatio)));
    const tIdx = shuffle(Array.from({ length: tLen }, (_, i) => i));
    const pIdx = shuffle(Array.from({ length: total }, (_, i) => i));
    const sf = this.cfg.motion.scatterForce;
    for (let k = 0; k < total; k++) {
      const p = this.particles[pIdx[k]];
      if (k < coreN) {
        const t = this.targets[tIdx[k]];
        p.tx = t.x; p.ty = t.y;
        p.vx += rand(-sf, sf); p.vy += rand(-sf, sf);
      } else {
        p.tx = null; p.ty = null;
      }
    }
  }

  /* ---- clock physics ---- */

  _clockPhysics(ts) {
    const M = this.cfg.motion;
    const ia = this.cfg.interaction;
    for (const p of this.particles) {
      for (const e of this.effects) {
        const dx = e.x - p.x, dy = e.y - p.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > ia.radius * ia.radius) continue;
        const d = Math.sqrt(d2) || 0.001;
        const life = clamp(1 - (ts - e.t) / ia.pulseDuration, 0, 1);
        const f = ia.pulseForce * life * (1 - d / ia.radius) * e.dir * 0.016;
        p.vx += (dx / d) * f;
        p.vy += (dy / d) * f;
      }
      if (p.tx != null) {
        const jx = Math.cos(ts * 0.001 + p.phase) * M.jitter;
        const jy = Math.sin(ts * 0.0012 + p.phase) * M.jitter;
        p.x += ((p.tx + jx) - p.x) * M.approach;
        p.y += ((p.ty + jy) - p.y) * M.approach;
        p.x += p.vx; p.y += p.vy;
        p.vx *= M.scatterDecay; p.vy *= M.scatterDecay;
      } else {
        p.vx += Math.cos(p.phase + ts * 0.0003) * M.wanderSpeed * 0.02;
        p.vy += Math.sin(p.phase + ts * 0.00035) * M.wanderSpeed * 0.02;
        p.x += p.vx; p.y += p.vy;
        const s2 = p.vx * p.vx + p.vy * p.vy;
        p.vx *= s2 > 1 ? M.scatterDecay : 0.98;
        p.vy *= s2 > 1 ? M.scatterDecay : 0.98;
        if (p.x < -10) p.x += this.w + 20;
        else if (p.x > this.w + 10) p.x -= this.w + 20;
        if (p.y < -10) p.y += this.h + 20;
        else if (p.y > this.h + 10) p.y -= this.h + 20;
      }
    }
    this.effects = this.effects.filter(e => ts - e.t < ia.pulseDuration);
  }

  /* ---- render ---- */

  _renderBg() {
    const ctx = this.ctx;
    const B = this.cfg.background;
    const S = this._styles;
    const bg = this.bgParticles;
    const linkD = B.linkDist;
    const linkD2 = linkD * linkD;

    ctx.lineWidth = B.linkWidth;
    for (let i = 0; i < bg.length; i++) {
      const a = bg[i];
      for (let j = i + 1; j < bg.length; j++) {
        const b = bg[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > linkD2) continue;
        const alpha = B.linkAlpha * (1 - Math.sqrt(d2) / linkD);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = `rgba(${S.linkR},${S.linkG},${S.linkB},${alpha})`;
        ctx.stroke();
      }
    }

    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = S.bgGlow;
    for (const p of bg) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * B.glowScale, 0, TAU);
      ctx.fill();
    }
    ctx.fillStyle = S.bgDot;
    for (const p of bg) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, TAU);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
  }

  _renderTrail(ts) {
    const D = this.cfg.drag;
    const fadeMs = D.trailFadeMs;
    const S = this._styles;
    const trail = this.dragTrail;

    let first = 0;
    while (first < trail.length && ts - trail[first].t > fadeMs) first++;
    if (first > 0) this.dragTrail = this.dragTrail.slice(first);
    if (this.dragTrail.length < 2) return;

    const ctx = this.ctx;
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (let pass = 0; pass < 2; pass++) {
      const isGlow = pass === 0;
      ctx.lineWidth = isGlow ? D.trailGlow : D.trailWidth;
      const baseAlpha = isGlow ? 0.12 : 0.45;

      for (let i = 1; i < this.dragTrail.length; i++) {
        const p0 = this.dragTrail[i - 1], p1 = this.dragTrail[i];
        const age = Math.max(ts - p0.t, ts - p1.t);
        const life = clamp(1 - age / fadeMs, 0, 1);
        if (life <= 0) continue;
        const a = (life * life * baseAlpha).toFixed(3);
        ctx.beginPath();
        ctx.moveTo(p0.x, p0.y);
        ctx.lineTo(p1.x, p1.y);
        ctx.strokeStyle = `rgba(${S.trailR},${S.trailG},${S.trailB},${a})`;
        ctx.stroke();
      }
    }
    ctx.globalCompositeOperation = "source-over";
  }

  _renderClock() {
    const ctx = this.ctx;
    const R = this.cfg.render;
    const S = this._styles;

    ctx.fillStyle = S.clockAmbient;
    for (const p of this.particles) {
      if (p.tx != null) continue;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * R.ambientScale, 0, TAU);
      ctx.fill();
    }

    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = S.glow;
    for (const p of this.particles) {
      if (p.tx == null) continue;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * R.glowScale, 0, TAU);
      ctx.fill();
    }
    ctx.fillStyle = S.core;
    for (const p of this.particles) {
      if (p.tx == null) continue;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * R.coreScale, 0, TAU);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
  }

  /* ---- loop ---- */

  _frame(ts) {
    requestAnimationFrame(this._frame);
    if (!this.visible || !this.ctx) return;
    if (ts - this.prevTs < this.frameMs) return;
    this.prevTs = ts;

    this._tick(false);
    this._bgPhysics(ts);
    this._clockPhysics(ts);

    const ctx = this.ctx;
    ctx.fillStyle = this._styles.bg;
    ctx.fillRect(0, 0, this.w, this.h);

    this._renderBg();
    this._renderTrail(ts);
    this._renderClock();
  }
}

async function main() {
  const cfg = await loadConfig();
  const canvas = document.getElementById("clock-canvas");
  if (!canvas) return;
  const clock = new ParticleClock(canvas, cfg);
  clock.start();
  addEventListener("beforeunload", () => clock.stop(), { once: true });
}

main();
