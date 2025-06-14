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
import base64

# ----------------------------------------------------------------------
# 1. アプリケーション設定
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="現場分析レポート",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)
BATCH_SIZE = 5  # モバイル環境を考慮し、一度に処理する枚数を調整

# セッション状態（アプリの状態を保存する場所）の初期化
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'report_payload' not in st.session_state:
    st.session_state.report_payload = None
if 'files_dict' not in st.session_state:
    st.session_state.files_dict = None
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'edited_report' not in st.session_state:
    st.session_state.edited_report = None

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
        password = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン"):
            if password == PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("パスワードが間違っています。")
        st.stop()
    return True


# ----------------------------------------------------------------------
# 3. デザインとGCP初期化
# ----------------------------------------------------------------------
def inject_custom_css():
    """モバイル表示に最適化したカスタムCSS"""
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        /* 全体の背景と文字色 */
        .stApp {
            background-color: #f0f2f6;
        }
        /* メインコンテンツエリアの余白調整 */
        .block-container {
            padding: 1rem 1rem 3rem 1rem !important;
        }
        /* カードスタイルの基本 */
        .card {
            background: #ffffff;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border: 1px solid #e5e7eb;
        }
        /* 写真のスタイル */
        .stImage img {
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        /* 指摘事項カードのスタイル */
        .finding-card {
            padding: 12px;
            border-radius: 8px;
            margin-top: 12px;
            border-left: 5px solid;
        }
        .finding-high { border-color: #ef4444; background-color: #fef2f2; }
        .finding-medium { border-color: #f97316; background-color: #fff7ed; }
        .finding-low { border-color: #3b82f6; background-color: #eff6ff; }
        
        .finding-location {
            font-weight: bold;
            font-size: 1.1em;
            color: #1f2937;
            margin-bottom: 8px;
        }
        .finding-details p {
            margin-bottom: 4px;
            line-height: 1.5;
            color: #374151;
        }
        .finding-details strong {
            color: #111827;
        }
        /* 所見・問題なしボックス */
        .observation-box {
            background-color: #f0fdf4;
            border-left: 5px solid #22c55e;
            padding: 12px;
            border-radius: 8px;
            margin-top: 12px;
        }
        /* ボタンのスタイル */
        .stButton button {
            width: 100%;
            border-radius: 8px;
            font-weight: bold;
        }
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
    response = model.generate_content([prompt] + image_parts, request_options={"timeout": 120})
    return response.text

def parse_json_response(text):
    """AIの応答からJSON部分を安全に抽出して解析"""
    # ```json ... ``` や ``` ... ``` で囲まれている場合を考慮
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
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')

    st.markdown(f"### {report_title}")
    st.caption(f"調査日: {survey_date}")
    
    # --- サマリー表示 ---
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("写真枚数", f"{len(report_data)}枚")
    with col2:
        st.metric("指摘件数", f"{total_findings}件")
    with col3:
        st.metric("緊急度「高」", f"{high_priority_count}件", delta=f"-{high_priority_count}" if high_priority_count > 0 else "0")
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 詳細分析結果 ---
    st.subheader("詳細分析結果")
    for i, item in enumerate(report_data):
        st.markdown(f'<div class="card">', unsafe_allow_html=True)
        # 写真を表示
        if files_dict and item.get('file_name') in files_dict:
            st.image(files_dict[item['file_name']], caption=f"{i + 1}. {item['file_name']}", use_column_width=True)
        
        # 指摘事項を表示
        findings = item.get("findings", [])
        if findings:
            for finding in findings:
                priority = finding.get('priority', '中').lower()
                location = finding.get('location', '場所未記載')
                current_state = finding.get('current_state', '')
                suggested_work = finding.get('suggested_work', '')
                notes = finding.get('notes', '')

                st.markdown(f'<div class="finding-card finding-{priority}">', unsafe_allow_html=True)
                st.markdown(f'<div class="finding-location">{location} [緊急度: {priority.upper()}]</div>', unsafe_allow_html=True)
                details_html = f"""
                <div class="finding-details">
                    <p><strong>現状:</strong> {html.escape(current_state)}</p>
                    <p><strong>提案:</strong> {html.escape(suggested_work)}</p>
                """
                if notes:
                    details_html += f'<p><strong>備考:</strong> {html.escape(notes)}</p>'
                details_html += "</div>"
                st.markdown(details_html, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        
        # 所見または問題なしの場合
        elif item.get("observation"):
            st.markdown(f'<div class="observation-box"><strong>所見:</strong> {html.escape(item["observation"])}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="observation-box">✔ 修繕の必要箇所は見つかりませんでした。</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

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

    # --- レポート表示画面 ---
    if st.session_state.report_payload:
        display_report(st.session_state.report_payload, st.session_state.files_dict)
        if st.button("✨ 新しいレポートを作成する"):
            st.session_state.clear()
            st.rerun()
        return

    # --- レポート作成（入力）画面 ---
    st.header("レポート作成")
    with st.form("report_form"):
        report_title = st.text_input("物件名・案件名", "（例）〇〇ビル 301号室 原状回復工事")
        survey_date = st.date_input("調査日", date.today())
        
        uploaded_files = st.file_uploader(
            "分析したい写真を選択（複数可）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        
        submitted = st.form_submit_button(
            "分析を開始する",
            type="primary",
            disabled=st.session_state.processing
        )

    if submitted and not uploaded_files:
        st.warning("写真をアップロードしてください。")

    if submitted and uploaded_files:
        st.session_state.processing = True
        st.rerun() # UIを更新して処理中表示に切り替える

    if st.session_state.processing:
        st.info("AIによる分析を開始しました。写真の枚数に応じて数分かかることがあります。")
        progress_bar = st.progress(0, text="準備中...")
        final_report_data = []
        try:
            total_batches = math.ceil(len(uploaded_files) / BATCH_SIZE)
            for i in range(0, len(uploaded_files), BATCH_SIZE):
                current_batch_num = (i // BATCH_SIZE) + 1
                progress_text = f"写真を分析中... (バッチ {current_batch_num}/{total_batches})"
                progress_bar.progress(i / len(uploaded_files), text=progress_text)

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
        except Exception as e:
            st.error(f"分析処理中にエラーが発生しました: {str(e)}")
        finally:
            st.session_state.processing = False
            st.rerun()

if __name__ == "__main__":
    main()
