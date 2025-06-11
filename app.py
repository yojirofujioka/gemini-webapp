import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
from google.oauth2 import service_account
import base64

# ───────────────────────────────────────
# 0. model を必ず定義しておく
# ───────────────────────────────────────
model = None
GCP_AUTH_SUCCESS = False

# ───────────────────────────────────────
# 1. GCP 認証＆Vertex AI 初期化
# ───────────────────────────────────────
try:
    gcp_cfg = st.secrets["gcp"]
    GCP_PROJECT_ID = gcp_cfg["project_id"]
    GCP_REGION = "asia-northeast1"

    # secrets.toml に格納した JSON 文字列を辞書化
    svc_info = json.loads(gcp_cfg["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(svc_info)

    # Vertex AI の初期化
    vertexai.init(
        project     = GCP_PROJECT_ID,
        location    = GCP_REGION,
        credentials = credentials
    )

    # モデル読み込み
    model = GenerativeModel("gemini-1.5-pro")
    GCP_AUTH_SUCCESS = True

except Exception as e:
    st.error(f"❌ GCP 認証／Vertex AI 初期化に失敗しました。\nSecrets 設定を確認してください。\n{e}")

# ───────────────────────────────────────
# 2. UI 部分
# ───────────────────────────────────────
st.title("📷 AIによるリフォーム箇所分析アプリ")
st.markdown("""
360度写真や、気になる箇所の詳細な写真をアップロードしてください。  
AIが写真を分析し、リフォームや修繕が必要な箇所を自動でリストアップします。
""")

uploaded = st.file_uploader(
    "分析したい写真を選択してください（複数選択可）",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

# ───────────────────────────────────────
# 3. アップロード直後プレビュー
# ───────────────────────────────────────
if uploaded:
    st.subheader("🔽 アップロード画像プレビュー（クリックで拡大可）")
    cols = st.columns(3)
    for idx, file in enumerate(uploaded):
        b64 = base64.b64encode(file.getvalue()).decode()
        mime = file.type
        html = (
            f'<a href="data:{mime};base64,{b64}" target="_blank">'
            f'<img src="data:{mime};base64,{b64}" width="150" '
            f'style="border:1px solid #ddd; border-radius:4px;" />'
            "</a>"
        )
        cols[idx % 3].markdown(f"**{file.name}**  \n{html}", unsafe_allow_html=True)

prompt = """\
（ここに元のプロンプトをそのまま貼り付けてください）\
"""

# ───────────────────────────────────────
# 4. 分析開始ボタン押下
# ───────────────────────────────────────
if st.button("分析を開始する"):
    # 認証チェック
    if not GCP_AUTH_SUCCESS:
        st.error("GCP 認証が完了していないため、処理を中断しました。")
        st.stop()

    if not uploaded:
        st.warning("まずはファイルをアップロードしてください。")
        st.stop()

    if model is None:
        st.error("モデルのロードに失敗しています。再起動してください。")
        st.stop()

    with st.spinner("AIが写真を分析中です…"):
        # 画像を Part に変換
        parts = [Part.from_data(data=f.getvalue(), mime_type=f.type) for f in uploaded]
        contents = [prompt] + parts

        try:
            response = model.generate_content(contents)
        except Exception as e:
            st.error(f"モデル呼び出し中にエラー発生: {e}")
            st.stop()

    st.subheader("🔍 分析結果")

    # レスポンスを行単位で取得
    lines = response.text.splitlines()

    # 「3. 写真のサムネイル」までをそのまま出力
    for line in lines:
        if line.startswith("3. 写真のサムネイル"):
            break
        st.markdown(line)

    # テーブル部の行を抜き出し（| 写真 | サムネイル | コメント | ヘッダ行はスキップ）
    table_rows = []
    in_table = False
    for line in lines:
        if line.strip().startswith("| 写真") and "コメント" in line:
            in_table = True
            continue
        if in_table:
            if line.strip().startswith("| 写真"):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                # cols = [写真ラベル, サムネイル, コメント]
                if len(cols) >= 3:
                    table_rows.append((cols[0], cols[2]))
            else:
                break  # テーブル終了

    st.markdown("### 📸 各写真のプレビュー＆コメント")

    # アップロード順に対応して表示
    for idx, file in enumerate(uploaded):
        label, comment = table_rows[idx] if idx < len(table_rows) else (f"写真{idx+1}", "")
        b64 = base64.b64encode(file.getvalue()).decode()
        mime = file.type
        thumb_html = (
            f'<a href="data:{mime};base64,{b64}" target="_blank">'
            f'<img src="data:{mime};base64,{b64}" width="150" '
