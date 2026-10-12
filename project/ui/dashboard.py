"""Gradio demo UI backed by the FastAPI boundary over HTTP."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import gradio as gr
import httpx

from ui.css import custom_css
from ui.auth_service import AuthClient, AuthClientError, AuthSession


HERO = """
<section class="hero-shell">
  <div class="hero-copy">
    <div class="eyebrow"><span class="live-dot"></span> ENTERPRISE KNOWLEDGE COPILOT</div>
    <h1>让企业知识回答<br><span>有依据、可追溯。</span></h1>
    <p>面向制度、技术文档与产品手册的 Agentic RAG。系统会先检索、再精排、后校验，证据不足时主动拒答。</p>
    <div class="hero-tags">
      <span>Parent–Child</span><span>Hybrid Search</span><span>LangGraph</span><span>Fact Check</span>
    </div>
  </div>
  <div class="hero-visual" aria-hidden="true">
    <div class="orbit orbit-one"></div><div class="orbit orbit-two"></div>
    <div class="core-mark"><span></span><strong>RAG</strong><small>evidence first</small></div>
    <div class="signal signal-a">Dense</div><div class="signal signal-b">BM25</div>
    <div class="signal signal-c">Rerank</div><div class="signal signal-d">Verify</div>
  </div>
</section>
"""


METRICS = """
<section class="metric-grid" aria-label="离线评测摘要">
  <article><span>检索召回</span><strong>97.5%</strong><small>Hybrid + Rerank · Recall@5</small></article>
  <article><span>首条命中质量</span><strong>0.914</strong><small>500 条冻结测试 · MRR</small></article>
  <article><span>答案来源召回</span><strong>98%</strong><small>100 条独立答案 holdout</small></article>
  <article><span>总体无依据回答</span><strong>5%</strong><small>确定性规则评测</small></article>
</section>
"""


CAPABILITIES = """
<section class="capability-grid">
  <article><i>01</i><div><strong>多格式解析</strong><span>PDF、DOCX、XLSX、Markdown 与 TXT</span></div></article>
  <article><i>02</i><div><strong>双路召回</strong><span>BGE-M3 Dense + BM25，RRF 融合</span></div></article>
  <article><i>03</i><div><strong>Agentic 工作流</strong><span>查询改写、二次检索与工具调用</span></div></article>
  <article><i>04</i><div><strong>可靠性校验</strong><span>来源引用、事实检查与安全拒答</span></div></article>
</section>
"""


DOC_GUIDE = """
<div class="guide-card">
  <div class="guide-title">入库流程</div>
  <ol>
    <li><span>1</span><div><strong>选择文档</strong><small>支持批量上传，单文件不超过 20 MB</small></div></li>
    <li><span>2</span><div><strong>解析并切分</strong><small>保留页码、工作表与标题路径</small></div></li>
    <li><span>3</span><div><strong>写入索引</strong><small>子块用于召回，父块用于回答</small></div></li>
  </ol>
</div>
"""


FOOTER = """
<footer class="app-footer">
  <span>Enterprise Agentic RAG</span>
  <span>LangGraph · Milvus · BGE-M3 · FastAPI</span>
</footer>
"""


APP_THEME = gr.themes.Soft(
    primary_hue="cyan",
    secondary_hue="blue",
    neutral_hue="slate",
    spacing_size="md",
    radius_size="lg",
    text_size="md",
    font=("Inter", "PingFang SC", "Microsoft YaHei", "ui-sans-serif", "system-ui"),
    font_mono=("JetBrains Mono", "Consolas", "ui-monospace", "monospace"),
).set(
    body_background_fill="#07111f",
    body_background_fill_dark="#07111f",
    body_text_color="#edf7ff",
    body_text_color_dark="#edf7ff",
    body_text_color_subdued="#8fa7bb",
    body_text_color_subdued_dark="#8fa7bb",
    background_fill_primary="#07111f",
    background_fill_primary_dark="#07111f",
    background_fill_secondary="#0b1727",
    background_fill_secondary_dark="#0b1727",
    block_background_fill="#0f1d2e",
    block_background_fill_dark="#0f1d2e",
    block_border_color="#24394e",
    block_border_color_dark="#24394e",
    panel_background_fill="#0b1727",
    panel_background_fill_dark="#0b1727",
    input_background_fill="#0b1727",
    input_background_fill_dark="#0b1727",
    input_background_fill_focus="#0f1d2e",
    input_background_fill_focus_dark="#0f1d2e",
    input_border_color="#29445d",
    input_border_color_dark="#29445d",
    input_placeholder_color="#607b91",
    input_placeholder_color_dark="#607b91",
)


def _escape_markdown(value: str) -> str:
    """Keep document names from changing the surrounding Markdown."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", value)


