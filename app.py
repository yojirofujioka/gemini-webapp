import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date
import math
from PIL import Image
import io
import html
import time

# ----------------------------------------------------------------------
# 1. アプリケーション設定
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="現場分析レポート",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)
BATCH_SIZE = 5

# ----------------------------------------------------------------------
# 2. パスワード認証
# ----------------------------------------------------------------------
def check_password():
    """Secretsに保存されたパスワードで認証を行う"""
    try:
        PASSWORD = st.secrets["PASSWORD"]
    except (KeyError, FileNotFoundError):
        st.error("パスワードが設定されていません。")
        st.info("このアプリを実行するには、secrets.tomlファイルに'PASSWORD = \"あなたのパスワード\"'を設定する必要があります。")
        st.stop()

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if not st.session_state.password_correct:
        password = st.text_input("パスワードを入力してください", type="password", key="password_input")
        if st.button("ログイン", key="login_button"):
            if password == PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("パスワードが間違っています。")
        st.stop()
    return True

# ----------------------------------------------------------------------
# 3. デザイン（CSS）
# ----------------------------------------------------------------------
def inject_custom_css():
    """ライトモードとダークモード両対応のカスタムCSS"""
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        /* ========== 基本スタイル (ライトモード) ========== */
        :root {
            --card-bg-color: #ffffff;
            --card-border-color: #e5e7eb;
            --text-color-primary: #111827;
            --text-color-secondary: #374151;
            --finding-high-bg: #fef2f2;
            --finding-high-border: #ef4444;
            --finding-medium-bg: #fff7ed;
            --finding-medium-border: #f97316;
            --finding-low-bg: #eff6ff;
            --finding-low-border: #3b82f6;
            --observation-bg: #f0fdf4;
            --observation-border: #22c55e;
        }

        /* ========== ダークモード用の上書き ========== */
        body[data-theme="dark"] {
            --card-bg-color: #1f2937;
            --card-border-color: #374151;
            --text-color-primary: #f9fafb;
            --text-color-secondary: #d1d5db;
            --finding-high-bg: #450a0a;
            --finding-high-border: #ef4444;
            --finding-medium-bg: #4a2c0d;
            --finding-medium-border: #f97316;
            --finding-low-bg: #1e3a8a;
            --finding-low-border: #3b82f6;
            --observation-bg: #064e3b;
            --observation-border: #22c55e;
        }

        /* ========== 共通スタイル ========== */
        .block-container {
            padding: 1rem 1rem 3rem 1rem !important;
        }
        .card {
            background-color: var(--card-bg-color);
            border: 1px solid var(--card-border-color);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        .stImage img { border-radius: 8px; }
        .finding-card, .observation-box {
            padding: 12px;
            border-radius: 8px;
            margin-top: 12px;
            border-left: 5px solid;
        }
        .finding-high { background-color: var(--finding-high-bg); border-color: var(--finding-high-border); }
        .finding-medium { background-color: var(--finding-medium-bg); border-color: var(--finding-medium-border); }
        .finding-low { background-color: var(--finding-low-bg); border-color: var(--finding-low-border); }
        .observation-box { background-color: var(--observation-bg); border-color: var(--observation-border); }
        
        .finding-location {
            font-weight: bold;
            font-size: 1.1em;
            color: var(--text-color-primary);
            margin-bottom: 8px;
        }
        .finding-details p {
            margin-bottom: 4px;
            line-height: 1.5;
            color: var(--text-color-secondary);
        }
        .finding-details strong { color: var(--text-color-primary); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def initialize_vertexai():
    """GCPサービスアカウント情報を使ってVertex AIを初期化"""
    try:
        gcp_secrets = st.secrets["gcp"]
        service_account_info = json.loads(gcp_secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        vertexai.init(project=gcp_secrets["project_id"], location="asia-northeast1", credentials=credentials)
        return GenerativeModel("gemini-1.5-pro")
    except Exception as e:
        st.error(f"GCPの認証に失敗しました: {e}")
        st.info("secrets.tomlファイルにGCPの認証情報が正しく設定されているか確認してください。")
        return None

# ----------------------------------------------------------------------
# 4. AIとデータ処理
# ----------------------------------------------------------------------
def create_report_prompt(filenames):
    """現場での確認に最適化された、簡潔かつ重要な情報を重視するプロンプト"""
    file_list_str = "\\n".join([f"- {name}" for name in filenames])
    return f"""
    あなたは日本のリフォーム工事専門のベテラン現場監督です。提供された現場写真を分析し、新人監督がスマホで確認しながら使える、具体的で実用的な修繕指示レポートを作成してください。

    【重視する点】
    - **見落とし防止**: 新人が見逃しがちな細かい点も指摘する。
    - **具体的な指示**: 何をすべきか明確に記述する。
    - **リスク回避**: 寸法間違いや仕様違いが起きやすい点について注意喚起する。

    【各指摘事項に含める情報】
    - "location": (string) どこで問題が起きているか。（例：「リビング北側壁、床から30cmの高さ」）
    - "current_state": (string) 何がどうなっているか。（例：「幅5cmの擦り傷と、深さ2mmの凹み」）
    - "suggested_work": (string) 具体的に何をすべきか。（例：「パテで補修後、部分的なクロス張替え。品番はAA-1234」）
    - "priority": (string) 「高」「中」「低」の3段階評価。
    - "notes": (string) 新人へのアドバイス。（例：「採寸時は窓枠の内寸も測ること。結露による下地の腐食も確認。」）

    **最重要**: 出力は純粋なJSON文字列のみとすること。説明文や ```json ... ``` のようなマークダウンは絶対に含めないでください。

    **JSONの構造**:
    `[ {{ "file_name": "...", "findings": [{{...}}], "observation": "..." }}, ... ]`
    という形式のリストにしてください。
    - "findings" がない場合は、"observation" に「設備は正常。定期清掃を推奨」のように写真から分かる状態を記述してください。
    - "findings" がある場合、"observation" は空文字列 `""` にしてください。

    分析対象ファイル: {file_list_str}
    それでは、分析を開始してください。プロの目で、現場で本当に役立つレポートを作成してください。
    """

def generate_ai_report(model, file_batch, prompt):
    """画像とプロンプトをAIに送り、レポートを生成"""
    image_parts = [Part.from_data(f.getvalue(), mime_type=f.type) for f in file_batch]
    response = model.generate_content([prompt] + image_parts)
    return response.text

def parse_json_response(text):
    """AIの応答からJSON部分を安全に抽出して解析"""
    match = re.search(r'```(json)?\s*(.*?)\s*```', text, re.DOTALL)
    json_str = match.group(2) if match else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        st.error(f"AIからの応答をJSONとして解析できませんでした。")
        st.info("AIからの生の応答:")
        st.code(text, language="text")
        return None

# ----------------------------------------------------------------------
# 5. レポート表示
# ----------------------------------------------------------------------
def display_report(report_payload, files_dict):
    """生成されたレポートをモバイルフレンドリーに表示"""
    st.header(report_payload.get('title', '分析レポート'))
    st.caption(f"調査日: {report_payload.get('date', '')}")
    
    report_data = report_payload.get('report_data', [])
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    with st.container(border=True):
        st.subheader("分析サマリー")
        col1, col2, col3 = st.columns(3)
        col1.metric("写真枚数", f"{len(report_data)}枚")
        col2.metric("指摘件数", f"{total_findings}件")
        col3.metric("緊急度「高」", f"{high_priority_count}件", delta=f"{high_priority_count}", delta_color="inverse")

    st.subheader("詳細分析結果")
    for i, item in enumerate(report_data):
        with st.container(border=True):
            if files_dict and item.get('file_name') in files_dict:
                # ★★★★★ 修正点 ★★★★★
                # use_column_width を use_container_width に変更
                st.image(files_dict[item['file_name']], caption=f"{i + 1}. {item['file_name']}", use_container_width=True)
            
            findings = item.get("findings", [])
            if findings:
                for finding in findings:
                    priority = finding.get('priority', '中').lower()
                    location = finding.get('location', '場所未記載')
                    details_html = f"""
                    <div class="finding-card finding-{priority}">
                        <div class="finding-location">{html.escape(location)} [緊急度: {priority.upper()}]</div>
                        <div class="finding-details">
                            <p><strong>現状:</strong> {html.escape(finding.get('current_state', ''))}</p>
                            <p><strong>提案:</strong> {html.escape(finding.get('suggested_work', ''))}</p>
                            {'<p><strong>備考:</strong> ' + html.escape(finding.get('notes', '')) + '</p>' if finding.get('notes') else ''}
                        </div>
                    </div>
                    """
                    st.markdown(details_html, unsafe_allow_html=True)
            elif item.get("observation"):
                st.markdown(f'<div class="observation-box"><strong>所見:</strong> {html.escape(item["observation"])}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="observation-box">✔ 修繕の必要箇所は見つかりませんでした。</div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# 6. メイン処理
# ----------------------------------------------------------------------
def main():
    inject_custom_css()
    st.title("📱 現場写真 分析レポート")

    if not check_password():
        return
    
    model = initialize_vertexai()
    if not model:
        st.stop()

    # レポートが既にあれば表示
    if 'report_payload' in st.session_state:
        display_report(st.session_state.report_payload, st.session_state.files_dict)
        if st.button("✨ 新しいレポートを作成する"):
            # セッションをクリアして最初から
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        return

    # レポートがなければ作成フォームを表示
    st.header("レポート作成")
    with st.form("report_form"):
        report_title = st.text_input("物件名・案件名", "（例）〇〇ビル 301号室 原状回復工事")
        survey_date = st.date_input("調査日", date.today())
        uploaded_files = st.file_uploader(
            "分析したい写真を選択（複数可）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        submitted = st.form_submit_button("分析を開始する", type="primary")

    if submitted:
        if not uploaded_files:
            st.warning("写真をアップロードしてください。")
            return

        with st.spinner("AIによる分析を開始しました。写真の枚数に応じて数分かかることがあります..."):
            try:
                final_report_data = []
                total_batches = math.ceil(len(uploaded_files) / BATCH_SIZE)
                progress_bar = st.progress(0.0, text="準備中...")
                
                for i in range(0, len(uploaded_files), BATCH_SIZE):
                    current_batch_num = (i // BATCH_SIZE) + 1
                    progress_text = f"写真を分析中... (バッチ {current_batch_num}/{total_batches})"
                    progress_percentage = (i / len(uploaded_files))
                    progress_bar.progress(progress_percentage, text=progress_text)
                    
                    file_batch = uploaded_files[i:i + BATCH_SIZE]
                    filenames = [f.name for f in file_batch]
                    prompt = create_report_prompt(filenames)
                    response_text = generate_ai_report(model, file_batch, prompt)
                    batch_report_data = parse_json_response(response_text)
                    
                    if batch_report_data:
                        final_report_data.extend(batch_report_data)
                    else:
                        raise Exception("AIからの応答の解析に失敗しました。")
                
                progress_bar.progress(1.0, text="分析完了！")
                
                st.session_state.files_dict = {f.name: f for f in uploaded_files}
                st.session_state.report_payload = {
                    "title": report_title,
                    "date": survey_date.strftime('%Y年%m月%d日'),
                    "report_data": final_report_data
                }
                st.success("分析が完了しました！")
                time.sleep(1)

            except Exception as e:
                st.error(f"分析処理中にエラーが発生しました: {str(e)}")
                if 'report_payload' in st.session_state:
                    del st.session_state['report_payload']
                return

        st.rerun()

if __name__ == "__main__":
    main()
