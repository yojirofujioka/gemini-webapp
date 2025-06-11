import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
from google.oauth2 import service_account

# -----------------------------------------------
# 2. ★★★ GCP認証と初期設定 ★★★
# -----------------------------------------------
try:
    gcp_cfg = st.secrets["gcp"]
    GCP_PROJECT_ID = gcp_cfg["project_id"]
    GCP_REGION     = "asia-northeast1"
    service_account_info = json.loads(gcp_cfg["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )
    vertexai.init(
        project     = GCP_PROJECT_ID,
        location    = GCP_REGION,
        credentials = credentials
    )
    model = GenerativeModel("gemini-1.5-pro")
    GCP_AUTH_SUCCESS = True
except Exception as e:
    GCP_AUTH_SUCCESS = False
    st.error(f"GCPの認証に失敗しました。\nStreamlitのSecrets設定を確認してください。\nエラー: {e}")

# -----------------------------------------------
# 3. UI（画面）部分
# -----------------------------------------------
st.title("📷 AIによるリフォーム箇所分析アプリ")
st.markdown("""
360度写真や、気になる箇所の詳細な写真をアップロードしてください。  
AIが写真を分析し、リフォームや修繕が必要な箇所を自動でリストアップします。
""")

# 画像アップロード
uploaded = st.file_uploader(
    "分析したい写真を選択してください（複数選択可）",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

# アップロード直後にプレビュー＆ファイル名表示
if uploaded:
    st.subheader("アップロード画像プレビュー")
    cols = st.columns(3)
    for idx, file in enumerate(uploaded):
        cols[idx % 3].image(
            file,
            caption=file.name,
            width=150  # お好みで調整
        )

prompt = """
あなたは、日本のリフォーム・原状回復工事を専門とする、経験豊富な積算担当者です。
...
# （以下、省略／元のプロンプトをそのまま入れてください）
"""

# -----------------------------------------------
# 4. 分析開始ボタン押下時の処理
# -----------------------------------------------
if st.button("分析を開始する"):
    if not GCP_AUTH_SUCCESS:
        st.stop()

    if not uploaded:
        st.warning("まずはファイルをアップロードしてください。")
        st.stop()

    with st.spinner("AIが写真を分析中です…"):
        try:
            # 画像データを Part オブジェクトに変換
            parts = [
                Part.from_data(data=f.getvalue(), mime_type=f.type)
                for f in uploaded
            ]

            # プロンプト＋画像を送信
            contents = [prompt] + parts
            response = model.generate_content(contents)

            st.subheader("🔍 分析結果")
            # レポート本文を表示
            st.markdown(response.text)
            st.success("✅ 分析が完了しました！")

        except Exception as e:
            st.error(f"分析中にエラーが発生しました: {e}")
