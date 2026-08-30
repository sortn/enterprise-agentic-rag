"""Visual system for the mounted Gradio application."""

custom_css = r"""
:root {
    --canvas: #07111f;
    --canvas-soft: #0b1727;
    --panel: rgba(15, 29, 46, 0.82);
    --panel-solid: #0f1d2e;
    --line: rgba(148, 163, 184, 0.16);
    --line-strong: rgba(103, 232, 249, 0.28);
    --text: #edf7ff;
    --muted: #8fa7bb;
    --cyan: #5ee7f2;
    --cyan-strong: #22d3ee;
    --blue: #60a5fa;
    --green: #5ee7a6;
    --danger: #fb7185;
}

html, body { background: var(--canvas) !important; }
body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
        radial-gradient(circle at 12% 6%, rgba(14, 165, 233, 0.16), transparent 30rem),
        radial-gradient(circle at 88% 16%, rgba(45, 212, 191, 0.10), transparent 28rem),
        linear-gradient(rgba(148, 163, 184, 0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(148, 163, 184, 0.025) 1px, transparent 1px);
    background-size: auto, auto, 42px 42px, 42px 42px;
}

.gradio-container {
    max-width: 1240px !important;
    min-height: 100vh !important;
    margin: 0 auto !important;
    padding: 30px 28px 10px !important;
    color: var(--text) !important;
    background: var(--canvas) !important;
}
.gradio-container * { box-sizing: border-box; }

.hero-shell {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) minmax(300px, .7fr);
    min-height: 400px;
    overflow: hidden;
    padding: 62px 68px;
    border: 1px solid var(--line);
    border-radius: 30px;
    background: linear-gradient(115deg, rgba(14, 34, 56, .98), rgba(8, 24, 39, .93)), var(--panel-solid);
    box-shadow: 0 30px 80px rgba(1, 8, 18, .42);
}
.hero-shell::after {
    content: "";
    position: absolute;
    width: 480px;
    height: 480px;
    right: -140px;
    top: -220px;
    border-radius: 50%;
    background: rgba(34, 211, 238, .12);
    filter: blur(15px);
}
.hero-copy { position: relative; z-index: 2; align-self: center; }
.eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #a8c5d8;
    font: 700 12px/1.2 "JetBrains Mono", Consolas, monospace;
    letter-spacing: .14em;
}
.live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 0 6px rgba(94, 231, 166, .1), 0 0 18px rgba(94, 231, 166, .65);
}
.hero-shell h1 {
    max-width: 700px;
    margin: 24px 0 20px;
    color: #f4fbff;
    font-size: clamp(42px, 5vw, 68px);
    font-weight: 720;
    line-height: 1.06;
    letter-spacing: -.045em;
}
.hero-shell h1 span {
    color: transparent;
    background: linear-gradient(90deg, var(--cyan), #a5b4fc);
    -webkit-background-clip: text;
    background-clip: text;
}
.hero-shell p {
    max-width: 670px;
    margin: 0;
    color: var(--muted);
    font-size: 16px;
    line-height: 1.8;
}
.hero-tags { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 30px; }
.hero-tags span {
    padding: 8px 12px;
    border: 1px solid rgba(94, 231, 242, .16);
    border-radius: 999px;
    color: #bcd2e1;
    background: rgba(94, 231, 242, .055);
    font: 600 12px/1 "JetBrains Mono", Consolas, monospace;
}
.hero-visual { position: relative; z-index: 1; min-height: 275px; }
.core-mark {
    position: absolute;
    left: 50%;
    top: 50%;
    display: flex;
    width: 148px;
    height: 148px;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    transform: translate(-50%, -50%);
    border: 1px solid rgba(103, 232, 249, .5);
    border-radius: 42px;
    color: white;
    background: linear-gradient(145deg, rgba(34, 211, 238, .22), rgba(59, 130, 246, .12));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.15), 0 20px 60px rgba(8,145,178,.2);
    backdrop-filter: blur(12px);
}
.core-mark span { position: absolute; inset: 12px; border: 1px dashed rgba(165, 243, 252, .25); border-radius: 32px; }
.core-mark strong { font-size: 32px; letter-spacing: .06em; }
.core-mark small { margin-top: 5px; color: #97bdcf; font: 600 10px/1 monospace; text-transform: uppercase; }
.orbit {
    position: absolute;
    left: 50%;
    top: 50%;
    border: 1px solid rgba(103, 232, 249, .15);
    border-radius: 50%;
    transform: translate(-50%, -50%) rotate(-16deg);
}
.orbit-one { width: 285px; height: 210px; }
.orbit-two { width: 355px; height: 275px; transform: translate(-50%, -50%) rotate(34deg); }
.signal {
    position: absolute;
    padding: 7px 10px;
    border: 1px solid var(--line-strong);
    border-radius: 9px;
    color: #c8e5f2;
    background: rgba(8, 24, 39, .88);
    box-shadow: 0 8px 24px rgba(1, 8, 18, .28);
    font: 600 10px/1 "JetBrains Mono", Consolas, monospace;
}
.signal-a { top: 19%; left: 6%; }
.signal-b { top: 65%; left: 2%; }
.signal-c { top: 14%; right: 2%; }
.signal-d { top: 70%; right: 4%; }

.metric-grid {
    position: relative;
    z-index: 3;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: -30px 24px 0;
}
.metric-grid article {
    min-height: 132px;
    padding: 22px;
    border: 1px solid var(--line);
    border-radius: 20px;
    background: rgba(12, 27, 44, .94);
    box-shadow: 0 18px 36px rgba(1, 8, 18, .28);
    backdrop-filter: blur(14px);
}
.metric-grid span { display: block; color: #8ca9bb; font-size: 12px; font-weight: 650; }
.metric-grid strong { display: block; margin: 7px 0 5px; color: var(--text); font-size: 29px; letter-spacing: -.03em; }
.metric-grid small { color: #698399; font-size: 11px; line-height: 1.45; }

.capability-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 28px 0 54px; }
.capability-grid article { display: flex; gap: 14px; align-items: flex-start; padding: 18px 16px; border-bottom: 1px solid var(--line); }
.capability-grid i { color: var(--cyan); font: normal 700 11px/1.5 monospace; }
.capability-grid strong, .capability-grid span { display: block; }
.capability-grid strong { color: #dcecf6; font-size: 14px; }
.capability-grid span { margin-top: 6px; color: #7892a7; font-size: 12px; line-height: 1.55; }

.workspace-heading { align-items: end !important; margin: 0 2px 18px !important; }
.workspace-title h2 { margin: 0 0 5px !important; color: var(--text) !important; font-size: 25px !important; }
.workspace-title p { margin: 0 !important; color: var(--muted) !important; font-size: 13px !important; }
.status-wrap { display: flex; justify-content: flex-end; align-items: center; }
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    padding: 9px 13px;
    border: 1px solid var(--line);
    border-radius: 999px;
    color: #a9becd;
    background: rgba(15,29,46,.8);
    font-size: 12px;
    font-weight: 650;
}
.status-pill span { width: 7px; height: 7px; border-radius: 50%; }
.status-ready span { background: var(--green); box-shadow: 0 0 10px rgba(94,231,166,.7); }
.status-warming span { background: #fbbf24; }
.status-offline span { background: var(--danger); }

#main-tabs {
    overflow: hidden;
    border: 1px solid var(--line) !important;
    border-radius: 24px !important;
    background: rgba(9, 22, 37, .76) !important;
    box-shadow: 0 24px 70px rgba(1, 8, 18, .3);
}
#main-tabs > .tab-nav {
    gap: 5px;
    padding: 9px 10px 0 !important;
    border-bottom: 1px solid var(--line) !important;
    background: rgba(15,29,46,.72) !important;
}
#main-tabs button[role="tab"] {
    padding: 12px 17px !important;
    border: 0 !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 10px 10px 0 0 !important;
    color: #7993a8 !important;
    background: transparent !important;
    font-weight: 700 !important;
}
#main-tabs button[role="tab"][aria-selected="true"] {
    border-bottom-color: var(--cyan) !important;
    color: #eaf8ff !important;
    background: rgba(94,231,242,.055) !important;
}

#knowledge-chatbot {
    min-height: 560px;
    border: 0 !important;
    border-radius: 0 !important;
    background: rgba(7,17,31,.58) !important;
}
#knowledge-chatbot .message { border-radius: 16px !important; line-height: 1.72 !important; }
#knowledge-chatbot .message.user {
    border: 1px solid rgba(103,232,249,.22) !important;
    color: #e9fbff !important;
    background: linear-gradient(135deg, rgba(8,145,178,.38), rgba(37,99,235,.28)) !important;
}
#knowledge-chatbot .message.bot {
    border: 1px solid var(--line) !important;
    color: #d9e9f3 !important;
    background: rgba(15,29,46,.88) !important;
}
.empty-chat { display: flex; flex-direction: column; gap: 9px; align-items: center; color: #698399; }
.empty-chat strong { color: #bfd5e3; font-size: 17px; }
.empty-chat span { max-width: 430px; font-size: 13px; line-height: 1.6; text-align: center; }
#main-tabs textarea { color: #e9f6ff !important; caret-color: var(--cyan) !important; }
#main-tabs textarea::placeholder { color: #607b91 !important; }
#main-tabs form {
    margin: 0 16px 17px !important;
    padding: 8px !important;
    border: 1px solid rgba(103,232,249,.18) !important;
    border-radius: 16px !important;
    background: rgba(15,29,46,.94) !important;
    box-shadow: 0 12px 34px rgba(1,8,18,.24) !important;
}

button.primary {
    border: 1px solid rgba(165,243,252,.22) !important;
    color: #06202c !important;
    background: linear-gradient(135deg, var(--cyan), #7dd3fc) !important;
    font-weight: 800 !important;
    box-shadow: 0 10px 24px rgba(34,211,238,.16) !important;
}
button.primary:hover { transform: translateY(-1px); filter: brightness(1.04); }
button.secondary { border: 1px solid var(--line) !important; color: #b9cfdd !important; background: rgba(30, 47, 65, .66) !important; }
button.stop { border-radius: 12px !important; }

.document-layout { gap: 0 !important; padding: 24px !important; }
.panel-card {
    min-height: 650px;
    padding: 28px !important;
    border: 1px solid var(--line) !important;
    background: rgba(12, 26, 43, .72) !important;
}
.upload-panel { border-radius: 18px 0 0 18px !important; }
.library-panel { border-left: 0 !important; border-radius: 0 18px 18px 0 !important; }
.panel-heading h2 { margin: 0 0 8px !important; color: #e4f3fa !important; font-size: 20px !important; }
.panel-heading p { color: #7994a9 !important; font-size: 12px !important; line-height: 1.6 !important; }
.panel-title-row { align-items: flex-start !important; }
.panel-title-row button { max-width: 76px; margin-top: 3px; }

#document-uploader {
    min-height: 245px !important;
    border: 1px dashed rgba(103,232,249,.28) !important;
    border-radius: 16px !important;
    background: rgba(7,17,31,.52) !important;
    transition: border-color .2s ease, background .2s ease;
}
#document-uploader:hover { border-color: rgba(103,232,249,.62) !important; background: rgba(8,145,178,.07) !important; }
.result-card, .document-list {
    overflow: auto;
    padding: 18px !important;
    border: 1px solid var(--line) !important;
    border-radius: 14px !important;
    color: #a9c0cf !important;
    background: rgba(7,17,31,.52) !important;
}
.result-card { min-height: 82px; }
.document-list { min-height: 490px; max-height: 540px; }
.result-card h3, .document-list h3 { color: #dcecf6 !important; font-size: 16px !important; }
.document-list code { color: #73ddec !important; background: rgba(34,211,238,.07) !important; }

.guide-card { margin-top: 8px; padding: 19px; border: 1px solid var(--line); border-radius: 14px; background: rgba(7,17,31,.32); }
.guide-title { margin-bottom: 14px; color: #bdd2df; font-size: 13px; font-weight: 800; }
.guide-card ol { display: grid; gap: 13px; margin: 0; padding: 0; list-style: none; }
.guide-card li { display: flex; gap: 11px; align-items: flex-start; }
.guide-card li > span {
    display: grid; width: 23px; height: 23px; flex: 0 0 23px; place-items: center;
    border: 1px solid rgba(94,231,242,.22); border-radius: 7px; color: var(--cyan); font: 700 10px monospace;
}
.guide-card strong, .guide-card small { display: block; }
.guide-card strong { color: #b9cfdd; font-size: 12px; }
.guide-card small { margin-top: 3px; color: #668197; font-size: 11px; line-height: 1.45; }

.app-footer {
    display: flex;
    justify-content: space-between;
    margin: 28px 2px 0;
    padding: 20px 4px;
    border-top: 1px solid var(--line);
    color: #547086;
    font: 600 11px/1.4 "JetBrains Mono", Consolas, monospace;
}
.progress-text { display: none !important; }
footer:not(.app-footer) { display: none !important; }

@media (max-width: 900px) {
    .gradio-container { padding: 16px 14px 8px !important; }
    .hero-shell { grid-template-columns: 1fr; padding: 42px 30px; }
    .hero-visual { display: none; }
    .metric-grid { grid-template-columns: repeat(2, 1fr); margin: 14px 0 0; }
    .capability-grid { grid-template-columns: repeat(2, 1fr); }
    .document-layout { padding: 14px !important; }
    .upload-panel, .library-panel { border: 1px solid var(--line) !important; border-radius: 16px !important; }
    .library-panel { margin-top: 12px !important; }
}
@media (max-width: 560px) {
    .hero-shell { min-height: auto; padding: 34px 22px; border-radius: 22px; }
    .hero-shell h1 { font-size: 38px; }
    .metric-grid, .capability-grid { grid-template-columns: 1fr; }
    .metric-grid article { min-height: 112px; }
    .workspace-heading { align-items: flex-start !important; }
    .status-wrap { justify-content: flex-start; }
    .app-footer { flex-direction: column; gap: 8px; }
}
"""
