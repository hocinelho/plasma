/* ═══════════════════════════════════════════════════════════════════════
   Plasma avatar — renderer
   ─────────────────────────────────────────────────────────────────────
   Extracted from index.html. This file owns the on-screen avatar and
   exposes a small, stable contract that the rest of the UI drives:

       window.avatarState    'idle' | 'listening' | 'thinking' | 'speaking'
                             — set by setStatus(); the avatar mirrors it.
       window.avatarLevel    0..1 live audio amplitude — written by the
                             TTS lip-sync analyser; drives the pulse/mouth.
       window.avatarWakeBurst(ms=1700)
                             — a brief "waking up" flash on the wake word.

   Everything else is private. Served at /avatar.js.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
    const TAU = Math.PI * 2;
    const avatarCanvas = document.getElementById('avatar');
    if (!avatarCanvas) return;

    // Shared contract — established here so index.html can read/write these
    // by bare name (avatar.js is loaded before the main inline script).
    if (typeof window.avatarState !== 'string') window.avatarState = 'idle';
    if (typeof window.avatarLevel !== 'number') window.avatarLevel = 0;

    // ── JARVIS avatar — 3D glass-node sphere with flowing light streams ───────
    // Nodes sit on a rotating sphere (perspective-projected, depth-sorted), nearby
    // ones link into a neural net, fibre-optic light ribbons flow through it, bokeh
    // orbs drift behind, and the whole thing pulses live with the TTS voice
    // (avatarLevel is fed by the lip-sync analyser).
    (function initAvatar() {
        const cv = avatarCanvas, ctx = cv.getContext('2d');
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const DPR = Math.min(window.devicePixelRatio || 1, 2);
        const CSS = 190;
        cv.width = CSS * DPR; cv.height = CSS * DPR;
        ctx.scale(DPR, DPR);
        const cx = CSS / 2, cy = CSS / 2, R = CSS * 0.30, FOCAL = 260;

        // Per-state look: core hue, colour spread, spin speed, aura rgb.
        const PALETTE = {
            idle:      { h: 205, spread: 90,  speed: 0.30, glow: '120,180,255' },
            listening: { h: 330, spread: 70,  speed: 0.85, glow: '255,90,150'  },
            thinking:  { h: 160, spread: 80,  speed: 0.55, glow: '80,230,180'  },
            speaking:  { h: 195, spread: 160, speed: 0.70, glow: '120,220,255' },
            // Brief "waking up" flash — bright icy-white/blue, wide spectrum, fast
            // spin. Overrides avatarState for a couple of seconds on wake events.
            waking:    { h: 200, spread: 240, speed: 2.4, glow: '200,225,255' },
        };
        let avatarWakeUntil = 0;   // performance.now() timestamp; sphere flashes until then
        window.avatarWakeBurst = (ms = 1700) => { avatarWakeUntil = performance.now() + ms; };

        // Fibonacci sphere → even 3D node distribution.
        const N = reduce ? 22 : 42;
        const nodes = [];
        for (let i = 0; i < N; i++) {
            const y = 1 - (i / (N - 1)) * 2;
            const rad = Math.sqrt(Math.max(0, 1 - y * y));
            const theta = i * 2.39996;
            nodes.push({ x: Math.cos(theta) * rad, y, z: Math.sin(theta) * rad,
                         size: 1.7 + Math.random() * 1.8 });
        }
        // Fixed topology: link each node to its 3 nearest neighbours (dedup).
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
        // Fibre-optic light ribbons crossing the sphere.
        const STREAMS = [
            { hue: 190, y: -0.55, amp: 0.55, phase: 0.0, speed: 0.55 },
            { hue: 320, y:  0.10, amp: 0.62, phase: 2.1, speed: 0.45 },
            { hue: 35,  y:  0.60, amp: 0.50, phase: 4.0, speed: 0.65 },
            { hue: 265, y: -0.10, amp: 0.45, phase: 1.0, speed: 0.40 },
        ];
        // Bokeh depth orbs.
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
            const waking = now < avatarWakeUntil;
            const p = waking ? PALETTE.waking : (PALETTE[avatarState] || PALETTE.idle);
            const blend = waking ? 0.22 : 0.06;   // snap fast into the wake flash
            curHue    += (p.h - curHue) * blend;
            curSpread += (p.spread - curSpread) * blend;
            curSpeed  += (p.speed - curSpeed) * blend;
            avatarLevel *= 0.86;
            const lvl = avatarLevel;
            const ry = t*curSpeed*(1+lvl*1.2), rx = Math.sin(t*0.3)*0.35;
            const cosY = Math.cos(ry), sinY = Math.sin(ry), cosX = Math.cos(rx), sinX = Math.sin(rx);
            const pulse = (1 + lvl*0.22 + Math.sin(t*1.2)*0.02) * R;

            ctx.clearRect(0, 0, CSS, CSS);
            ctx.globalCompositeOperation = 'lighter';

            // bokeh depth orbs
            for (const b of bokeh) {
                b.a += b.sp*dt;
                const bx = cx+Math.cos(b.a)*b.r, by = cy+Math.sin(b.a)*b.r*0.7+Math.sin(t+b.bob)*4;
                const g = ctx.createRadialGradient(bx,by,0,bx,by,b.sz);
                g.addColorStop(0, `hsla(${b.hue},90%,65%,${0.10+lvl*0.10})`);
                g.addColorStop(1, `hsla(${b.hue},90%,55%,0)`);
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(bx,by,b.sz,0,TAU); ctx.fill();
            }

            // project nodes (rotate Y then X, perspective)
            const pts = [];
            for (const nd of nodes) {
                let x = nd.x*cosY - nd.z*sinY;
                let z = nd.x*sinY + nd.z*cosY;
                let y = nd.y*cosX - z*sinX;
                z = nd.y*sinX + z*cosX;
                const scale = FOCAL/(FOCAL - z*pulse);
                pts.push({ sx: cx+x*pulse*scale, sy: cy+y*pulse*scale, depth: (z+1)/2, scale, nd });
            }

            // flowing light streams
            for (const s of STREAMS) drawStream(s, lvl, t);

            // neural-net connections (depth-shaded)
            ctx.lineWidth = 1;
            for (const [a, b] of L) {
                const pa = pts[a], pb = pts[b], dep = (pa.depth+pb.depth)/2;
                const hue = curHue + dep*curSpread + t*16;
                ctx.strokeStyle = `hsla(${hue},85%,${55+lvl*15}%,${(0.08+dep*0.42)*(0.7+lvl*0.6)})`;
                ctx.beginPath(); ctx.moveTo(pa.sx,pa.sy); ctx.lineTo(pb.sx,pb.sy); ctx.stroke();
            }

            // glassy nodes, back-to-front
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
    })();
})();
