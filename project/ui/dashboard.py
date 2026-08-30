"""Gradio demo UI backed by the FastAPI boundary over HTTP."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import gradio as gr
import httpx

from ui.css import custom_css


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


def create_gradio_ui(api_base_url: str):
    timeout = httpx.Timeout(180.0, connect=10.0)
    avatar = Path(__file__).resolve().parents[1] / "assets" / "chatbot_avatar.png"

    def list_documents() -> str:
        try:
            response = httpx.get(f"{api_base_url}/api/v1/documents", timeout=timeout)
            response.raise_for_status()
            documents = response.json().get("documents", [])
            if not documents:
                return "### 暂无已入库文档\n\n上传文档后，这里会显示文件名与文档 ID。"
            rows = [f"### 已入库 {len(documents)} 份文档", ""]
            for index, item in enumerate(documents, start=1):
                source = _escape_markdown(str(item.get("source", "未命名文档")))
                doc_id = _escape_markdown(str(item.get("doc_id", "-")))
                rows.append(f"**{index:02d}　{source}**  \n`{doc_id}`")
            return "\n\n".join(rows)
        except Exception as exc:
            return f"### 知识库暂不可用\n\n`{_escape_markdown(str(exc))}`"

    def upload(files):
        if not files:
            return "请选择至少一个文档。", list_documents()
        handles = []
        try:
            payload = []
            for file_path in files:
                handle = Path(file_path).open("rb")
                handles.append(handle)
                payload.append(("files", (Path(file_path).name, handle)))
            response = httpx.post(
                f"{api_base_url}/api/v1/documents",
                files=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            lines = ["### 入库完成", ""]
            for item in results:
                source = _escape_markdown(str(item.get("source", "未命名文档")))
                status = _escape_markdown(str(item.get("status", "completed")))
                chunks = item.get("chunks", 0)
                lines.append(f"- **{source}** · {status} · `{chunks}` 个子块")
            return "\n".join(lines), list_documents()
        except Exception as exc:
            return f"### 上传失败\n\n`{_escape_markdown(str(exc))}`", list_documents()
        finally:
            for handle in handles:
                handle.close()

    def chat(message, history, thread_id):
        answer = ""
        status = "正在分析问题…"
        try:
            with httpx.stream(
                "POST",
                f"{api_base_url}/api/v1/chat/stream",
                json={"question": message, "thread_id": thread_id},
                timeout=timeout,
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
                        yield f"◌　{status}"
                    elif event["event"] == "token":
                        answer += event.get("content", "")
                        yield answer
                    elif event["event"] == "final":
                        answer = event.get("answer", answer)
                        grounded = "通过" if event.get("grounded") else "未通过"
                        meta = (
                            "\n\n---\n"
                            f"**运行信息**　意图 `{event.get('intent', '')}`　·　"
                            f"检索 `{event.get('retrieval_attempts', 0)}` 次　·　"
                            f"事实校验 `{grounded}`"
                        )
                        yield answer + meta
                    elif event["event"] == "error":
                        yield f"请求失败：{event.get('message', '未知错误')}"
        except Exception as exc:
            yield f"无法连接后端：{exc}"

    with gr.Blocks(
        title="企业知识库 · Agentic RAG",
        fill_width=True,
    ) as demo:
        gr.HTML(HERO)
        gr.HTML(METRICS)
        gr.HTML(CAPABILITIES)

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
        with gr.Tabs(elem_id="main-tabs"):
            with gr.Tab("✦ 智能问答", id="chat"):
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
                    placeholder="输入关于制度、技术文档或产品手册的问题…",
                    show_label=False,
                    container=False,
                    max_lines=6,
                    submit_btn="发送",
                    stop_btn="停止",
                )
                gr.ChatInterface(
                    fn=chat,
                    chatbot=chatbot,
                    textbox=textbox,
                    additional_inputs=[thread_id],
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

            with gr.Tab("▣ 知识库管理", id="documents"):
                with gr.Row(equal_height=True, elem_classes="document-layout"):
                    with gr.Column(scale=5, min_width=340, elem_classes="panel-card upload-panel"):
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

                upload_button.click(upload, inputs=files, outputs=[upload_status, document_list])
                refresh_button.click(list_documents, outputs=document_list)

        gr.HTML(FOOTER)

    return demo