def _document_identity(item: dict) -> tuple[str, str]:
    """Normalize current API fields while accepting older response payloads."""
    source = item.get("source_name") or item.get("title") or item.get("source")
    document_id = item.get("id") or item.get("doc_id")
    return (
        _escape_markdown(str(source or "未命名文档")),
        _escape_markdown(str(document_id or "-")),
    )


def _format_citations(citations: list[dict] | None) -> str:
    rows: list[str] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations or []:
        source = str(citation.get("source") or "未命名来源").strip()
        locator = str(citation.get("locator") or "").strip()
        key = (source, locator)
        if key in seen:
            continue
        seen.add(key)
        label = f"- **{_escape_markdown(source)}**"
        if locator:
            label += f" · {_escape_markdown(locator)}"
        rows.append(label)
    return "\n\n**参考来源**\n" + "\n".join(rows) if rows else ""


def create_gradio_ui(api_base_url: str):
    timeout = httpx.Timeout(180.0, connect=10.0)
    avatar = Path(__file__).resolve().parents[1] / "assets" / "chatbot_avatar.png"
    auth_client = AuthClient(api_base_url, timeout)

    def _user_label(session: AuthSession) -> str:
        role = "管理员" if session.is_admin else "普通用户"
        username = _escape_markdown(str(session.user.get("username", "-")))
        return f"**{username}**　·　{role}"

    def login(username: str, password: str):
        try:
            session = auth_client.login(username, password)
            return (
                session,
                session.to_browser_state(),
                "登录成功，正在进入知识工作台。",
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(value=_user_label(session), visible=True),
                gr.update(visible=session.is_admin),
            )
        except (AuthClientError, httpx.HTTPError) as exc:
            return (
                AuthSession(),
                {},
                f"登录失败：{exc}",
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )

    def register(username: str, email: str, password: str, confirmation: str):
        if password != confirmation:
            return (
                AuthSession(),
                {},
                "注册失败：两次输入的密码不一致。",
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )
        try:
            session = auth_client.register(username, email, password)
            return (
                session,
                session.to_browser_state(),
                "注册成功，已自动登录。",
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(value=_user_label(session), visible=True),
                gr.update(visible=session.is_admin),
            )
        except (AuthClientError, httpx.HTTPError) as exc:
            return (
                AuthSession(),
                {},
                f"注册失败：{exc}",
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )

    def logout(session: AuthSession):
        session = auth_client.logout(session)
        return (
            session,
            {},
            "已安全退出登录。",
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def restore_login(browser_state):
        if not browser_state:
            return (
                AuthSession(),
                {},
                "请输入企业账号。",
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )
        try:
            session = auth_client.restore(browser_state)
            return (
                session,
                session.to_browser_state(),
                "登录状态已恢复。",
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(value=_user_label(session), visible=True),
                gr.update(visible=session.is_admin),
            )
        except (AuthClientError, httpx.HTTPError):
            return (
                AuthSession(),
                {},
                "登录状态已过期，请重新登录。",
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
            )

    def list_documents(session: AuthSession) -> tuple[str, AuthSession, dict]:
        try:
            response = auth_client.request("GET", "/api/v1/documents", session)
            response.raise_for_status()
            documents = response.json().get("documents", [])
            if not documents:
                return (
                    "### 暂无已入库文档\n\n上传文档后，这里会显示文件名与文档 ID。",
                    session,
                    session.to_browser_state(),
                )
            rows = [f"### 已入库 {len(documents)} 份文档", ""]
            for index, item in enumerate(documents, start=1):
                source, doc_id = _document_identity(item)
                rows.append(f"**{index:02d}　{source}**  \n`{doc_id}`")
            return "\n\n".join(rows), session, session.to_browser_state()
        except Exception as exc:
            return (
                f"### 知识库暂不可用\n\n`{_escape_markdown(str(exc))}`",
                session,
                session.to_browser_state(),
            )

    def upload(files, session: AuthSession):
        if not files:
            documents, session, browser_state = list_documents(session)
            return "请选择至少一个文档。", documents, session, browser_state
        handles = []
        try:
            payload = []
            for file_path in files:
                handle = Path(file_path).open("rb")
                handles.append(handle)
                payload.append(("files", (Path(file_path).name, handle)))
            response = auth_client.request(
                "POST",
                "/api/v1/documents",
                session,
                files=payload,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            lines = ["### 入库完成", ""]
            for item in results:
                source, _ = _document_identity(item)
                status = _escape_markdown(str(item.get("status", "completed")))
                chunks = item.get("chunks", 0)
                lines.append(f"- **{source}** · {status} · `{chunks}` 个子块")
            documents, session, browser_state = list_documents(session)
            return "\n".join(lines), documents, session, browser_state
        except Exception as exc:
            documents, session, browser_state = list_documents(session)
            return (
                f"### 上传失败\n\n`{_escape_markdown(str(exc))}`",
                documents,
                session,
                browser_state,
            )
        finally:
            for handle in handles:
                handle.close()

    def chat(message, history, thread_id, session: AuthSession):
        answer = ""
        status = "正在分析问题…"
        try:
            with auth_client.stream(
                "POST",
                "/api/v1/chat/stream",
                session,
                json={"question": message, "thread_id": thread_id},
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event["event"] == "node":
                        node = event.get("node", "")
                        status = {
                            "analyze_query": "已完成意图识别与查询改写",
                            "retrieve": f"已召回 {event.get('retrieved', 0)} 个候选片段",
                            "rewrite_search": "相关性不足，正在执行二次检索",
                            "run_tool": "已完成企业工具调用",
                            "fact_check": "正在核对答案与来源证据",
                        }.get(node, status)
                        yield f"◌　{status}", session, session.to_browser_state()
                    elif event["event"] == "token":
                        answer += event.get("content", "")
                        yield answer, session, session.to_browser_state()
                    elif event["event"] == "final":
                        answer = event.get("answer", answer)
                        sources = _format_citations(event.get("citations"))
                        grounded = "通过" if event.get("grounded") else "未通过"
                        meta = (
                            "\n\n---\n"
                            f"**运行信息**　意图 `{event.get('intent', '')}`　·　"
                            f"检索 `{event.get('retrieval_attempts', 0)}` 次　·　"
                            f"事实校验 `{grounded}`"
                        )
                        yield answer + sources + meta, session, session.to_browser_state()
                    elif event["event"] == "error":
                        yield (
                            f"请求失败：{event.get('message', '未知错误')}",
                            session,
                            session.to_browser_state(),
                        )
        except Exception as exc:
            yield f"无法连接后端：{exc}", session, session.to_browser_state()

    with gr.Blocks(
        title="企业知识库 · Agentic RAG",
        fill_width=True,
    ) as demo:
        gr.HTML(HERO)
        gr.HTML(METRICS)
        gr.HTML(CAPABILITIES)

        auth_state = gr.State(lambda: AuthSession())
        browser_auth_state = gr.BrowserState(
            default_value={},
            storage_key="enterprise-rag-auth-session-v1",
        )
        with gr.Column(visible=True, elem_id="auth-gateway") as auth_panel:
            gr.Markdown(
                "## 企业账号登录\n登录后访问知识问答；管理员可维护知识库文档。",
                elem_classes="auth-heading",
            )
            with gr.Tabs(elem_id="auth-tabs"):
                with gr.Tab("登录"):
                    login_username = gr.Textbox(
                        label="用户名或邮箱",
                        placeholder="输入用户名或企业邮箱",
                    )
                    login_password = gr.Textbox(
                        label="密码",
                        type="password",
                        placeholder="输入密码",
                    )
                    login_button = gr.Button("登录", variant="primary")
                with gr.Tab("注册"):
                    register_username = gr.Textbox(
                        label="用户名",
                        placeholder="3–50 位字母、数字、点、下划线或短横线",
                    )
                    register_email = gr.Textbox(label="企业邮箱", placeholder="name@company.com")
                    register_password = gr.Textbox(label="密码", type="password")
                    register_confirmation = gr.Textbox(label="确认密码", type="password")
                    register_button = gr.Button("创建账号", variant="primary")
            auth_message = gr.Markdown("请输入企业账号。", elem_classes="auth-message")

        with gr.Row(elem_classes="workspace-heading"):
            gr.Markdown(
                "## 知识工作台\n从企业文档中检索证据，并生成带来源的可靠回答。",
                elem_classes="workspace-title",
            )
            gr.HTML(
                '<div class="status-pill status-ready"><span></span>API 已连接 · RAG 按需初始化</div>',
                elem_classes="status-wrap",
            )

        thread_id = gr.State(lambda: str(uuid.uuid4()))
        with gr.Tabs(elem_id="main-tabs", visible=False) as main_tabs:
            with gr.Tab("✦ 智能问答", id="chat"):
                with gr.Row(elem_classes="user-session-bar"):
                    user_status = gr.Markdown("", elem_classes="user-identity")
                    logout_button = gr.Button("退出登录", size="sm", variant="secondary")
                chatbot = gr.Chatbot(
                    label="企业知识助手",
                    show_label=False,
                    height=560,
                    layout="bubble",
                    avatar_images=(None, str(avatar)),
                    placeholder=(
                        "<div class='empty-chat'>"
                        "<strong>从一个具体问题开始</strong>"
                        "<span>我会检索相关片段、核对证据，并在依据不足时明确说明。</span>"
                        "</div>"
                    ),
                    elem_id="knowledge-chatbot",
                )
                textbox = gr.Textbox(
                    placeholder="在这里输入问题，按 Enter 发送…",
                    show_label=False,
                    container=False,
                    max_lines=6,
                    submit_btn="发送",
                    stop_btn="停止",
                    elem_id="question-input",
                )
                gr.ChatInterface(
                    fn=chat,
                    chatbot=chatbot,
                    textbox=textbox,
                    additional_inputs=[thread_id, auth_state],
                    additional_outputs=[auth_state, browser_auth_state],
                    flagging_mode="never",
                    save_history=False,
                )
                gr.Examples(
                    examples=[
                        "出差住宿费超过标准应该怎么处理？",
                        "NX-MEET-PRO 的实时库存是多少？",
                        "财务部的联系电话是什么？",
                    ],
                    inputs=textbox,
                    example_labels=["制度问答", "库存查询", "组织信息"],
                    label="试试这些问题",
                    run_on_click=False,
                )

            with gr.Tab("▣ 知识库管理", id="documents") as documents_tab:
                with gr.Row(equal_height=True, elem_classes="document-layout"):
                    with gr.Column(
                        scale=5,
                        min_width=340,
                        visible=False,
                        elem_classes="panel-card upload-panel",
                    ) as admin_panel:
                        gr.Markdown(
                            "## 添加企业文档\n支持 PDF、Word、Excel、Markdown 与 TXT，可一次选择多个文件。",
                            elem_classes="panel-heading",
                        )
                        files = gr.File(
                            file_count="multiple",
                            type="filepath",
                            file_types=[".pdf", ".docx", ".xlsx", ".md", ".txt"],
                            label="拖放文件到这里，或点击选择",
                            height=245,
                            elem_id="document-uploader",
                        )
                        upload_button = gr.Button("解析并写入知识库", variant="primary", size="lg")
                        upload_status = gr.Markdown(
                            "尚未开始入库。",
                            elem_classes="result-card",
                        )
                        gr.HTML(DOC_GUIDE)

                    with gr.Column(scale=5, min_width=340, elem_classes="panel-card library-panel"):
                        with gr.Row(elem_classes="panel-title-row"):
                            gr.Markdown(
                                "## 当前知识库\n查看已完成索引的文档与唯一标识。",
                                elem_classes="panel-heading",
                            )
                            refresh_button = gr.Button("刷新", size="sm", variant="secondary")
                        document_list = gr.Markdown(
                            "### 等待刷新\n\n点击右上角刷新知识库列表。",
                            elem_classes="document-list",
                        )

                upload_button.click(
                    upload,
                    inputs=[files, auth_state],
                    outputs=[upload_status, document_list, auth_state, browser_auth_state],
                )
                refresh_button.click(
                    list_documents,
                    inputs=auth_state,
                    outputs=[document_list, auth_state, browser_auth_state],
                )
                documents_tab.select(
                    list_documents,
                    inputs=auth_state,
                    outputs=[document_list, auth_state, browser_auth_state],
                )

        auth_outputs = [
            auth_state,
            browser_auth_state,
            auth_message,
            auth_panel,
            main_tabs,
            user_status,
            admin_panel,
        ]
        login_button.click(
            login,
            inputs=[login_username, login_password],
            outputs=auth_outputs,
        )
        login_password.submit(
            login,
            inputs=[login_username, login_password],
            outputs=auth_outputs,
        )
        register_button.click(
            register,
            inputs=[
                register_username,
                register_email,
                register_password,
                register_confirmation,
            ],
            outputs=auth_outputs,
        )
        logout_button.click(logout, inputs=auth_state, outputs=auth_outputs)
        demo.load(restore_login, inputs=browser_auth_state, outputs=auth_outputs)

        gr.HTML(FOOTER)

    return demo
