import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
from google.oauth2 import service_account
import base64

# ───────────────────────────────────────
# 0. model と認証フラグを事前定義
# ───────────────────────────────────────
model = None
GCP_AUTH_SUCCESS = False

# ───────────────────────────────────────
# 1. GCP 認証＆Vertex AI 初期化
# ───────────────────────────────────────
try:
    # .streamlit/secrets.toml の [gcp] セクションを読み込む
    gcp_cfg = st.secrets["gcp"]
    GCP_PROJECT_ID = gcp_cfg["project_id"]
    GCP_REGION     = "asia-northeast1"

    # JSON文字列を辞書化
    service_account_info = json.loads(gcp_cfg["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )

    # Vertex AI 初期化
    vertexai.init(
        project     = GCP_PROJECT_ID,
        location    = GCP_REGION,
        credentials = credentials
    )

    # モデルをロード
    model = GenerativeModel("gemini-1.5-pro")
    GCP_AUTH_SUCCESS = True

except Exception as e:
    st.error(f"❌ GCP 認証／Vertex AI の初期化に失敗しました。\nSecrets をご確認ください。\nエラー: {e}")

# ───────────────────────────────────────
# 2. UI 部分
# ───────────────────────────────────────
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

# ───────────────────────────────────────
# 3. アップロード直後にサムネイルプレビュー
# ───────────────────────────────────────
if uploaded:
    st.subheader("🔽 アップロード画像プレビュー（クリックで拡大）")
    cols = st.columns(3)
    for idx, file in enumerate(uploaded):
        b64 = base64.b64encode(file.getvalue()).decode()
        mime = file.type
        thumb_html = (
            f'<a href="data:{mime};base64,{b64}" target="_blank">'
            f'<img src="data:{mime};base64,{b64}" width="150" '
            f'style="border:1px solid #ddd; border-radius:4px;" />'
            '</a>'
        )
        cols[idx % 3].markdown(f"**{file.name}**  \n{thumb_html}",
                               unsafe_allow_html=True)

# ───────────────────────────────────────
# 4. AIプロンプト定義
# ───────────────────────────────────────
prompt = """
あなたは、日本のリフォーム・原状回復工事を専門とする、経験豊富な積算担当者です。

これから提供する現場写真と図面に基づき、以下の#出力フォーマットと#報告書作成ルールに厳密に従って、プロフェッショナルな報告書を日本語で作成してください。このプロンプトには、理想的な報告書のすべての要素が含まれています。 

# プロジェクト概要

物件名: (例: ○○ビル 301号室)
住所: (例: 東京都渋谷区○○ 1-2-3)
依頼主の要望:
(例: 2LDKを広い1LDKに変更したい)
(例: 内装は白を基調としたシンプルモダンなデザインを希望)
(例: 水回りの設備はすべて一新したい)
(例: 予算は税込みでXXX万円以内を希望)

# 入力データ
現場写真:
[写真1.jpg] - [写真5.jpg]: 各部屋の現状（リビング、和室、キッチン、浴室、トイレ）
[写真6.jpg]: キッチンの配管周りの腐食が確認できるアップ
[写真7.jpg]: 窓サッシの歪みと隙間がわかるアップ

図面:
[平面図.pdf]: 各部屋の寸法、間取り、建具の位置が記載
[電気配線図.pdf]: 既存のスイッチ、コンセント、照明の位置が記載

# 出力フォーマット
以下の構成と項目を厳密に守り、報告書を作成してください。 

1. ヘッダー

書類名: 現場調査報告書 
報告書番号: No. (8桁の数字で自動生成) 
発行日: (今日の日付)

発行元情報:
会社名: (あなたの会社名)
住所: (あなたの住所)
電話/FAX: (あなたの連絡先)
登録番号: (例: T3010901009251) 111111111

2. 物件情報

物件名: (プロジェクト概要から転記)
住所: (プロジェクト概要から転記)

3. 写真のサムネイル、写真についてのコメント
"""

# ───────────────────────────────────────
# 5. 分析開始ボタン押下時の処理
# ───────────────────────────────────────
if st.button("分析を開始する"):
    # 認証チェック
    if not GCP_AUTH_SUCCESS:
