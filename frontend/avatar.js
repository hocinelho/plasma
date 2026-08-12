/* ═══════════════════════════════════════════════════════════════════════
   Plasma avatar — renderer
   ─────────────────────────────────────────────────────────────────────
   This file owns the on-screen avatar and exposes a small, stable contract
   that the rest of the UI drives:

       window.avatarState    'idle' | 'listening' | 'thinking' | 'speaking'
                             — set by setStatus(); the avatar mirrors it.
       window.avatarLevel    0..1 live audio amplitude — written by the
                             TTS lip-sync analyser; drives the pulse/mouth.
       window.avatarWakeBurst(ms=1700)
                             — a brief "waking up" reaction on the wake word.

   Two renderers ship here:
     • "mascot" (default) — Plasma, a plasma-jelly creature companion with a
       face, eyes and moods. See docs/avatar-design.md.
     • "orb"             — the original JARVIS neural-galaxy sphere.
   Pick with  <canvas id="avatar" data-avatar="orb">  (defaults to mascot).

   Served at /avatar.js.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
    const TAU = Math.PI * 2;
    const avatarCanvas = document.getElementById('avatar');
    if (!avatarCanvas) return;

    // Shared contract — established here so index.html can read/write these
    // by bare name (avatar.js is loaded before the main inline script).
    if (typeof window.avatarState !== 'string') window.avatarState = 'idle';
    if (typeof window.avatarLevel !== 'number') window.avatarLevel = 0;

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Wake burst is shared by both renderers. avatarWakeUntil is a timestamp;
    // isWaking(now) is true for the brief excited reaction after the wake word.
    let avatarWakeUntil = 0;
    window.avatarWakeBurst = (ms = 1700) => { avatarWakeUntil = performance.now() + ms; };
    const isWaking = (now) => now < avatarWakeUntil;

    const lerp = (a, b, t) => a + (b - a) * t;
    const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

    // ══════════════════════════════════════════════════════════════════════
    //  MASCOT — "Plasma", a plasma-jelly creature companion
    //  A soft, glowing gel body that breathes and bobs, two big expressive
    //  eyes that blink / glance / widen, a mouth that lip-syncs the voice, a
    //  springy energy antenna, and a few motes of plasma orbiting it. Every
    //  state has its own colour + mood; the wake word makes it perk up.
    // ══════════════════════════════════════════════════════════════════════
    function startMascot() {
        const cv = avatarCanvas, ctx = cv.getContext('2d');
        const DPR = Math.min(window.devicePixelRatio || 1, 2);
        const CSS = 190;
        cv.width = CSS * DPR; cv.height = CSS * DPR;
        ctx.scale(DPR, DPR);
        const cx = CSS / 2, cyBase = CSS * 0.56, R = CSS * 0.28;
        const MOTION = reduce ? 0.35 : 1;   // damp everything for reduced-motion

        // Per-state personality. gaze is a resting eye direction (x,y in eye
        // radii); wander scales how much the eyes roam; mouth picks a shape.
        const STATES = {
            idle:      { hue: 205, sat: 78, bob: 3.0, breath: 1.05, gaze: [0,  0.06], wander: 1.0, eye: 1.00, mouth: 'smile',   antenna: 0.5, blush: 0.10 },
            listening: { hue: 330, sat: 80, bob: 2.2, breath: 1.70, gaze: [0,  0.20], wander: 0.4, eye: 1.28, mouth: 'soft',    antenna: 1.0, blush: 0.28 },
            thinking:  { hue: 162, sat: 66, bob: 1.6, breath: 1.25, gaze: [0.12,-0.30], wander: 2.4, eye: 0.90, mouth: 'neutral', antenna: 0.7, blush: 0.05 },
            speaking:  { hue: 190, sat: 84, bob: 4.2, breath: 1.55, gaze: [0,  0.02], wander: 0.3, eye: 0.96, mouth: 'talk',    antenna: 0.95, blush: 0.22 },
            waking:    { hue: 46,  sat: 95, bob: 6.0, breath: 2.40, gaze: [0, -0.04], wander: 0.0, eye: 1.45, mouth: 'open',    antenna: 1.5, blush: 0.35 },
        };

        // Smoothed live values.
        const cur = { hue: 205, sat: 78, gx: 0, gy: 0.06, eye: 1, antenna: 0.5, blush: 0.1, pop: 0 };
        let antAng = 0, antVel = 0;                 // springy antenna angle
        let blinkT = 0, nextBlink = 0.8 + Math.random() * 3;
        let gzTX = 0, gzTY = 0.06, nextSaccade = 1; // gaze saccade target
        let t = 0, last = performance.now(), bodyY = cyBase, bodyVel = 0;

        const M = reduce ? 3 : 6;
        const motes = [];
        for (let i = 0; i < M; i++)
            motes.push({ a: Math.random() * TAU, r: R * (1.45 + Math.random() * 0.6),
                sp: (0.18 + Math.random() * 0.30) * (Math.random() < 0.5 ? -1 : 1),
                sz: 1.1 + Math.random() * 1.8, bob: Math.random() * TAU });

        // Jelly body outline — a wobbling rounded blob, bottom-heavy for charm.
        function bodyPath(bx, by, rx, ry, wob) {
            const steps = 44;
            ctx.beginPath();
            for (let i = 0; i <= steps; i++) {
                const th = i / steps * TAU;
                const w = 1 + Math.sin(th * 3 + t * 1.4) * 0.028 * wob
                            + Math.sin(th * 2 - t * 0.9) * 0.022 * wob;
                const heavy = 1 + Math.sin(th) * 0.06;   // fatter at the bottom
                const x = bx + Math.cos(th) * rx * w;
                const y = by + Math.sin(th) * ry * w * heavy;
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.closePath();
        }

        function drawEye(ex, ey, ew, eh, gx, gy, open, hue, sat) {
            // Closed → a friendly curved lid.
            if (open < 0.12) {
                ctx.strokeStyle = `hsl(${hue},${sat}%,22%)`;
                ctx.lineWidth = 2.4; ctx.lineCap = 'round';
                ctx.beginPath();
                ctx.moveTo(ex - ew * 0.8, ey);
                ctx.quadraticCurveTo(ex, ey + eh * 0.5, ex + ew * 0.8, ey);
                ctx.stroke();
                return;
            }
            const h = eh * open;
            // Sclera — soft luminous white.
            ctx.fillStyle = 'rgba(248,251,255,0.96)';
            ctx.beginPath(); ctx.ellipse(ex, ey, ew, h, 0, 0, TAU); ctx.fill();
            // Iris — glowing state hue.
            const ix = ex + gx * ew * 0.45, iy = ey + gy * h * 0.5;
            const ir = ew * 0.62;
            const ig = ctx.createRadialGradient(ix - ir * 0.3, iy - ir * 0.3, ir * 0.1, ix, iy, ir);
            ig.addColorStop(0, `hsl(${hue},${sat}%,68%)`);
            ig.addColorStop(1, `hsl(${hue + 15},${sat}%,38%)`);
            ctx.save();
            ctx.beginPath(); ctx.ellipse(ex, ey, ew, h, 0, 0, TAU); ctx.clip();
            ctx.fillStyle = ig;
            ctx.beginPath(); ctx.ellipse(ix, iy, ir, ir * clamp(open, 0.4, 1), 0, 0, TAU); ctx.fill();
            // Pupil.
            ctx.fillStyle = 'rgba(12,18,30,0.92)';
            ctx.beginPath(); ctx.ellipse(ix, iy, ir * 0.5, ir * 0.5 * clamp(open, 0.4, 1), 0, 0, TAU); ctx.fill();
            ctx.restore();
            // Catchlights — the spark of life.
            ctx.fillStyle = 'rgba(255,255,255,0.95)';
            ctx.beginPath(); ctx.arc(ix - ir * 0.32, iy - ir * 0.38, ir * 0.26, 0, TAU); ctx.fill();
            ctx.fillStyle = 'rgba(255,255,255,0.6)';
            ctx.beginPath(); ctx.arc(ix + ir * 0.28, iy + ir * 0.22, ir * 0.13, 0, TAU); ctx.fill();
        }

        function drawMouth(mx, my, shape, lvl, hue) {
            ctx.strokeStyle = `hsl(${hue},70%,26%)`;
            ctx.fillStyle = `hsl(${hue},60%,20%)`;
            ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
            const w = R * 0.34;
            if (shape === 'talk' || shape === 'open') {
                const base = shape === 'open' ? 0.5 : 0.12;
                const oh = (base + lvl * 0.9) * R * 0.42;
                ctx.beginPath();
                ctx.ellipse(mx, my + oh * 0.25, w * 0.62, oh, 0, 0, TAU);
                ctx.fill();
                // little tongue glow
                ctx.fillStyle = `hsl(${hue},75%,60%)`;
                ctx.globalAlpha = 0.5;
                ctx.beginPath(); ctx.ellipse(mx, my + oh * 0.55, w * 0.4, oh * 0.4, 0, 0, TAU); ctx.fill();
                ctx.globalAlpha = 1;
            } else if (shape === 'neutral') {
                ctx.beginPath(); ctx.moveTo(mx - w * 0.5, my); ctx.lineTo(mx + w * 0.5, my); ctx.stroke();
            } else { // 'smile' | 'soft'
                const curve = shape === 'smile' ? w * 0.55 : w * 0.32;
                ctx.beginPath();
                ctx.moveTo(mx - w * 0.6, my);
                ctx.quadraticCurveTo(mx, my + curve, mx + w * 0.6, my);
                ctx.stroke();
            }
        }

        function frame(now) {
            const dt = Math.min(0.05, (now - last) / 1000); last = now; t += dt;
            window.avatarLevel *= 0.9;
            const lvl = clamp(window.avatarLevel, 0, 1);
            const waking = isWaking(now);
            const st = waking ? STATES.waking : (STATES[window.avatarState] || STATES.idle);
            const k = waking ? 0.20 : 0.08;

            cur.hue    = lerp(cur.hue, st.hue, k);
            cur.sat    = lerp(cur.sat, st.sat, k);
            cur.eye    = lerp(cur.eye, st.eye, 0.12);
            cur.antenna= lerp(cur.antenna, st.antenna, 0.10);
            cur.blush  = lerp(cur.blush, st.blush + lvl * 0.25, 0.10);
            cur.pop    = lerp(cur.pop, waking ? 1 : 0, 0.15);

            // Gaze: state rest direction + occasional saccades (livelier when thinking).
            nextSaccade -= dt;
            if (nextSaccade <= 0) {
                gzTX = st.gaze[0] + (Math.random() * 2 - 1) * 0.12 * st.wander;
                gzTY = st.gaze[1] + (Math.random() * 2 - 1) * 0.10 * st.wander;
                nextSaccade = 0.5 + Math.random() * (st.wander > 1 ? 1.1 : 2.6);
            }
            cur.gx = lerp(cur.gx, gzTX, 0.14);
            cur.gy = lerp(cur.gy, gzTY, 0.14);

            // Blink: a quick close-open every few seconds.
            nextBlink -= dt;
            if (blinkT > 0) { blinkT = Math.max(0, blinkT - dt * 7); }
            else if (nextBlink <= 0) { blinkT = 1; nextBlink = 1.6 + Math.random() * 4; }
            const closed = blinkT > 0 ? Math.sin(blinkT * Math.PI) : 0;
            const eyeOpen = clamp((1 - closed) * cur.eye, 0, 1.5);

            // Body motion — breathe, bob, rise a little when excited / speaking.
            const breathe = Math.sin(t * st.breath * 1.6);
            const bob = Math.sin(t * st.breath * 1.2) * st.bob * MOTION;
            const targetY = cyBase + bob - cur.pop * 8 * MOTION - lvl * 6 * MOTION;
            bodyVel = (targetY - bodyY) / Math.max(dt, 0.001);
            bodyY = targetY;
            const by = bodyY;
            const sq = breathe * 0.04 * MOTION + lvl * 0.05 + cur.pop * 0.05;
            const scale = 1 + cur.pop * 0.10 + lvl * 0.04;
            const rx = R * (1 + sq) * scale, ry = R * (1 - sq) * scale;
            const hue = cur.hue, sat = cur.sat;

            // Antenna spring — flicks with body velocity + voice + a gentle idle sway.
            const drive = Math.sin(t * 2.4) * 0.10 * cur.antenna
                        + clamp(-bodyVel * 0.004, -0.25, 0.25) * MOTION
                        + lvl * Math.sin(t * 17) * 0.14
                        + (waking ? Math.sin(t * 22) * 0.18 : 0);
            antVel += (drive - antAng) * 32 * dt - antVel * 8 * dt;
            antAng += antVel * dt;

            ctx.clearRect(0, 0, CSS, CSS);

            // Aura behind the creature.
            ctx.globalCompositeOperation = 'lighter';
            const ag = ctx.createRadialGradient(cx, by, 0, cx, by, R * 2.2);
            ag.addColorStop(0, `hsla(${hue},${sat}%,60%,${0.18 + lvl * 0.22 + cur.pop * 0.2})`);
            ag.addColorStop(1, `hsla(${hue},${sat}%,55%,0)`);
            ctx.fillStyle = ag; ctx.beginPath(); ctx.arc(cx, by, R * 2.2, 0, TAU); ctx.fill();

            // Motes drifting behind (the ones on the far side).
            for (const m of motes) {
                m.a += m.sp * dt * (1 + lvl);
                const mx = cx + Math.cos(m.a) * m.r;
                const my = by + Math.sin(m.a) * m.r * 0.6 + Math.sin(t + m.bob) * 3;
                if (Math.sin(m.a) >= 0) continue;  // behind → draw before body
                const g = ctx.createRadialGradient(mx, my, 0, mx, my, m.sz * 3);
                g.addColorStop(0, `hsla(${hue + 20},90%,72%,0.7)`);
                g.addColorStop(1, `hsla(${hue + 20},90%,60%,0)`);
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(mx, my, m.sz * 3, 0, TAU); ctx.fill();
            }
            ctx.globalCompositeOperation = 'source-over';

            // ── Body ──────────────────────────────────────────────────────
            bodyPath(cx, by, rx, ry, 1 + lvl * 1.5);
            const bg = ctx.createRadialGradient(cx - rx * 0.3, by - ry * 0.45, rx * 0.15, cx, by, rx * 1.15);
            bg.addColorStop(0, `hsl(${hue},${sat}%,${72 + lvl * 8}%)`);
            bg.addColorStop(0.55, `hsl(${hue},${sat}%,58%)`);
            bg.addColorStop(1, `hsl(${hue + 12},${sat}%,44%)`);
            ctx.save();
            ctx.shadowColor = `hsla(${hue},${sat}%,60%,${0.5 + lvl * 0.4})`;
            ctx.shadowBlur = 22 + lvl * 26;
            ctx.fillStyle = bg; ctx.fill();
            ctx.restore();
            // Rim light along the top edge.
            bodyPath(cx, by, rx, ry, 1 + lvl * 1.5);
            ctx.save(); ctx.clip();
            const rim = ctx.createLinearGradient(cx, by - ry, cx, by - ry * 0.2);
            rim.addColorStop(0, 'rgba(255,255,255,0.55)');
            rim.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = rim; ctx.fillRect(cx - rx, by - ry, rx * 2, ry);
            // Inner core glow.
            const core = ctx.createRadialGradient(cx, by + ry * 0.15, 0, cx, by + ry * 0.15, rx * 0.7);
            core.addColorStop(0, `hsla(${hue},100%,85%,${0.28 + lvl * 0.4})`);
            core.addColorStop(1, `hsla(${hue},100%,80%,0)`);
            ctx.globalCompositeOperation = 'lighter';
            ctx.fillStyle = core; ctx.fillRect(cx - rx, by - ry, rx * 2, ry * 2.2);
            ctx.restore();

            // ── Face ──────────────────────────────────────────────────────
            const eyeY = by - ry * 0.12;
            const eyeDX = rx * 0.42, ew = rx * 0.24, eh = ry * 0.34;
            // Cheek blush.
            if (cur.blush > 0.02) {
                ctx.fillStyle = `hsla(${(hue + 320) % 360},90%,68%,${cur.blush * 0.5})`;
                for (const s of [-1, 1]) {
                    ctx.beginPath();
                    ctx.ellipse(cx + s * eyeDX * 1.15, eyeY + eh * 0.9, ew * 0.7, eh * 0.4, 0, 0, TAU);
                    ctx.fill();
                }
            }
            drawEye(cx - eyeDX, eyeY, ew, eh, cur.gx, cur.gy, eyeOpen, hue, sat);
            drawEye(cx + eyeDX, eyeY, ew, eh, cur.gx, cur.gy, eyeOpen, hue, sat);
            drawMouth(cx + cur.gx * ew * 0.3, by + ry * 0.42, st.mouth, lvl, hue);

            // ── Antenna ───────────────────────────────────────────────────
            const rootX = cx + rx * 0.02, rootY = by - ry * 0.98;
            const tipX = rootX + Math.sin(antAng) * rx * 0.5;
            const tipY = rootY - ry * 0.55 - Math.cos(antAng) * ry * 0.2;
            const midX = (rootX + tipX) / 2 - Math.sin(antAng) * 4;
            const midY = (rootY + tipY) / 2;
            ctx.strokeStyle = `hsl(${hue},${sat}%,60%)`;
            ctx.lineWidth = 2.4; ctx.lineCap = 'round';
            ctx.beginPath(); ctx.moveTo(rootX, rootY);
            ctx.quadraticCurveTo(midX, midY, tipX, tipY); ctx.stroke();
            ctx.globalCompositeOperation = 'lighter';
            const tg = ctx.createRadialGradient(tipX, tipY, 0, tipX, tipY, 9 + lvl * 8 + cur.pop * 6);
            tg.addColorStop(0, `hsla(${hue},100%,85%,${0.9})`);
            tg.addColorStop(1, `hsla(${hue},100%,70%,0)`);
            ctx.fillStyle = tg; ctx.beginPath(); ctx.arc(tipX, tipY, 9 + lvl * 8 + cur.pop * 6, 0, TAU); ctx.fill();
            ctx.fillStyle = 'rgba(255,255,255,0.95)';
            ctx.beginPath(); ctx.arc(tipX, tipY, 2.4 + cur.pop * 1.5, 0, TAU); ctx.fill();
            ctx.globalCompositeOperation = 'source-over';

            // ── Thought dots while thinking ───────────────────────────────
            if (window.avatarState === 'thinking' && !waking) {
                ctx.globalCompositeOperation = 'lighter';
                for (let i = 0; i < 3; i++) {
                    const ph = t * 2 - i * 0.5;
                    const a = (Math.sin(ph) + 1) / 2;
                    const dx = cx + rx * 0.7 + i * 9;
                    const dy = by - ry * 1.15 - i * 6 + Math.sin(t * 3 - i) * 2;
                    ctx.fillStyle = `hsla(${hue},90%,72%,${0.25 + a * 0.6})`;
                    ctx.beginPath(); ctx.arc(dx, dy, 2 + a * 1.5, 0, TAU); ctx.fill();
                }
                ctx.globalCompositeOperation = 'source-over';
            }

            // Motes drifting in front.
            ctx.globalCompositeOperation = 'lighter';
            for (const m of motes) {
                if (Math.sin(m.a) < 0) continue;
                const mx = cx + Math.cos(m.a) * m.r;
                const my = by + Math.sin(m.a) * m.r * 0.6 + Math.sin(t + m.bob) * 3;
                const g = ctx.createRadialGradient(mx, my, 0, mx, my, m.sz * 3.2);
                g.addColorStop(0, `hsla(${hue + 20},95%,80%,0.85)`);
                g.addColorStop(1, `hsla(${hue + 20},95%,65%,0)`);
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(mx, my, m.sz * 3.2, 0, TAU); ctx.fill();
            }

            // Wake sparkles — a quick burst of excitement.
            if (cur.pop > 0.05) {
                const n = reduce ? 5 : 9;
                for (let i = 0; i < n; i++) {
                    const a = i / n * TAU + t * 2;
                    const rr = R * (1.2 + (1 - cur.pop) * 1.4);
                    const sx = cx + Math.cos(a) * rr, sy = by + Math.sin(a) * rr;
                    ctx.fillStyle = `hsla(${hue + i * 12},100%,80%,${cur.pop * 0.9})`;
                    ctx.beginPath(); ctx.arc(sx, sy, 1.6 + cur.pop * 2, 0, TAU); ctx.fill();
                }
            }
            ctx.globalCompositeOperation = 'source-over';

            cv.style.filter = `drop-shadow(0 0 ${12 + lvl * 26 + cur.pop * 20}px hsla(${hue},${sat}%,60%,${0.3 + lvl * 0.4}))`;
            requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    // ══════════════════════════════════════════════════════════════════════
    //  ORB — the original JARVIS neural-galaxy sphere (opt-in via data-avatar)
    // ══════════════════════════════════════════════════════════════════════
    function startOrb() {
        const cv = avatarCanvas, ctx = cv.getContext('2d');
        const DPR = Math.min(window.devicePixelRatio || 1, 2);
        const CSS = 190;
        cv.width = CSS * DPR; cv.height = CSS * DPR;
        ctx.scale(DPR, DPR);
        const cx = CSS / 2, cy = CSS / 2, R = CSS * 0.30, FOCAL = 260;

        const PALETTE = {
            idle:      { h: 205, spread: 90,  speed: 0.30, glow: '120,180,255' },
            listening: { h: 330, spread: 70,  speed: 0.85, glow: '255,90,150'  },
            thinking:  { h: 160, spread: 80,  speed: 0.55, glow: '80,230,180'  },
            speaking:  { h: 195, spread: 160, speed: 0.70, glow: '120,220,255' },
            waking:    { h: 200, spread: 240, speed: 2.4, glow: '200,225,255' },
        };

        const N = reduce ? 22 : 42;
        const nodes = [];
        for (let i = 0; i < N; i++) {
            const y = 1 - (i / (N - 1)) * 2;
            const rad = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = i * 2.39996;
            nodes.push({ x: Math.cos(theta) * rad, y, z: Math.sin(theta) * rad,
                         size: 1.7 + Math.random() * 1.8 });
        }
        const seen = new Set(), L = [];
        for (let i = 0; i < N; i++) {
            const ds = [];
            for (let j = 0; j < N; j++) if (j !== i) {
                const dx = nodes[i].x-nodes[j].x, dy = nodes[i].y-nodes[j].y, dz = nodes[i].z-nodes[j].z;
                ds.push([dx*dx+dy*dy+dz*dz, j]);
            }
            ds.sort((a, b) => a[0]-b[0]);
            for (let k = 0; k < 3; k++) {
                const j = ds[k][1], a = Math.min(i, j), b = Math.max(i, j), key = a+'_'+b;
                if (!seen.has(key)) { seen.add(key); L.push([a, b]); }
            }
        }
        const STREAMS = [
            { hue: 190, y: -0.55, amp: 0.55, phase: 0.0, speed: 0.55 },
            { hue: 320, y:  0.10, amp: 0.62, phase: 2.1, speed: 0.45 },
            { hue: 35,  y:  0.60, amp: 0.50, phase: 4.0, speed: 0.65 },
            { hue: 265, y: -0.10, amp: 0.45, phase: 1.0, speed: 0.40 },
        ];
        const bokeh = [];
        for (let i = 0; i < (reduce ? 4 : 9); i++)
            bokeh.push({ a: Math.random()*TAU, r: R*(1.45+Math.random()*0.9),
                sz: 7+Math.random()*15, hue: [190,320,35,265][i%4],
                sp: (Math.random()*0.3+0.08)*(Math.random()<0.5?-1:1), bob: Math.random()*TAU });

        function drawStream(s, lvl, t) {
            const ph = t*s.speed + s.phase, baseY = cy + s.y*R, amp = s.amp*R*(0.8+lvl*0.5), steps = 26;
            ctx.lineWidth = 2.2 + lvl*2.8; ctx.lineCap = 'round';
            for (let i = 0; i < steps; i++) {
                const u0 = i/steps, u1 = (i+1)/steps;
                const env0 = Math.sin(u0*Math.PI), env1 = Math.sin(u1*Math.PI);
                const x0 = -12+u0*(CSS+24), x1 = -12+u1*(CSS+24);
                const y0 = baseY + Math.sin(u0*6+ph)*amp*env0, y1 = baseY + Math.sin(u1*6+ph)*amp*env1;
                const head = ((u0 - (t*s.speed*0.5))%1+1)%1;
                const bright = Math.pow(1 - Math.abs(((head+0.5)%1)-0.5)*2, 2);
                const o = (0.07+bright*0.55)*(0.6+lvl*0.6)*env0;
                ctx.strokeStyle = `hsla(${s.hue},95%,${60+bright*25}%,${o})`;
                ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke();
            }
        }

        let t = 0, last = performance.now();
        let curHue = PALETTE.idle.h, curSpread = PALETTE.idle.spread, curSpeed = PALETTE.idle.speed;

        function frame(now) {
            const dt = Math.min(0.05, (now-last)/1000); last = now; t += dt;
            const waking = isWaking(now);
            const p = waking ? PALETTE.waking : (PALETTE[window.avatarState] || PALETTE.idle);
            const blend = waking ? 0.22 : 0.06;
            curHue    += (p.h - curHue) * blend;
            curSpread += (p.spread - curSpread) * blend;
            curSpeed  += (p.speed - curSpeed) * blend;
            window.avatarLevel *= 0.86;
            const lvl = window.avatarLevel;
            const ry = t*curSpeed*(1+lvl*1.2), rx = Math.sin(t*0.3)*0.35;
            const cosY = Math.cos(ry), sinY = Math.sin(ry), cosX = Math.cos(rx), sinX = Math.sin(rx);
            const pulse = (1 + lvl*0.22 + Math.sin(t*1.2)*0.02) * R;

            ctx.clearRect(0, 0, CSS, CSS);
            ctx.globalCompositeOperation = 'lighter';

            for (const b of bokeh) {
                b.a += b.sp*dt;
                const bx = cx+Math.cos(b.a)*b.r, byy = cy+Math.sin(b.a)*b.r*0.7+Math.sin(t+b.bob)*4;
                const g = ctx.createRadialGradient(bx,byy,0,bx,byy,b.sz);
                g.addColorStop(0, `hsla(${b.hue},90%,65%,${0.10+lvl*0.10})`);
                g.addColorStop(1, `hsla(${b.hue},90%,55%,0)`);
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(bx,byy,b.sz,0,TAU); ctx.fill();
            }

            const pts = [];
            for (const nd of nodes) {
                let x = nd.x*cosY - nd.z*sinY;
                let z = nd.x*sinY + nd.z*cosY;
                let y = nd.y*cosX - z*sinX;
                z = nd.y*sinX + z*cosX;
                const scale = FOCAL/(FOCAL - z*pulse);
                pts.push({ sx: cx+x*pulse*scale, sy: cy+y*pulse*scale, depth: (z+1)/2, scale, nd });
            }

            for (const s of STREAMS) drawStream(s, lvl, t);

            ctx.lineWidth = 1;
            for (const [a, b] of L) {
                const pa = pts[a], pb = pts[b], dep = (pa.depth+pb.depth)/2;
                const hue = curHue + dep*curSpread + t*16;
                ctx.strokeStyle = `hsla(${hue},85%,${55+lvl*15}%,${(0.08+dep*0.42)*(0.7+lvl*0.6)})`;
                ctx.beginPath(); ctx.moveTo(pa.sx,pa.sy); ctx.lineTo(pb.sx,pb.sy); ctx.stroke();
            }

            pts.sort((a, b) => a.depth - b.depth);
            for (const pt of pts) {
                const hue = curHue + pt.depth*curSpread + t*22;
                const sz = pt.nd.size*pt.scale*(0.7+pt.depth*0.6)*(1+lvl*0.6);
                const alpha = 0.35 + pt.depth*0.6;
                const g = ctx.createRadialGradient(pt.sx,pt.sy,0,pt.sx,pt.sy,sz*3.4);
                g.addColorStop(0, `hsla(${hue},95%,68%,${alpha})`);
                g.addColorStop(1, `hsla(${hue},95%,60%,0)`);
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(pt.sx,pt.sy,sz*3.4,0,TAU); ctx.fill();
                const gb = ctx.createRadialGradient(pt.sx-sz*0.4,pt.sy-sz*0.5,sz*0.1,pt.sx,pt.sy,sz);
                gb.addColorStop(0, `hsla(${hue},100%,92%,${alpha})`);
                gb.addColorStop(0.5, `hsla(${hue},95%,65%,${alpha*0.9})`);
                gb.addColorStop(1, `hsla(${hue+20},90%,45%,${alpha*0.7})`);
                ctx.fillStyle = gb; ctx.beginPath(); ctx.arc(pt.sx,pt.sy,sz,0,TAU); ctx.fill();
                ctx.fillStyle = `hsla(0,0%,100%,${alpha*0.8})`;
                ctx.beginPath(); ctx.arc(pt.sx-sz*0.35,pt.sy-sz*0.4,sz*0.28,0,TAU); ctx.fill();
            }

            ctx.globalCompositeOperation = 'source-over';
            cv.style.filter = `drop-shadow(0 0 ${14+lvl*30}px rgba(${p.glow},${0.25+lvl*0.4}))`;
            requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    // ══════════════════════════════════════════════════════════════════════
    //  HUMAN — full-body 3D avatar (TalkingHead + three.js, all local files)
    //  Realistic person with facial expressions, gaze, gestures and real
    //  lip-sync. Drives the same contract; additionally exposes
    //  window.avatarSpeak(b64, text) so the page can hand TTS audio over for
    //  proper mouth animation. Falls back to the mascot on any failure.
    // ══════════════════════════════════════════════════════════════════════
    function startHuman() {
        const wrap = avatarCanvas.parentElement;
        const holder = document.createElement('div');
        holder.id = 'avatar-human';
        avatarCanvas.style.display = 'none';
        wrap.classList.add('human');
        wrap.appendChild(holder);

        let head = null, stateTimer = null;
        let failed = false;
        function fail(err) {
            if (failed) return;
            failed = true;
            console.warn('[avatar] human renderer unavailable — using mascot.', err);
            if (stateTimer) clearInterval(stateTimer);
            delete window.avatarSpeak;
            delete window.avatarGesture;
            delete window.avatarAnimation;
            holder.remove();
            wrap.classList.remove('human');
            avatarCanvas.style.display = '';
            startMascot();
        }

        // Piper gives us audio but no word timings — estimate them by spreading
        // the words over the clip weighted by word length. Close enough for
        // natural-looking visemes.
        function estimateTimings(text, durationMs) {
            const words = (text || '').trim().split(/\s+/).filter(Boolean);
            const wtimes = [], wdurations = [];
            if (words.length) {
                const weights = words.map(w => w.length + 2);
                const sum = weights.reduce((a, b) => a + b, 0);
                let tcur = 0;
                for (let i = 0; i < words.length; i++) {
                    const d = durationMs * weights[i] / sum;
                    wtimes.push(Math.round(tcur));
                    wdurations.push(Math.round(d * 0.9));
                    tcur += d;
                }
            }
            return { words, wtimes, wdurations };
        }

        const guessLang = (text) =>
            /[äöüß]|\b(und|ich|nicht|das|ist|ein|eine|der|die)\b/i.test(text || '') ? 'de' : 'en';

        import('talkinghead').then(async ({ TalkingHead }) => {
            // Camera framing: full body by default; override with
            // <canvas id="avatar" data-avatar-view="upper|mid|head">.
            const view = (avatarCanvas.dataset.avatarView || 'full').toLowerCase();
            head = new TalkingHead(holder, {
                lipsyncModules: ['en', 'de'],
                lipsyncLang: 'en',
                cameraView: ['full', 'mid', 'upper', 'head'].includes(view) ? view : 'full',
                cameraRotateEnable: false,
                cameraPanEnable: false,
                cameraZoomEnable: false,
                avatarMood: 'neutral',
                // Cinematic 3-point-ish lighting: a warm key from the front
                // left, soft fill, and a cool rim that separates her from the
                // dark UI. Flattering on skin instead of the flat default.
                lightAmbientColor: 0xfff2e6,
                lightAmbientIntensity: 1.6,
                lightDirectColor: 0xfff0dd,
                lightDirectIntensity: 28,
                lightDirectPhi: 0.9,
                lightDirectTheta: 1.6,
                lightSpotColor: 0x66aaff,
                lightSpotIntensity: 12,
                lightSpotPhi: 0.5,
                lightSpotTheta: 3.6,
                lightSpotDispersion: 1.4,
                // Sharper render + smoother motion than the defaults.
                modelPixelRatio: 1.5,
                modelFPS: 60,
                statsNode: null,
            });
            await head.showAvatar({
                url: '/avatars/brunette.glb',
                body: 'F',
                avatarMood: 'neutral',
                lipsyncLang: 'en',
            });

            // Map the shared contract onto moods / gaze / gestures.
            const MOODS = { idle: 'neutral', listening: 'happy', thinking: 'neutral', speaking: 'happy' };
            let lastState = null, wakeApplied = false;
            stateTimer = setInterval(() => {
                try {
                    const waking = performance.now() < (window.__avatarWakeUntil || 0);
                    if (waking && !wakeApplied) {
                        wakeApplied = true;
                        head.setMood('love');
                        head.playGesture('handup', 2);
                        head.lookAtCamera(800);
                    } else if (!waking && wakeApplied) {
                        wakeApplied = false;
                        head.setMood(MOODS[window.avatarState] || 'neutral');
                    }
                    if (window.avatarState !== lastState) {
                        lastState = window.avatarState;
                        if (!waking) head.setMood(MOODS[lastState] || 'neutral');
                        if (lastState === 'listening') head.lookAtCamera(1000);
                        // Occasionally raise an index finger — "one moment…"
                        if (lastState === 'thinking' && Math.random() < 0.3) head.playGesture('index', 2);
                    }
                } catch (e) { /* one bad tick must not kill the loop */ }
            }, 250);

            // Perform a named gesture on request (backend's avatar_move skill).
            // Returns true only if the name is one the rig actually knows —
            // playGesture() silently ignores unknown names, so check first.
            window.avatarGesture = (name, seconds = 3) => {
                if (!head || failed || !name) return false;
                const known = (head.gestureTemplates && head.gestureTemplates[name])
                           || (head.animEmojis && head.animEmojis[name]);
                if (!known) return false;
                try {
                    head.playGesture(name, seconds);
                    head.lookAtCamera(800);
                    return true;
                } catch (e) { return false; }
            };

            // Only one animation can play at a time — starting a second one
            // replaces the first. So a clip the user actually asked for is
            // protected until it has finished: without this, the "talking"
            // gesturing below (or an idle clip) silently overwrote the dance
            // or the demo she had just been asked to perform.
            let protectedUntil = 0;

            function playClip(name, seconds, { ambient = false } = {}) {
                if (!head || failed || !name) return false;
                // The name goes straight into a URL — keep it strictly safe.
                if (!/^[a-z0-9][a-z0-9-]*$/.test(name)) return false;
                // Ambient motion never interrupts a requested move.
                if (ambient && performance.now() < protectedUntil) return false;
                try {
                    const p = head.playAnimation(`/animations/${name}.fbx`, null, seconds);
                    if (p && p.catch) p.catch(e => console.warn('[avatar] animation failed:', name, e));
                    if (!ambient) protectedUntil = performance.now() + seconds * 1000;
                    return true;
                } catch (e) {
                    console.warn('[avatar] animation failed:', name, e);
                    return false;
                }
            }

            // Play a full-body Mixamo clip from /animations/<name>.fbx.
            // Unlike gestures (arms only) this animates the whole skeleton.
            window.avatarAnimation = (name, seconds = 8) => playClip(name, seconds);

            // ── Free movement ─────────────────────────────────────────────
            // Clips are discovered server-side, so any .fbx dropped into
            // frontend/animations/ becomes usable without touching this file.
            let clips = { animations: [], idle: [] };
            let idleTimer = null, lastIdle = 0;
            const IDLE_MIN_GAP_MS = 45000;   // don't fidget constantly

            fetch('/api/avatar/animations')
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (!data) return;
                    clips = data;
                    if (clips.idle && clips.idle.length) scheduleIdle();
                })
                .catch(() => { /* offline / no backend — gestures still work */ });

            // Occasional ambient motion so she doesn't stand frozen between
            // conversations. Only ever while genuinely idle, never mid-reply.
            function scheduleIdle() {
                clearTimeout(idleTimer);
                const wait = IDLE_MIN_GAP_MS + Math.random() * 45000;
                idleTimer = setTimeout(() => {
                    const quiet = window.avatarState === 'idle'
                               && performance.now() > lastIdle + IDLE_MIN_GAP_MS;
                    if (quiet && clips.idle.length) {
                        const pick = clips.idle[Math.floor(Math.random() * clips.idle.length)];
                        playClip(pick, 6, { ambient: true });
                        lastIdle = performance.now();
                    }
                    scheduleIdle();
                }, wait);
            }

            // Gesture naturally while speaking, if a "talking" clip exists.
            function talkingClip() {
                return clips.animations && clips.animations.includes('talking')
                    ? 'talking' : null;
            }

            // TTS playback + real lip-sync. Returns a Promise while handling
            // (page waits for it), or null → page falls back to plain audio.
            window.avatarSpeak = (b64, text) => {
                if (!head || failed) return null;
                try {
                    const bin = atob(b64);
                    const bytes = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    return head.audioCtx.decodeAudioData(bytes.buffer).then(audio =>
                        new Promise(resolve => {
                            const { words, wtimes, wdurations } = estimateTimings(text, audio.duration * 1000);
                            // Move her hands while she talks — a person
                            // explaining something doesn't stand rigid. Only
                            // for replies long enough to be worth it.
                            // Ambient: skipped while a requested move is still
                            // playing, so "dance for me" isn't cut short by
                            // her starting to gesture at the reply.
                            const clip = talkingClip();
                            if (clip && audio.duration > 3) {
                                playClip(clip, Math.min(audio.duration, 20), { ambient: true });
                            }
                            head.speakAudio({ audio, words, wtimes, wdurations },
                                            { lipsyncLang: guessLang(text) });
                            head.speakMarker(() => resolve());
                            // Safety net in case the marker never fires.
                            setTimeout(resolve, audio.duration * 1000 + 4000);
                        })
                    ).catch(() => null);
                } catch (e) { return null; }
            };
        }).catch(fail);

        // WebGL sanity check — bail out early on devices without it.
        try {
            const test = document.createElement('canvas');
            if (!test.getContext('webgl2') && !test.getContext('webgl')) fail(new Error('WebGL unavailable'));
        } catch (e) { fail(e); }
    }

    // Wake handling for the human renderer: reuse the shared timestamp via a
    // window mirror (the mascot/orb close over avatarWakeUntil directly).
    const origWakeBurst = window.avatarWakeBurst;
    window.avatarWakeBurst = (ms = 1700) => {
        window.__avatarWakeUntil = performance.now() + ms;
        origWakeBurst(ms);
    };

    const which = (avatarCanvas.dataset.avatar || 'human').toLowerCase();
    if (which === 'orb') startOrb();
    else if (which === 'mascot') startMascot();
    else startHuman();
})();
